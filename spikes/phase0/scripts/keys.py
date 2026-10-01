"""Original key of each spike song, from the instrumental (essentia KeyExtractor, as in the app's pipeline).

Runs in the worker image, which has essentia:
docker run --rm --entrypoint python -v <spike>:/spike karaoke-worker /spike/scripts/keys.py
"""
from __future__ import annotations

import json
from pathlib import Path

import essentia.standard as es

WORK = Path("/spike/work")


def main() -> None:
    keys = {}
    for song in sorted((WORK / "songs").iterdir()):
        instrumental = song / "sep" / "bs_roformer_fast" / "instrumental.flac"
        if not instrumental.exists():
            continue
        audio = es.MonoLoader(filename=str(instrumental), sampleRate=44100)()
        key, scale, strength = es.KeyExtractor()(audio)
        keys[song.name] = {"key": key, "scale": scale, "strength": round(float(strength), 3)}
        print(song.name, key, scale, round(float(strength), 3))
    (WORK / "results" / "keys.json").write_text(json.dumps(keys, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
