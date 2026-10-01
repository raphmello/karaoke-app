"""Step 2a: speed grid for the two RoFormer models on a 60-second excerpt, overlap × precision.

Each output is also compared with the slowest setting (overlap 4, float32) of the same model: "dB vs reference"
says how close the faster output is to it (higher is closer; above ~30 dB the difference is inaudible in practice).
MUSDB (musdb_eval.py) then measures true quality for the settings chosen here.
"""
from __future__ import annotations

import argparse
import subprocess
import time

import soundfile as sf
import torch

from common import RESULTS, SONGS, WORK, GpuMonitor, free_gpu, write_json
from musdb_eval import sdr
from separate import BS, MELBAND, load, prefetch, separate_one

OVERLAPS = (4, 2, 1)
PRECISIONS = ("fp32", "autocast", "fp16")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--song", default="evidencias")
    parser.add_argument("--start", type=float, default=60.0)
    parser.add_argument("--seconds", type=float, default=60.0)
    args = parser.parse_args()

    monitor = GpuMonitor()
    excerpt = WORK / "tmp" / "speed" / "excerpt.wav"
    excerpt.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(args.start), "-t", str(args.seconds),
         "-i", str(SONGS / args.song / "source.wav"), str(excerpt)],
        check=True,
    )
    tmp = WORK / "tmp" / "speed" / "out"
    tmp.mkdir(parents=True, exist_ok=True)

    rows = []
    for model in (BS, MELBAND):
        prefetch(tmp, {"model": model})
        reference = None
        for precision in PRECISIONS:
            for overlap in OVERLAPS:
                variant = {"model": model, "overlap": overlap, "precision": precision}
                dest = WORK / "tmp" / "speed" / f"{model}-{overlap}-{precision}"
                row = {"model": model, "overlap": overlap, "precision": precision}
                torch.cuda.reset_peak_memory_stats()
                try:
                    with monitor:
                        sep, load_s = load(tmp, variant)
                        # first call pays CUDA warm-up; time the second
                        separate_one(sep, excerpt, tmp, dest)
                        elapsed = separate_one(sep, excerpt, tmp, dest)
                    inst, _ = sf.read(dest / "instrumental.flac", always_2d=True)
                    if reference is None:
                        reference = inst
                    row.update({
                        "load_s": round(load_s, 2),
                        "separate_s": round(elapsed, 2),
                        "realtime_factor": round(args.seconds / elapsed, 1),
                        "vram_process_mib": monitor.above_idle_mib,
                        "db_vs_reference": round(sdr(reference, inst), 1),
                    })
                    del sep
                except Exception as exc:  # an unsupported precision is a finding, not a crash
                    row["error"] = repr(exc)[:300]
                free_gpu()
                rows.append(row)
                print(f"   {model[:22]:22} overlap {overlap} {precision:8} -> {row.get('separate_s', 'ERR')} s, "
                      f"{row.get('realtime_factor', '-')}x, {row.get('db_vs_reference', '-')} dB vs ref, "
                      f"{row.get('vram_process_mib', '-')} MiB {row.get('error', '')}")
        write_json(RESULTS / "speed.json", {"song": args.song, "seconds": args.seconds, "rows": rows})


if __name__ == "__main__":
    main()
