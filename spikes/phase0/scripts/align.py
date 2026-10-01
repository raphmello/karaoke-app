"""Step 3: align the LRCLIB lyrics to the audio with stable-ts; compare line starts with the LRC timestamps.

LRC timestamps are set by people, one per line, so they are a reference for line starts, not for single words.
Words are checked by eye in the evidence page. Two kinds of disagreement are expected and are not alignment
errors: a constant offset (the video has a different intro, or the LRC marks the line slightly early) and a
small drift (the LRC was synced on a copy playing at a slightly different speed). The error is therefore
measured against a straight line fitted to the line starts (offset and scale), ignoring lines more than 2 s off;
the fitted drift is reported next to it.
"""
from __future__ import annotations

import argparse
import statistics
import time

import numpy as np
import stable_whisper
import torch

from common import MODELS, RESULTS, SONGS, GpuMonitor, free_gpu, load_songs, read_json, write_json

WHISPER = {
    "whisper_turbo": ("openai", "turbo"),
    "fw_large_v3": ("faster", "large-v3"),
}
VARIANTS = {  # name: (model, input, extra align() options)
    "turbo_vocals": ("whisper_turbo", "vocals", {}),
    "turbo_vocals_vad": ("whisper_turbo", "vocals", {"vad": True}),
    "fw_large_v3_vocals": ("fw_large_v3", "vocals", {}),
    "fw_large_v3_vocals_vad": ("fw_large_v3", "vocals", {"vad": True}),
    "turbo_mix": ("whisper_turbo", "mix", {}),  # control: the original mix, to show what isolating the voice buys
}


def load_model(key: str):
    kind, name = WHISPER[key]
    start = time.perf_counter()
    if kind == "openai":
        model = stable_whisper.load_model(name, device="cuda", download_root=str(MODELS / "whisper"))
    else:
        model = stable_whisper.load_faster_whisper(
            name, device="cuda", compute_type="float16", download_root=str(MODELS / "faster-whisper")
        )
    return model, time.perf_counter() - start


def share(flags: list[bool]) -> float:
    return round(sum(flags) / len(flags), 3) if flags else 0.0


