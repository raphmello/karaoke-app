"""Step 4b: ways to make a key change faster, on one song at +4 semitones.

R3 (finer) with the two stems one after the other is what pitch.py measures. Here: R3 with both stems at once,
and R2 (faster) with both stems at once. The R2 instrumental is encoded for listening next to R3's.
"""
from __future__ import annotations

import argparse
import subprocess
import time

import soundfile as sf

from common import RESULTS, SONGS, encode_opus, write_json

STEPS = 4


def shift_both(stems, out, engine: str) -> float:
    out.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    procs = [
        subprocess.Popen(["rubberband", "-q", engine, "-p", str(STEPS), str(stems / f"{s}.flac"), str(out / f"{s}.wav")])
        for s in ("instrumental", "vocals")
    ]
    for proc in procs:
        if proc.wait() != 0:
            raise RuntimeError(f"rubberband exited with {proc.returncode}")
    return time.perf_counter() - start


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--song", default="evidencias")
    parser.add_argument("--stem-model", default="bs_roformer_fast")
    args = parser.parse_args()

    folder = SONGS / args.song
    stems = folder / "sep" / args.stem_model
    rows = []
    for label, engine in (("R3 (finer), stems em paralelo", "--fine"), ("R2 (faster), stems em paralelo", "--fast")):
        out = folder / "pitch_options" / engine.strip("-")
        elapsed = shift_both(stems, out, engine)
        diff_ms = (sf.info(str(out / "instrumental.wav")).duration - sf.info(str(stems / "instrumental.flac")).duration) * 1000
        rows.append({"option": label, "wall_s": round(elapsed, 2), "duration_diff_ms": round(diff_ms, 1)})
        if engine == "--fast":
            encode_opus(out / "instrumental.wav", folder / "play" / f"inst_pitch+{STEPS}_r2.opus")
        print(f"   {label}: {elapsed:.1f} s, duration diff {diff_ms:.1f} ms")
    write_json(
        RESULTS / "pitch_options.json",
        {"song": args.song, "semitones": STEPS, "audio_s": round(sf.info(str(stems / "instrumental.flac")).duration, 2), "rows": rows},
    )


if __name__ == "__main__":
    main()
