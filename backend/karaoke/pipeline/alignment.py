"""Stage 6: word timings, with stable-ts and Whisper turbo (no VAD) on the isolated voice.

- Synced lyrics (LRC): the LRC is the skeleton. The whole text is aligned once only to measure the offset and
  drift between the LRC and this audio, and that measure is checked against where the isolated voice actually
  sings (a whole-song alignment can get lost, as it did in Numb). When the LRC is as long as the video, a drift
  is not believed (in Gangnam Style the lost alignment read 4%) and a plain offset that covers the voice as well
  wins. Every line then starts at its LRC time mapped
  onto the audio; a line that lands where the voice does not sing (an error in the LRC, as in Battle Symphony)
  moves to where the singing starts before the next line. Its words are aligned inside that line's window alone,
  so an error cannot spill into the next line. A line whose words cannot be aligned gets them spread by length
  and is marked low_confidence. From 0.17.4, a line whose LRC window is over REWINDOW away from where the
  whole-song alignment put it is aligned in both windows, and the surest set of windows that keeps the lines in
  order wins (Gangnam Style's LRC had lines 3 to 7 s off, which no offset could fix).
- Plain lyrics: the whole text is aligned at once. Lines whose words came out squeezed into an instant (the
  alignment got lost, as in a long club mix) get them spread by length between the lines around them, and are
  marked low_confidence.
- No lyrics, transcription authorized: Whisper transcribes the voice.

Output: lyrics/aligned.json in the architecture's format.
"""
from __future__ import annotations

import logging

import numpy as np

from karaoke.core.storage import read_json, write_json
from karaoke.pipeline.gpu import free_gpu
from karaoke.pipeline.progress import ALIGNMENT, follow, part

log = logging.getLogger("karaoke.pipeline")

SAMPLE_RATE = 16000  # what Whisper reads
PAD = 0.3  # seconds of audio on each side of a line's window
MAX_LINE = 12.0  # a line's window never runs longer, even before a long instrumental break
LAST_LINE = 6.0  # window of the last line, which has no next timestamp
OUTLIER = 2.0  # lines further than this from the fitted line do not shape it
HOP = 0.05  # seconds per frame of the voice's energy
VOICED = 0.1  # a frame sings when its energy passes this share of the loud frames' (95th percentile)
SEARCH = 60.0  # the plain offsets tried, in seconds each way
MARGIN = 0.05  # how much better (F1) a plain offset must cover the voice to replace Whisper's fit
REWINDOW = 1.0  # seconds between a line's LRC window and the whole-song alignment's that make both worth trying
SURER = 0.1  # how much surer (mean word confidence) the whole-song alignment's window must be to win
MIN_SEGMENT = 0.3  # a whole-song segment shorter than this (seconds) was not really aligned
SAME_LENGTH_S = 3.0  # an LRC this close to the video's length is the same recording: its clock runs as the audio's
MAX_DRIFT = 0.01  # beyond this, a drift on the same recording is the whole-song alignment lost
SILENT = 0.1  # a line whose window has less voice than this share landed where nobody sings
MIN_RUN = 0.5  # seconds of unbroken voice that count as the singing starting
SQUEEZED = 0.05  # a word shorter than this (seconds) was not really aligned


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


def voiced_frames(audio: np.ndarray) -> np.ndarray:
    """Which HOP-long frames of the isolated voice carry singing."""
    n = int(HOP * SAMPLE_RATE)
    frames = audio[: len(audio) // n * n].reshape(-1, n)
    if not len(frames):
        return np.zeros(0, dtype=bool)
    rms = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1))
    return rms > VOICED * np.percentile(rms, 95)


def voice_score(stamps: list[dict], slope: float, intercept: float, voiced: np.ndarray) -> float:
    """F1 of "the voice sings inside the lines" for one LRC-to-audio mapping."""
    lines = np.zeros(len(voiced), dtype=bool)
    for line in skeleton(stamps, slope, intercept):
        lines[int(line["start"] / HOP): int(line["end"] / HOP)] = True
    hits = (voiced & lines).sum()
    if not hits:
        return 0.0
    precision, recall = hits / lines.sum(), hits / voiced.sum()
    return float(2 * precision * recall / (precision + recall))


