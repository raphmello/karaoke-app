from itertools import pairwise

import numpy as np
import pytest

from karaoke.pipeline.alignment import (
    HOP,
    LAST_LINE,
    MAX_LINE,
    SAMPLE_RATE,
    check_fit,
    first_voice,
    fit_line,
    move_silent_lines,
    skeleton,
    spread_squeezed,
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


def test_a_line_the_lrc_put_on_silence_moves_to_where_the_singing_starts():
    # Battle Symphony in small: the LRC puts the first line at 2 s, over an instrumental intro; it is sung at 27.8 s
    stamps = [{"t": 2.0, "text": "first"}, {"t": 33.0, "text": "second"}, {"t": 40.0, "text": "third"}]
    voiced = voiced_frames(voice_at([{"t": 27.8, "text": "first"}, {"t": 33.0, "text": "second"},
                                     {"t": 40.0, "text": "third"}], seconds=50.0))
    lines = skeleton(stamps, 1.0, 0.0)
    assert move_silent_lines(lines, voiced) == 1
    assert lines[0]["start"] == pytest.approx(27.8, abs=HOP) and lines[0]["end"] == 33.0
    assert (lines[1]["start"], lines[2]["start"]) == (33.0, 40.0)  # the lines with voice stay


def test_a_silent_line_with_no_voice_before_the_next_one_stays():
    stamps = [{"t": 2.0, "text": "first"}, {"t": 20.0, "text": "second"}]
    voiced = voiced_frames(voice_at([{"t": 20.0, "text": "second"}], seconds=30.0))
    lines = skeleton(stamps, 1.0, 0.0)
    assert move_silent_lines(lines, voiced) == 0
    assert lines[0]["start"] == 2.0


def test_the_singing_starts_at_the_first_unbroken_half_second():
    voiced = np.zeros(int(10 / HOP), dtype=bool)
    voiced[int(2 / HOP): int(2.2 / HOP)] = True  # a breath, too short
    voiced[int(5 / HOP): int(7 / HOP)] = True
    assert first_voice(voiced, 0.0, 10.0) == pytest.approx(5.0)
    assert first_voice(voiced, 0.0, 4.0) is None


def test_a_good_whisper_fit_stays():
    voiced = voiced_frames(voice_at(STAMPS, shift=0.5))
    slope, intercept, info = check_fit(STAMPS, 1.002, 0.45, voiced)
    assert (slope, intercept, info["mapping"]) == (1.002, 0.45, "whisper")


def test_on_an_lrc_as_long_as_the_video_a_drift_the_voice_does_not_need_gives_way():
    # Gangnam Style in small: singing with no pause, so a drifting fit covers the voice almost as well
    audio = np.zeros(int(70 * SAMPLE_RATE), dtype=np.float32)
    audio[20 * SAMPLE_RATE: 52 * SAMPLE_RATE] = 0.3 * np.sin(np.arange(32 * SAMPLE_RATE) / 10)
    voiced = voiced_frames(audio)
    assert check_fit(STAMPS, 0.96, 1.0, voiced)[2]["mapping"] == "whisper"
    slope, intercept, info = check_fit(STAMPS, 0.96, 1.0, voiced, same_length=True)
    assert (slope, info["mapping"]) == (1.0, "length") and intercept == pytest.approx(0.0, abs=0.6)
    # a drift within MAX_DRIFT stays, as long as the lengths match
    assert check_fit(STAMPS, 1.002, 0.45, voiced, same_length=True)[2]["mapping"] == "whisper"


def test_lines_squeezed_into_an_instant_are_spread_between_their_neighbours():
    def line(start, end, words):
        return {"start": start, "end": end, "low_confidence": False,
                "words": [{"w": w, "s": s, "e": e, "c": 0.9} for w, s, e in words]}

    lines = [line(10.0, 12.0, [("um", 10.0, 11.0), ("dois", 11.0, 12.0)]),
             line(12.0, 12.0, [("tres", 12.0, 12.0), ("quatro", 12.0, 12.0)]),
             line(12.0, 12.01, [("cinco", 12.0, 12.0), ("seis", 12.0, 12.01)]),
             line(20.0, 22.0, [("sete", 20.0, 21.0), ("oito", 21.0, 22.0)])]
    assert spread_squeezed(lines) == 2
    assert [line["low_confidence"] for line in lines] == [False, True, True, False]
    assert lines[1]["start"] == 12.0 and lines[2]["end"] == 20.0
    words = [w for line in lines[1:3] for w in line["words"]]
    assert all(w["e"] - w["s"] > 0.1 for w in words)
    assert all(a["e"] <= b["s"] + 1e-6 for a, b in pairwise(words))
    assert lines[0]["words"][0]["s"] == 10.0 and lines[3]["words"][0]["s"] == 20.0  # the others stay


def test_lines_take_the_whole_song_window_only_when_surer_and_in_order():
    from karaoke.pipeline.alignment import in_order

    def w(start):
        return {"start": start, "end": start + 2}

    def sure(c):
        return [{"w": "a", "s": 0, "e": 1, "c": c}]

    lrc = [w(10), w(12), w(14)]
    whole = [w(13), w(11)]
    options = [
        [(lrc[0], sure(0.1)), (whole[0], sure(0.9))],  # much surer at 13 s
        [(lrc[1], sure(0.2)), (whole[1], sure(0.95))],  # surer at 11 s, but that would come before line 0's 13 s
        [(lrc[2], sure(0.8))],
    ]
    picked = in_order(options)
    starts = [window["start"] for window, _ in picked]
    assert starts == sorted(starts)
    assert picked[2][0] is lrc[2]
    # a whole-song window barely surer than the LRC's stays out
    assert in_order([[(lrc[0], sure(0.5)), (whole[0], sure(0.55))]])[0][0] is lrc[0]