def fit_line(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Line y = slope * x + intercept that a run of badly aligned lines cannot bend.

    Theil–Sen (median of pairwise slopes) first, then least squares on the lines within 2 s of it.
    """
    i, j = np.triu_indices(len(x), k=1)
    dx = x[j] - x[i]
    keep = dx > 1.0
    slope = float(np.median((y[j] - y[i])[keep] / dx[keep]))
    intercept = float(np.median(y - slope * x))
    inliers = np.abs(y - (slope * x + intercept)) <= 2.0
    if inliers.sum() >= 3:
        slope, intercept = np.polyfit(x[inliers], y[inliers], 1)
    return float(slope), float(intercept)


def evaluate(lines: list[dict]) -> dict:
    lrc = np.array([line["lrc_t"] for line in lines], dtype=float)
    start = np.array([line["start"] for line in lines], dtype=float)
    offset = float(np.median(start - lrc))
    slope, intercept = fit_line(lrc, start)
    errors = [float(e) for e in np.abs(start - (slope * lrc + intercept))]
    words = [w for line in lines for w in line["words"]]
    probs = [w["c"] for w in words if w["c"] is not None]
    return {
        "lines": len(lines),
        "offset_s": round(offset, 2),
        "drift_pct": round((slope - 1) * 100, 2),
        "mae_raw_s": round(float(np.mean(np.abs(start - lrc))), 2),
        "mae_s": round(statistics.fmean(errors), 2),
        "median_err_s": round(statistics.median(errors), 2),
        "within_0_3s": share([e <= 0.3 for e in errors]),
        "within_0_5s": share([e <= 0.5 for e in errors]),
        "within_1_0s": share([e <= 1.0 for e in errors]),
        "lines_over_2s": int(sum(e > 2.0 for e in errors)),
        "words": len(words),
        "short_words": share([w["e"] - w["s"] < 0.05 for w in words]),
        "mean_word_prob": round(statistics.fmean(probs), 3) if probs else None,
    }


def align_song(model, song: dict, audio, sung: list[dict], options: dict) -> tuple[list[dict], float, int]:
    text = "\n".join(line["text"] for line in sung)
    start = time.perf_counter()
    result = model.align(str(audio), text, language=song["language"], original_split=True, **options)
    elapsed = time.perf_counter() - start
    out = []
    for segment, line in zip(result.segments, sung):
        out.append(
            {
                "start": round(float(segment.start), 3),
                "end": round(float(segment.end), 3),
                "lrc_t": line["t"],
                "words": [
                    {
                        "w": w.word.strip(),
                        "s": round(float(w.start), 3),
                        "e": round(float(w.end), 3),
                        "c": round(float(w.probability), 3) if w.probability is not None else None,
                    }
                    for w in segment.words
                ],
            }
        )
    return out, elapsed, len(result.segments)


def rescore() -> None:
    """Recompute the metrics from the saved aligned.json files, keeping the measured times and VRAM."""
    report = read_json(RESULTS / "alignment.json", {})
    for variant, entry in report.items():
        for slug, metrics in entry["songs"].items():
            path = SONGS / slug / "align" / variant / "aligned.json"
            if "error" in metrics or not path.exists():
                continue
            kept = {k: metrics[k] for k in ("align_s", "segments", "lrc_sung_lines")}
            metrics.clear()
            metrics.update(evaluate(read_json(path)["lines"]))
            metrics.update(kept)
            print(f"   {variant} {slug}: drift {metrics['drift_pct']}%, median error {metrics['median_err_s']} s, "
                  f"within 0.5 s {metrics['within_0_5s']:.0%}, over 2 s {metrics['lines_over_2s']}")
    write_json(RESULTS / "alignment.json", report)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variants", default=",".join(VARIANTS))
    parser.add_argument("--stem-model", default="bs_roformer_fast", help="separation whose vocals.flac is aligned")
    parser.add_argument("--only", help="slug of a single song")
    parser.add_argument("--rescore", action="store_true", help="only recompute metrics from saved alignments")
    args = parser.parse_args()
    if args.rescore:
        rescore()
        return

    monitor = GpuMonitor()
    songs = [s for s in load_songs(args.only) if (SONGS / s["slug"] / "lyrics.json").exists()]
    selected = args.variants.split(",")
    report = read_json(RESULTS / "alignment.json", {})

    for model_key in dict.fromkeys(VARIANTS[v][0] for v in selected):
        print(f"== {model_key}")
        model, _ = load_model(model_key)  # first load downloads the weights; not measured
        del model
        free_gpu()
        torch.cuda.reset_peak_memory_stats()
        with monitor:
            model, load_s = load_model(model_key)
            for variant in [v for v in selected if VARIANTS[v][0] == model_key]:
                _, source, options = VARIANTS[variant]
                per_song = {}
                for song in songs:
                    folder = SONGS / song["slug"]
                    audio = folder / "source.wav" if source == "mix" else folder / "sep" / args.stem_model / "vocals.flac"
                    sung = [line for line in read_json(folder / "lyrics.json")["lines"] if line["text"]]
                    try:
                        lines, align_s, segments = align_song(model, song, audio, sung, options)
                    except Exception as exc:  # keep going: a failed song is itself a finding
                        per_song[song["slug"]] = {"error": repr(exc)}
                        print(f"   {variant} {song['slug']}: FAILED {exc!r}")
                        continue
                    write_json(
                        folder / "align" / variant / "aligned.json",
                        {"version": 1, "language": song["language"], "source": "lrclib", "lines": lines},
                    )
                    metrics = evaluate(lines)
                    metrics.update(
                        {"align_s": round(align_s, 2), "segments": segments, "lrc_sung_lines": len(sung)}
                    )
                    per_song[song["slug"]] = metrics
                    print(
                        f"   {variant} {song['slug']}: {align_s:.1f} s, offset {metrics['offset_s']} s, "
                        f"drift {metrics['drift_pct']}%, median error {metrics['median_err_s']} s, "
                        f"within 0.5 s {metrics['within_0_5s']:.0%}, over 2 s {metrics['lines_over_2s']}"
                    )
                report[variant] = {"model": model_key, "input": source, "options": options, "songs": per_song}
        for variant in [v for v in selected if VARIANTS[v][0] == model_key]:
            report[variant].update(
                {
                    "load_s": round(load_s, 2),
                    "vram_model_mib": monitor.delta_mib,
                    "vram_process_mib": monitor.above_idle_mib,
                    "torch_peak_mib": round(torch.cuda.max_memory_allocated() / 2**20),
                }
            )
        write_json(RESULTS / "alignment.json", report)
        del model
        free_gpu()


if __name__ == "__main__":
    main()
