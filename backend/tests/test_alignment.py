from itertools import pairwise

import numpy as np
import pytest

from karaoke.pipeline.alignment import (
    HOP,
    LAST_LINE,
    MAX_LINE,
    SAMPLE_RATE,
    check_fit,
    fit_line,
    skeleton,
    uniform_words,
    voiced_frames,
)


def test_fit_line_finds_offset_and_drift():
    lrc = np.linspace(10, 280, 50)
    audio = 1.012 * lrc - 5.5  # the clip starts 5.5 s earlier and plays 1.2% slower than the LRC's copy
    slope, intercept = fit_line(lrc, audio)
    assert slope == pytest.approx(1.012, abs=1e-6)
    assert intercept == pytest.approx(-5.5, abs=1e-4)


def test_fit_line_ignores_a_run_of_badly_aligned_lines():
    lrc = np.linspace(0, 340, 50)
    audio = lrc + 0.3
    audio[-6:] -= np.array([17, 21, 29, 22, 25, 40])  # the collapsed ending seen in the spike
    slope, intercept = fit_line(lrc, audio)
    assert slope == pytest.approx(1.0, abs=1e-6)
    assert intercept == pytest.approx(0.3, abs=1e-4)


def test_fit_line_with_too_few_lines_keeps_the_scale():
    assert fit_line(np.array([10.0, 20.0]), np.array([11.0, 21.5])) == (1.0, pytest.approx(1.25))


def test_skeleton_maps_lines_and_uses_empty_lines_as_ends():
    stamps = [
        {"t": 10.0, "text": "one"},
        {"t": 14.0, "text": ""},  # singing pauses here
        {"t": 30.0, "text": "two"},
        {"t": 60.0, "text": "three"},
        {"t": 80.0, "text": "four"},
    ]
    lines = skeleton(stamps, slope=1.0, intercept=2.0)
    assert [line["text"] for line in lines] == ["one", "two", "three", "four"]
    assert (lines[0]["start"], lines[0]["end"]) == (12.0, 16.0)
    assert lines[1]["end"] == 32.0 + MAX_LINE  # a long gap does not stretch the window
    assert lines[3]["end"] == 82.0 + LAST_LINE


def test_uniform_words_cover_the_line_by_length():
    words = uniform_words({"text": "a longer line", "start": 10.0, "end": 20.0})
    assert [w["w"] for w in words] == ["a", "longer", "line"]
    assert words[0]["s"] == 10.0
    assert all(a["e"] == pytest.approx(b["s"]) for a, b in pairwise(words))
    assert words[-1]["e"] <= 20.0
    assert words[1]["e"] - words[1]["s"] > words[0]["e"] - words[0]["s"]


# A voice that sings where an LRC says, almost through each 4 s line, then a pause: the Numb case in small.
STAMPS = [{"t": 20.0 + 4 * i, "text": f"line {i}"} for i in range(8)] + [{"t": 52.0, "text": ""}]


def voice_at(stamps, shift=0.0, seconds=70.0) -> np.ndarray:
    audio = np.zeros(int(seconds * SAMPLE_RATE), dtype=np.float32)
    for stamp in stamps:
        if stamp["text"]:
            a, b = int((stamp["t"] + shift) * SAMPLE_RATE), int((stamp["t"] + shift + 3.8) * SAMPLE_RATE)
            audio[a:b] = 0.3 * np.sin(np.arange(b - a) / 10)
    return audio


def test_voiced_frames_follow_the_singing():
    voiced = voiced_frames(voice_at(STAMPS))
    assert voiced[int(21 / HOP)] and not voiced[int(10 / HOP)] and not voiced[int(23.9 / HOP)]


def test_a_lost_whisper_fit_gives_way_to_the_offset_the_voice_shows():
    voiced = voiced_frames(voice_at(STAMPS, shift=2.0))
    slope, intercept, info = check_fit(STAMPS, 0.76, -21.8, voiced)  # what Whisper measured for Numb
    assert info["mapping"] == "voice"
    assert slope == 1.0 and intercept == pytest.approx(2.0, abs=0.15)
    assert info["voice_f1_offset"] > info["voice_f1_fit"] + 0.05


def test_a_good_whisper_fit_stays():
    voiced = voiced_frames(voice_at(STAMPS, shift=0.5))
    slope, intercept, info = check_fit(STAMPS, 1.002, 0.45, voiced)
    assert (slope, intercept, info["mapping"]) == (1.002, 0.45, "whisper")
