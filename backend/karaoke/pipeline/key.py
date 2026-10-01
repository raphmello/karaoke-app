"""Stage 7: the original key of the song, from the instrumental (essentia KeyExtractor)."""
from __future__ import annotations


def run(ctx) -> dict:
    import essentia.standard as es

    audio = es.MonoLoader(filename=str(ctx.folder.instrumental), sampleRate=44100)()
    key, scale, strength = es.KeyExtractor()(audio)
    return {"key": key, "scale": scale, "strength": round(float(strength), 3)}
