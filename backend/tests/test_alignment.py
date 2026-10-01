from itertools import pairwise

import numpy as np
import pytest

from karaoke.pipeline.alignment import LAST_LINE, MAX_LINE, fit_line, skeleton, uniform_words


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
