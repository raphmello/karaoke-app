"""Step 2b: objective separation quality on the MUSDB18 7-second test excerpts, which come with true stems.

SDR (signal-to-distortion ratio, in dB) compares each estimate with the true stem: higher is better.
"""
from __future__ import annotations

import argparse
import statistics

import musdb
import numpy as np
import soundfile as sf

from common import MODELS, RESULTS, WORK, free_gpu, read_json, write_json
from separate import VARIANTS, load, prefetch, separate_one

DEFAULT_RUN = (
    "bs_roformer,bs_roformer_fast,bs_roformer_o1,melband_roformer,melband_roformer_fast,melband_roformer_o1,htdemucs_ft"
)


def sdr(reference: np.ndarray, estimate: np.ndarray) -> float:
    n = min(len(reference), len(estimate))
    reference, estimate = reference[:n], estimate[:n]
    signal = np.sum(reference**2)
    noise = np.sum((reference - estimate) ** 2)
    return float(10 * np.log10((signal + 1e-8) / (noise + 1e-8)))


def summary(values: list[float]) -> dict:
    return {
        "n": len(values),
        "median": round(statistics.median(values), 2),
        "mean": round(statistics.fmean(values), 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variants", default=DEFAULT_RUN)
    parser.add_argument("--limit", type=int, default=50, help="number of test excerpts")
    args = parser.parse_args()

    mus = musdb.DB(root=str(MODELS / "musdb"), download=True, subsets="test")
    tracks = mus.tracks[: args.limit]
    mixes = WORK / "tmp" / "musdb_mix"
    mixes.mkdir(parents=True, exist_ok=True)
    for i, track in enumerate(tracks):
        path = mixes / f"{i:02d}.wav"
        if not path.exists():
            sf.write(path, track.audio, track.rate, subtype="PCM_24")

    report = read_json(RESULTS / "musdb.json", {})
    tmp = WORK / "tmp" / "musdb_sep"
    tmp.mkdir(parents=True, exist_ok=True)
    for key in args.variants.split(","):
        variant = VARIANTS[key]
        print(f"== {key}")
        prefetch(tmp, variant)
        sep, _ = load(tmp, variant)
        rows = []
        for i, track in enumerate(tracks):
            dest = WORK / "tmp" / "musdb_out" / key / f"{i:02d}"
            separate_one(sep, mixes / f"{i:02d}.wav", tmp, dest)
            vocals, _ = sf.read(dest / "vocals.flac", always_2d=True)
            instrumental, _ = sf.read(dest / "instrumental.flac", always_2d=True)
            row = {"track": track.name, "sdr_instrumental": round(sdr(track.targets["accompaniment"].audio, instrumental), 2)}
            true_vocals = track.targets["vocals"].audio
            if np.mean(true_vocals**2) > 1e-6:  # excerpts without singing have no vocal SDR
                row["sdr_vocals"] = round(sdr(true_vocals, vocals), 2)
            rows.append(row)
        report[key] = {
            "instrumental": summary([r["sdr_instrumental"] for r in rows]),
            "vocals": summary([r["sdr_vocals"] for r in rows if "sdr_vocals" in r]),
            "tracks": rows,
        }
        write_json(RESULTS / "musdb.json", report)
        print(f"   instrumental {report[key]['instrumental']}, vocals {report[key]['vocals']}")
        del sep
        free_gpu()


if __name__ == "__main__":
    main()
