"""Step 6 (spike 0b): line timing from the LRC, words aligned inside each line.

The whole-song alignment (align.py) puts ~6% of the lines seconds away from where they are sung, and that is what
confuses the singer. Here every line starts where the LRC says, after mapping the LRC onto the audio with the
offset and drift fitted against the whole-song alignment. Words are then placed inside each line's window:

- lrc_uniform: spread over the line by word length (control, no word aligner)
- lrc_stable: stable-ts (Whisper turbo) on the line's window of the isolated vocals
- lrc_ctc: CTC forced alignment (torchaudio MMS_FA, wav2vec2 trained for alignment) on the same window

A line whose words cannot be aligned falls back to lrc_uniform and is marked low_confidence.
"""
from __future__ import annotations

import argparse
import statistics
import time
import unicodedata

import numpy as np
import torch

from align import fit_line
from common import RESULTS, SONGS, free_gpu, load_songs, read_json, write_json

SAMPLE_RATE = 16000
PAD = 0.3  # seconds of audio added on each side of a line's window
MAX_LINE = 12.0  # a window never runs longer than this, even before a long instrumental break
VARIANTS = ("atual", "lrc_uniform", "lrc_stable", "lrc_ctc")


def skeleton(lyrics: dict, whole_song: list[dict]) -> tuple[list[dict], dict]:
    """Sung lines with start/end on the audio's clock, from the LRC mapped by the fitted line."""
    x = np.array([line["lrc_t"] for line in whole_song], dtype=float)
    y = np.array([line["start"] for line in whole_song], dtype=float)
    slope, intercept = fit_line(x, y)
    to_audio = lambda t: slope * t + intercept  # noqa: E731

    stamps = lyrics["lines"]  # every LRC line, empty ones included: they mark where singing stops
    lines = []
    for i, stamp in enumerate(stamps):
        if not stamp["text"]:
            continue
        start = to_audio(stamp["t"])
        nxt = next((s["t"] for s in stamps[i + 1:] if s["t"] > stamp["t"]), None)
        end = min(to_audio(nxt), start + MAX_LINE) if nxt is not None else start + 6.0
        lines.append({"text": stamp["text"], "lrc_t": stamp["t"], "start": round(start, 3), "end": round(end, 3)})

    moved = [abs(a["start"] - b["start"]) for a, b in zip(whole_song, lines)]
    fit = {
        "offset_s": round(intercept, 2),
        "drift_pct": round((slope - 1) * 100, 2),
        "lines_moved_over_1s": int(sum(m > 1.0 for m in moved)),
        "lines_moved_over_2s": int(sum(m > 2.0 for m in moved)),
    }
    return lines, fit


def uniform_words(line: dict) -> list[dict]:
    words = line["text"].split()
    sung = min((line["end"] - line["start"]) * 0.9, 0.5 * len(words) + 0.5)
    weights = [max(len(w), 1) for w in words]
    total, t, out = sum(weights), line["start"], []
    for word, weight in zip(words, weights):
        d = sung * weight / total
        out.append({"w": word, "s": round(t, 3), "e": round(t + d, 3), "c": None})
        t += d
    return out


def finish(line: dict, words: list[dict] | None) -> dict:
    """A line in the aligned.json format; no words means the uniform fallback, marked low confidence."""
    low = not words
    return {
        "start": line["start"],
        "end": line["end"],
        "lrc_t": line["lrc_t"],
        "low_confidence": low,
        "words": uniform_words(line) if low else words,
    }


def window(line: dict, audio_s: float) -> tuple[float, float]:
    return max(0.0, line["start"] - PAD), min(audio_s, line["end"] + PAD)


def align_stable(model, audio: np.ndarray, line: dict, language: str) -> list[dict] | None:
    a, b = window(line, len(audio) / SAMPLE_RATE)
    piece = audio[int(a * SAMPLE_RATE): int(b * SAMPLE_RATE)]
    try:
        result = model.align(piece, line["text"], language=language)
    except Exception:
        return None
    words = [w for seg in result.segments for w in seg.words] if result else []
    if not words:
        return None
    return [
        {"w": w.word.strip(), "s": round(a + float(w.start), 3), "e": round(a + float(w.end), 3),
         "c": round(float(w.probability), 3) if w.probability is not None else None}
        for w in words
    ]


def romanize(word: str, alphabet: set[str]) -> str:
    """MMS_FA reads lowercase Latin letters: drop accents (ã -> a, ç -> c) and anything else."""
    decomposed = unicodedata.normalize("NFKD", word.lower().replace("’", "'"))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch) and ch in alphabet)


