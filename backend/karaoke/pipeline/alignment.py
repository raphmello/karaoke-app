"""Stage 6: word timings, with stable-ts and Whisper turbo (no VAD) on the isolated voice.

- Synced lyrics (LRC): the LRC is the skeleton. The whole text is aligned once only to measure the offset and
  drift between the LRC and this audio; every line then starts at its LRC time mapped onto the audio, and its
  words are aligned inside that line's window alone, so an error cannot spill into the next line. A line whose
  words cannot be aligned gets them spread by length and is marked low_confidence.
- Plain lyrics: the whole text is aligned at once.
- No lyrics, transcription authorized: Whisper transcribes the voice.

Output: lyrics/aligned.json in the architecture's format.
"""
from __future__ import annotations

import logging

import numpy as np

from karaoke.core.storage import read_json, write_json
from karaoke.pipeline.gpu import free_gpu

log = logging.getLogger("karaoke.pipeline")

SAMPLE_RATE = 16000  # what Whisper reads
PAD = 0.3  # seconds of audio on each side of a line's window
MAX_LINE = 12.0  # a line's window never runs longer, even before a long instrumental break
LAST_LINE = 6.0  # window of the last line, which has no next timestamp
OUTLIER = 2.0  # lines further than this from the fitted line do not shape it


def fit_line(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """y = slope * x + intercept that a run of badly aligned lines cannot bend.

    Theil-Sen (median of pairwise slopes) first, then least squares on the points within OUTLIER of it.
    """
    if len(x) < 3:
        return 1.0, float(np.median(y - x)) if len(x) else 0.0
    i, j = np.triu_indices(len(x), k=1)
    dx = x[j] - x[i]
    keep = dx > 1.0
    if not keep.any():
        return 1.0, float(np.median(y - x))
    slope = float(np.median((y[j] - y[i])[keep] / dx[keep]))
    intercept = float(np.median(y - slope * x))
    inliers = np.abs(y - (slope * x + intercept)) <= OUTLIER
    if inliers.sum() >= 3:
        slope, intercept = np.polyfit(x[inliers], y[inliers], 1)
    return float(slope), float(intercept)


def skeleton(stamps: list[dict], slope: float, intercept: float) -> list[dict]:
    """Sung lines with start/end on the audio's clock. Empty LRC lines are not sung but end the line before."""
    lines = []
    for index, stamp in enumerate(stamps):
        if not stamp["text"]:
            continue
        start = slope * stamp["t"] + intercept
        later = [s["t"] for s in stamps[index + 1:] if s["t"] > stamp["t"]]
        end = min(slope * later[0] + intercept, start + MAX_LINE) if later else start + LAST_LINE
        lines.append({"text": stamp["text"], "start": round(max(start, 0.0), 3), "end": round(max(end, 0.0), 3)})
    return lines


def uniform_words(line: dict) -> list[dict]:
    """Words spread over the line by their length, for when they cannot be aligned."""
    words = line["text"].split()
    sung = min((line["end"] - line["start"]) * 0.9, 0.5 * len(words) + 0.5)
    weights = [max(len(w), 1) for w in words]
    total, t, out = sum(weights), line["start"], []
    for word, weight in zip(words, weights, strict=True):
        d = sung * weight / total
        out.append({"w": word, "s": round(t, 3), "e": round(t + d, 3), "c": None})
        t += d
    return out


def _words(segment, offset: float = 0.0) -> list[dict]:
    return [
        {
            "w": w.word.strip(),
            "s": round(offset + float(w.start), 3),
            "e": round(offset + float(w.end), 3),
            "c": round(float(w.probability), 3) if w.probability is not None else None,
        }
        for w in segment.words
        if w.word.strip()
    ]


def _line(start: float, end: float, words: list[dict], low_confidence: bool = False) -> dict:
    return {"start": round(start, 3), "end": round(end, 3), "low_confidence": low_confidence, "words": words}


def load_whisper(settings):
    import stable_whisper

    return stable_whisper.load_model(
        settings.whisper_model, device="cuda", download_root=str(settings.models_dir / "whisper")
    )


def align_line(model, audio: np.ndarray, line: dict, language: str | None) -> list[dict] | None:
    a = max(0.0, line["start"] - PAD)
    b = min(len(audio) / SAMPLE_RATE, line["end"] + PAD)
    piece = audio[int(a * SAMPLE_RATE): int(b * SAMPLE_RATE)]
    if len(piece) < SAMPLE_RATE // 4:
        return None
    try:
        result = model.align(piece, line["text"], language=language)
    except Exception as exc:  # one line failing must not fail the song: it falls back to spread words
        log.debug("linha não alinhada (%s): %s", line["text"][:30], exc)
        return None
    words = [w for segment in (result.segments if result else []) for w in _words(segment, offset=a)]
    return words or None


def align_synced(model, vocals: str, stamps: list[dict], language: str | None) -> tuple[list[dict], dict]:
    from whisper.audio import load_audio

    sung = [s for s in stamps if s["text"]]
    whole = model.align(vocals, "\n".join(s["text"] for s in sung), language=language, original_split=True)
    # the alignment may return fewer segments than lines; the fit only needs the pairs it has
    pairs = [(stamp["t"], float(segment.start)) for stamp, segment in zip(sung, whole.segments, strict=False)]
    x = np.array([p[0] for p in pairs], dtype=float)
    y = np.array([p[1] for p in pairs], dtype=float)
    slope, intercept = fit_line(x, y)

    audio = load_audio(vocals)
    lines = []
    for line in skeleton(stamps, slope, intercept):
        words = align_line(model, audio, line, language)
        if words:
            lines.append(_line(line["start"], line["end"], words))
        else:
            lines.append(_line(line["start"], line["end"], uniform_words(line), low_confidence=True))
    return lines, {"offset_s": round(intercept, 2), "drift_pct": round((slope - 1) * 100, 2)}


def align_plain(model, vocals: str, texts: list[str], language: str | None) -> list[dict]:
    result = model.align(vocals, "\n".join(texts), language=language, original_split=True)
    return [_line(float(s.start), float(s.end), _words(s)) for s in result.segments if s.words]


def transcribe(model, vocals: str) -> tuple[list[dict], str | None]:
    result = model.transcribe(vocals, word_timestamps=True)
    lines = [_line(float(s.start), float(s.end), _words(s)) for s in result.segments if s.words]
    return lines, result.language


def run(ctx) -> dict:
    folder = ctx.folder
    lyrics = read_json(folder.lyrics_source)
    language = ctx.manifest.info("language").get("language")
    vocals = str(folder.vocals)
    extra: dict = {}

    model = load_whisper(ctx.settings)
    try:
        if lyrics and lyrics["synced"]:
            mode, source = "lrc_skeleton", lyrics["source"]
            lines, extra = align_synced(model, vocals, lyrics["lines"], language)
        elif lyrics:
            mode, source = "whole_song", lyrics["source"]
            lines = align_plain(model, vocals, [line["text"] for line in lyrics["lines"] if line["text"]], language)
        else:
            mode, source = "transcription", "transcrita"
            lines, language = transcribe(model, vocals)
    finally:
        del model
        free_gpu()

    write_json(folder.aligned, {"version": 1, "language": language, "source": source, "lines": lines})
    return {
        "mode": mode,
        "language": language,
        "lines": len(lines),
        "low_confidence_lines": sum(line["low_confidence"] for line in lines),
        **extra,
    }
