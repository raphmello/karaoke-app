"""Step 4: Rubber Band R3 pitch shift of both stems at -4 and +4 semitones.

Times it and checks that the duration does not change, which is what keeps the lyric timings valid in any key.
"""
from __future__ import annotations

import argparse
import subprocess
import time

import soundfile as sf

from common import RESULTS, SONGS, encode_opus, load_songs, read_json, write_json

STEPS = (-4, 4)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stem-model", default="bs_roformer_fast", help="separation whose stems are shifted")
    parser.add_argument("--only", help="slug of a single song")
    args = parser.parse_args()

    report = read_json(RESULTS / "pitch.json", {})
    for song in load_songs(args.only):
        folder = SONGS / song["slug"]
        stems = folder / "sep" / args.stem_model
        if not (stems / "instrumental.flac").exists():
            continue
        rows = []
        for steps in STEPS:
            out = folder / "pitch" / f"{steps:+d}"
            out.mkdir(parents=True, exist_ok=True)
            row = {"semitones": steps}
            for stem in ("instrumental", "vocals"):
                src, dst = stems / f"{stem}.flac", out / f"{stem}.wav"
                start = time.perf_counter()
                subprocess.run(["rubberband", "-q", "--fine", "-p", str(steps), str(src), str(dst)], check=True)
                row[f"{stem}_s"] = round(time.perf_counter() - start, 2)
                row[f"{stem}_duration_diff_ms"] = round((sf.info(str(dst)).duration - sf.info(str(src)).duration) * 1000, 1)
            row["total_s"] = round(row["instrumental_s"] + row["vocals_s"], 2)
            encode_opus(out / "instrumental.wav", folder / "play" / f"inst_pitch{steps:+d}.opus")
            rows.append(row)
            print(f"   {song['slug']} {steps:+d}: {row['total_s']} s, duration diff {row['instrumental_duration_diff_ms']} ms")
        report[song["slug"]] = {"stem_model": args.stem_model, "audio_s": round(sf.info(str(stems / "instrumental.flac")).duration, 2), "steps": rows}
        write_json(RESULTS / "pitch.json", report)


if __name__ == "__main__":
    main()