def align_ctc(ctc, wave: torch.Tensor, line: dict) -> list[dict] | None:
    model, tokenizer, aligner, alphabet = ctc
    a, b = window(line, wave.size(1) / SAMPLE_RATE)
    piece = wave[:, int(a * SAMPLE_RATE): int(b * SAMPLE_RATE)]
    words = line["text"].split()
    romans = [romanize(w, alphabet) for w in words]
    kept = [i for i, r in enumerate(romans) if r]
    if not kept:
        return None
    try:
        with torch.inference_mode():
            emission, _ = model(piece.to("cuda"))
            # "*" absorbs the audio around the line that is not part of it
            spans = aligner(emission[0], tokenizer(["*"] + [romans[i] for i in kept] + ["*"]))[1:-1]
    except Exception:
        return None
    ratio = piece.size(1) / emission.size(1) / SAMPLE_RATE
    timed = {}
    for i, span in zip(kept, spans):
        score = float(np.exp(np.mean([s.score for s in span])))
        timed[i] = (a + span[0].start * ratio, a + span[-1].end * ratio, score)
    out = []
    for i, word in enumerate(words):
        if i in timed:
            s, e, c = timed[i]
        else:  # nothing to align (digits, symbols): squeeze it between its neighbours
            prev_e = out[-1]["e"] if out else line["start"]
            nxt = next((timed[j][0] for j in range(i + 1, len(words)) if j in timed), prev_e + 0.3)
            s, e, c = prev_e, max(prev_e, nxt), None
        out.append({"w": word, "s": round(s, 3), "e": round(e, 3), "c": round(c, 3) if c is not None else None})
    return out


def agreement(a: list[dict], b: list[dict]) -> float | None:
    """Share of words whose start differs by at most 0.2 s between two alignments of the same text."""
    diffs = [
        abs(wa["s"] - wb["s"])
        for la, lb in zip(a, b)
        if not la["low_confidence"] and not lb["low_confidence"] and len(la["words"]) == len(lb["words"])
        for wa, wb in zip(la["words"], lb["words"])
    ]
    return round(sum(d <= 0.2 for d in diffs) / len(diffs), 3) if diffs else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="slug of a single song")
    parser.add_argument("--stem-model", default="bs_roformer_fast", help="separation whose vocals.flac is aligned")
    args = parser.parse_args()

    import stable_whisper
    import torchaudio
    from whisper.audio import load_audio

    songs = [s for s in load_songs(args.only) if (SONGS / s["slug"] / "align" / "turbo_vocals" / "aligned.json").exists()]
    prepared = {}
    for song in songs:
        folder = SONGS / song["slug"]
        whole = read_json(folder / "align" / "turbo_vocals" / "aligned.json")["lines"]
        lines, fit = skeleton(read_json(folder / "lyrics.json"), whole)
        audio = load_audio(str(folder / "sep" / args.stem_model / "vocals.flac"))
        prepared[song["slug"]] = {"song": song, "whole": whole, "lines": lines, "fit": fit, "audio": audio}

    results = {slug: {"fit": p["fit"], "variants": {}} for slug, p in prepared.items()}
    out = {slug: {} for slug in prepared}

    for slug, p in prepared.items():
        out[slug]["atual"] = [dict(line, low_confidence=False) for line in p["whole"]]
        start = time.perf_counter()
        out[slug]["lrc_uniform"] = [finish(line, None) | {"low_confidence": False} for line in p["lines"]]
        results[slug]["variants"]["lrc_uniform"] = {"seconds": round(time.perf_counter() - start, 2)}

    print("== lrc_stable (Whisper turbo, line by line)")
    model = stable_whisper.load_model("turbo", device="cuda", download_root="/models/whisper")
    for slug, p in prepared.items():
        start = time.perf_counter()
        lines = [finish(line, align_stable(model, p["audio"], line, p["song"]["language"])) for line in p["lines"]]
        elapsed = time.perf_counter() - start
        out[slug]["lrc_stable"] = lines
        results[slug]["variants"]["lrc_stable"] = {
            "seconds": round(elapsed, 2), "fallback_lines": sum(l["low_confidence"] for l in lines)
        }
        print(f"   {slug}: {elapsed:.1f} s, fallback {results[slug]['variants']['lrc_stable']['fallback_lines']} of {len(lines)}")
    del model
    free_gpu()

    print("== lrc_ctc (MMS_FA, line by line)")
    bundle = torchaudio.pipelines.MMS_FA
    ctc_model = bundle.get_model(with_star=True).to("cuda")
    alphabet = {ch for ch in bundle.get_dict(star="*") if len(ch) == 1 and ch not in "*-"}
    ctc = (ctc_model, bundle.get_tokenizer(), bundle.get_aligner(), alphabet)
    for slug, p in prepared.items():
        wave = torch.from_numpy(p["audio"]).unsqueeze(0)
        start = time.perf_counter()
        lines = [finish(line, align_ctc(ctc, wave, line)) for line in p["lines"]]
        elapsed = time.perf_counter() - start
        out[slug]["lrc_ctc"] = lines
        results[slug]["variants"]["lrc_ctc"] = {
            "seconds": round(elapsed, 2), "fallback_lines": sum(l["low_confidence"] for l in lines)
        }
        print(f"   {slug}: {elapsed:.1f} s, fallback {results[slug]['variants']['lrc_ctc']['fallback_lines']} of {len(lines)}")
    del ctc_model
    free_gpu()

    for slug, p in prepared.items():
        results[slug]["stable_ctc_agreement_0_2s"] = agreement(out[slug]["lrc_stable"], out[slug]["lrc_ctc"])
        results[slug]["lines"] = len(p["lines"])
        for variant in VARIANTS:
            write_json(
                SONGS / slug / "sync" / variant / "aligned.json",
                {"version": 1, "language": p["song"]["language"], "source": "lrclib", "lines": out[slug][variant]},
            )
        print(f"   {slug}: fit {p['fit']}, stable × ctc agree {results[slug]['stable_ctc_agreement_0_2s']}")
    write_json(RESULTS / "sync.json", results)


if __name__ == "__main__":
    main()