def check_fit(stamps: list[dict], slope: float, intercept: float, voiced: np.ndarray,
              same_length: bool = False) -> tuple[float, float, dict]:
    """Keep Whisper's fit unless a plain offset (no drift) covers the voice clearly better, or, on an LRC as long as
    the video, at least as well while the fit drifts more than MAX_DRIFT."""
    fitted = voice_score(stamps, slope, intercept, voiced)
    offsets = np.arange(-SEARCH, SEARCH + HOP, 0.1)
    scores = np.array([voice_score(stamps, 1.0, float(o), voiced) for o in offsets])
    # Lines often run a bit longer than the singing, so a range of offsets ties: take the middle of the best range.
    near_best = np.flatnonzero(scores >= scores.max() - 0.005)
    best = int(near_best[len(near_best) // 2])
    info = {"voice_f1_fit": round(fitted, 3), "voice_f1_offset": round(float(scores[best]), 3)}
    if scores[best] > fitted + MARGIN:
        log.info("a reta do Whisper cobre mal a voz (%.2f); usando deslocamento de %.1f s (%.2f)",
                 fitted, offsets[best], scores[best])
        return 1.0, round(float(offsets[best]), 2), {**info, "mapping": "voice"}
    if same_length and abs(slope - 1) > MAX_DRIFT and scores[best] >= fitted:
        log.info("deriva de %.1f%% numa letra da duração do vídeo; usando deslocamento de %.1f s",
                 (slope - 1) * 100, offsets[best])
        return 1.0, round(float(offsets[best]), 2), {**info, "mapping": "length"}
    return slope, intercept, {**info, "mapping": "whisper"}


def first_voice(voiced: np.ndarray, start: float, end: float) -> float | None:
    """Where the first MIN_RUN of unbroken voice begins between start and end; None when there is none."""
    run = int(MIN_RUN / HOP)
    a, b = max(int(start / HOP), 0), min(int(end / HOP), len(voiced))
    count = 0
    for i in range(a, b):
        count = count + 1 if voiced[i] else 0
        if count == run:
            return round((i - run + 1) * HOP, 3)
    return None


def move_silent_lines(lines: list[dict], voiced: np.ndarray) -> int:
    """A line whose window is nearly silent was put where nobody sings: an error in the LRC, not a pause (in Battle
    Symphony a first line at 2 s, over an instrumental intro, sung at 27.8 s). It moves to where the singing starts
    before the next line, and ends where that one begins. Lines change in place; returns how many moved."""
    moved = 0
    for index, line in enumerate(lines):
        window = voiced[int(line["start"] / HOP): int(line["end"] / HOP)]
        if len(window) and window.mean() >= SILENT:
            continue
        limit = lines[index + 1]["start"] if index + 1 < len(lines) else len(voiced) * HOP
        onset = first_voice(voiced, line["start"], limit)
        if onset is None:
            continue
        log.info("linha sem voz em %.1f s (%s); movida para %.1f s", line["start"], line["text"][:30], onset)
        line["start"], line["end"] = onset, round(min(limit, onset + MAX_LINE), 3)
        moved += 1
    return moved


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


def squeezed(line: dict) -> bool:
    """Half or more of the line's words got no time of their own."""
    words = line["words"]
    return bool(words) and 2 * sum(w["e"] - w["s"] < SQUEEZED for w in words) >= len(words)


def spread_squeezed(lines: list[dict]) -> int:
    """Each run of squeezed lines gets the time between the lines around it, shared by length, its words spread
    by length as uniform_words does; the lines are marked low_confidence. Returns how many lines changed."""
    changed, index = 0, 0
    while index < len(lines):
        if not squeezed(lines[index]):
            index += 1
            continue
        end = index
        while end + 1 < len(lines) and squeezed(lines[end + 1]):
            end += 1
        run = lines[index:end + 1]
        a = lines[index - 1]["end"] if index else min(line["start"] for line in run)
        b = lines[end + 1]["start"] if end + 1 < len(lines) else max(line["end"] for line in run)
        b = max(b, a)
        weights = [max(sum(len(w["w"]) for w in line["words"]), 1) for line in run]
        t = a
        for line, weight in zip(run, weights, strict=True):
            span = (b - a) * weight / sum(weights)
            sung = min(span * 0.9, 0.5 * len(line["words"]) + 0.5)
            sizes = [max(len(w["w"]), 1) for w in line["words"]]
            w_t = t
            for word, size in zip(line["words"], sizes, strict=True):
                d = sung * size / sum(sizes)
                word.update(s=round(w_t, 3), e=round(w_t + d, 3), c=None)
                w_t += d
            line.update(start=round(t, 3), end=round(t + span, 3), low_confidence=True)
            t += span
        changed += len(run)
        index = end + 1
    return changed


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


def align_synced(model, vocals: str, stamps: list[dict], language: str | None,
                 report=lambda fraction: None, same_length: bool = False) -> tuple[list[dict], dict]:
    """`report` follows the whole-song alignment (the first ~40%), then the lines one by one."""
    from whisper.audio import load_audio

    sung = [s for s in stamps if s["text"]]
    with follow(ALIGNMENT, part(report, 0.0, 0.4)):
        whole = model.align(vocals, "\n".join(s["text"] for s in sung), language=language, original_split=True)
    # the alignment may return fewer segments than lines; the fit only needs the pairs it has
    pairs = [(stamp["t"], float(segment.start)) for stamp, segment in zip(sung, whole.segments, strict=False)]
    x = np.array([p[0] for p in pairs], dtype=float)
    y = np.array([p[1] for p in pairs], dtype=float)
    slope, intercept = fit_line(x, y)

    audio = load_audio(vocals)
    voiced = voiced_frames(audio)
    slope, intercept, checked = check_fit(stamps, slope, intercept, voiced, same_length)
    windows = skeleton(stamps, slope, intercept)
    moved = move_silent_lines(windows, voiced)
    others = whole_windows(windows, whole.segments)
    options: list[list[tuple[dict, list[dict] | None]]] = []
    for done, (line, other) in enumerate(zip(windows, others, strict=True), start=1):
        choices = [(line, align_line(model, audio, line, language))]
        if other and abs(other["start"] - line["start"]) > REWINDOW:
            choices.append((other, align_line(model, audio, other, language)))
        options.append(choices)
        report(0.4 + 0.6 * done / len(windows))
    picked = in_order(options)
    lines = []
    for (line, words), choices in zip(picked, options, strict=True):
        if line is not choices[0][0]:
            log.info("linha fora do lugar no LRC (%.1f s); o alinhamento da música inteira a põe em %.1f s",
                     choices[0][0]["start"], line["start"])
        if words:
            lines.append(_line(line["start"], line["end"], words))
        else:
            lines.append(_line(line["start"], line["end"], uniform_words(line), low_confidence=True))
    info = {"offset_s": round(intercept, 2), "drift_pct": round((slope - 1) * 100, 2), "moved_lines": moved,
            "rewindowed_lines": sum(p[0] is not o[0][0] for p, o in zip(picked, options, strict=True))}
    return lines, {**info, **checked}


def in_order(options: list[list[tuple[dict, list[dict] | None]]]) -> list[tuple[dict, list[dict] | None]]:
    """One window per line, the LRC's or the whole-song alignment's, so that the lines stay in order and the words
    come out surest, the whole-song window having to be SURER to be worth it (dynamic programming over the lines)."""
    def score(index: int, choice: int) -> float:
        return sureness(options[index][choice][1]) - (SURER if choice else 0.0)

    best: list[list[tuple[float, int]]] = []  # per line and choice: the best total up to it, and the choice before
    for index, choices in enumerate(options):
        row = []
        for choice, (window, _) in enumerate(choices):
            if not index:
                row.append((score(0, choice), -1))
                continue
            before = [(best[index - 1][k][0], k) for k, (prev, _) in enumerate(options[index - 1])
                      if best[index - 1][k][0] > -np.inf and prev["start"] <= window["start"]]
            total, k = max(before) if before else (-np.inf, -1)
            row.append((total + score(index, choice), k))
        best.append(row)
    if not options or max(best[-1])[0] == -np.inf:  # no order holds (should not happen): the LRC's windows
        return [choices[0] for choices in options]
    choice = max(range(len(best[-1])), key=lambda k: best[-1][k][0])
    picked = []
    for index in range(len(options) - 1, -1, -1):
        picked.append(options[index][choice])
        choice = best[index][choice][1]
    return picked[::-1]


def whole_windows(windows: list[dict], segments) -> list[dict | None]:
    """Each line's window by the whole-song alignment, None where it did not really align the line. Only when it
    returned one segment per line: otherwise the pairs cannot be told."""
    if len(segments) != len(windows):
        return [None] * len(windows)
    out: list[dict | None] = []
    for line, segment in zip(windows, segments, strict=True):
        start, end = float(segment.start), float(segment.end)
        out.append({"text": line["text"], "start": round(start, 3), "end": round(end, 3)}
                   if end - start >= MIN_SEGMENT else None)
    return out


def sureness(words: list[dict] | None) -> float:
    """The alignment's mean confidence in a line's words; -1 when they could not be aligned."""
    if not words:
        return -1.0
    return sum(w["c"] or 0.0 for w in words) / len(words)


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
    ctx.progress(0.1)  # the model is in memory; the rest follows the audio (pipeline/progress.py)
    report = part(ctx.progress, 0.1, 1.0)
    try:
        if lyrics and lyrics["synced"]:
            mode, source = "lrc_skeleton", lyrics["source"]
            video = ctx.manifest.info("metadata").get("duration_s")
            same_length = bool(video and lyrics.get("duration")
                               and abs(lyrics["duration"] - video) <= SAME_LENGTH_S)
            lines, extra = align_synced(model, vocals, lyrics["lines"], language, report, same_length)
        elif lyrics:
            mode, source = "whole_song", lyrics["source"]
            with follow(ALIGNMENT, report):
                lines = align_plain(model, vocals, [line["text"] for line in lyrics["lines"] if line["text"]],
                                    language)
            extra = {"spread_lines": spread_squeezed(lines)}
        else:
            mode, source = "transcription", "transcrita"
            with follow(ALIGNMENT, report):
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
