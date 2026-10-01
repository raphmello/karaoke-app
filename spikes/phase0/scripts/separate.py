"""Step 2: separate every song with each candidate variant; measure load time, separation time and VRAM.

A variant is a model plus its speed settings. RoFormer models default to overlap 4 (each stretch of audio is
predicted four times) in float32; the speed grid (speed.py) shows what lower overlap and half precision buy.
"""
from __future__ import annotations

import argparse
import logging
import re
import shutil
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from audio_separator.separator import Separator

from common import (
    MODELS, RESULTS, SONGS, WORK, GpuMonitor, encode_opus, free_gpu, load_songs, probe_duration, read_json, write_json,
)

BS = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"
MELBAND = "vocals_mel_band_roformer.ckpt"
VARIANTS = {
    "bs_roformer": {"model": BS},
    "bs_roformer_fast": {"model": BS, "overlap": 2, "precision": "autocast"},
    "bs_roformer_o1": {"model": BS, "overlap": 1, "precision": "autocast"},
    "melband_roformer": {"model": MELBAND},
    "melband_roformer_fast": {"model": MELBAND, "overlap": 2, "precision": "autocast"},
    "melband_roformer_o1": {"model": MELBAND, "overlap": 1, "precision": "autocast"},
    "htdemucs_ft": {"model": "htdemucs_ft.yaml"},
}
DEFAULT_RUN = "bs_roformer_fast,melband_roformer_fast,htdemucs_ft"
STEM = re.compile(r"_\(([^)]+)\)")

# GitHub answers HTTP 500 for this release asset (checked 2026-10-01). UVR's own data repo has the same file
# (2273 bytes, like the asset); placed in the model folder first, audio-separator skips its download.
CONFIG_MIRRORS = {
    "model_bs_roformer_ep_317_sdr_12.9755.yaml":
        "https://raw.githubusercontent.com/TRvlvr/application_data/main/mdx_model_data/mdx_c_configs/"
        "model_bs_roformer_ep_317_sdr_12.9755.yaml",
}


def place_mirrored_configs() -> None:
    import requests

    folder = MODELS / "audio-separator"
    folder.mkdir(parents=True, exist_ok=True)
    for name, url in CONFIG_MIRRORS.items():
        if not (folder / name).exists():
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            (folder / name).write_bytes(resp.content)


def make_separator(out_dir: Path, variant: dict) -> Separator:
    precision = variant.get("precision", "fp32")
    return Separator(
        log_level=logging.WARNING,
        model_file_dir=str(MODELS / "audio-separator"),
        output_dir=str(out_dir),
        output_format="FLAC",
        use_autocast=precision == "autocast",
        use_native_fp16=precision == "fp16",
        mdxc_params={
            "segment_size": 256,
            "override_model_segment_size": False,
            "batch_size": None,
            "overlap": variant.get("overlap"),  # None: the model's own setting
            "pitch_shift": 0,
        },
    )


def load(out_dir: Path, variant: dict) -> tuple[Separator, float]:
    start = time.perf_counter()
    sep = make_separator(out_dir, variant)
    sep.load_model(model_filename=variant["model"])
    return sep, time.perf_counter() - start


def prefetch(out_dir: Path, variant: dict) -> None:
    """Download the model outside the measurement; load time is then measured from local disk."""
    place_mirrored_configs()
    sep, _ = load(out_dir, variant)
    del sep
    free_gpu()


def to_vocals_instrumental(tmp: Path, dest: Path) -> None:
    """Move the model's outputs to dest as vocals.flac and instrumental.flac.

    Demucs writes four stems; its instrumental is the sum of every stem except vocals.
    """
    stems = {}
    for path in tmp.glob("*.flac"):
        match = STEM.search(path.name)
        if match:
            stems[match[1].lower()] = path
    dest.mkdir(parents=True, exist_ok=True)
    shutil.move(stems.pop("vocals"), dest / "vocals.flac")
    if "instrumental" in stems:
        shutil.move(stems.pop("instrumental"), dest / "instrumental.flac")
    elif len(stems) == 1:
        shutil.move(stems.popitem()[1], dest / "instrumental.flac")
    else:
        mix, rate = None, None
        for path in stems.values():
            data, rate = sf.read(path, always_2d=True)
            mix = data if mix is None else mix[: len(data)] + data[: len(mix)]
            path.unlink()
        sf.write(dest / "instrumental.flac", np.clip(mix, -1.0, 1.0), rate, subtype="PCM_24")


def separate_one(sep: Separator, src: Path, tmp: Path, dest: Path) -> float:
    for leftover in tmp.glob("*"):
        leftover.unlink()
    start = time.perf_counter()
    sep.separate(str(src))
    elapsed = time.perf_counter() - start
    to_vocals_instrumental(tmp, dest)
    return elapsed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variants", default=DEFAULT_RUN, help="comma-separated keys of VARIANTS")
    parser.add_argument("--only", help="slug of a single song")
    args = parser.parse_args()

    monitor = GpuMonitor()
    songs = [s for s in load_songs(args.only) if (SONGS / s["slug"] / "source.wav").exists()]
    report = read_json(RESULTS / "separation.json", {})
    tmp = WORK / "tmp" / "separate"
    tmp.mkdir(parents=True, exist_ok=True)

    for key in args.variants.split(","):
        variant = VARIANTS[key]
        print(f"== {key} {variant}")
        prefetch(tmp, variant)
        torch.cuda.reset_peak_memory_stats()
        per_song = report.get(key, {}).get("songs", {}) if args.only else {}
        with monitor:
            sep, load_s = load(tmp, variant)
            for song in songs:
                folder = SONGS / song["slug"]
                dest = folder / "sep" / key
                sep_s = separate_one(sep, folder / "source.wav", tmp, dest)
                encode_s = encode_opus(dest / "instrumental.flac", folder / "play" / f"inst_{key}.opus")
                encode_s += encode_opus(dest / "vocals.flac", folder / "play" / f"vocals_{key}.opus")
                audio_s = probe_duration(folder / "source.wav")
                per_song[song["slug"]] = {
                    "separate_s": round(sep_s, 2),
                    "audio_s": round(audio_s, 2),
                    "realtime_factor": round(audio_s / sep_s, 1),
                    "encode_opus_s": round(encode_s, 2),
                }
                print(f"   {song['slug']}: {sep_s:.1f} s for {audio_s:.0f} s of audio")
        report[key] = {
            **variant,
            "cuda": torch.cuda.is_available(),
            "load_s": round(load_s, 2),
            "vram_model_mib": monitor.delta_mib,
            "vram_process_mib": monitor.above_idle_mib,
            "vram_idle_mib": round(monitor.idle_mib),
            "torch_peak_mib": round(torch.cuda.max_memory_allocated() / 2**20),
            "songs": per_song,
        }
        write_json(RESULTS / "separation.json", report)
        del sep
        free_gpu()


if __name__ == "__main__":
    main()
