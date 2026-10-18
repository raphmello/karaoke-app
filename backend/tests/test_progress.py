"""A song's preparation shown in step with the time (docs/ARCHITECTURE.md, "Progresso da preparação"): the
libraries' own progress from inside the long stages, each stage weighing the time it takes, and the time left
learned from this PC."""
import json
import sys
import types

import pytest

from karaoke.pipeline.progress import bar_class, follow, part
from karaoke.worker.estimate import DEFAULT_PACE, Pace, Tracker

# --- from inside a stage ------------------------------------------------------------------------------------------

def test_the_stand_in_reports_how_far_a_library_got():
    seen = []
    bar = bar_class(seen.append)
    assert list(bar(["a", "b", "c", "d"])) == ["a", "b", "c", "d"]  # the separator: for chunk in tqdm(chunks)
    with bar(total=10.0, unit="sec", disable=True) as manual:  # stable-ts: counts seconds by hand
        manual.update(5.0)
        manual.set_description("Locate")  # anything else draws nothing
        manual.update(5.0)
    assert seen == [0.25, 0.5, 0.75, 1.0, 0.5, 1.0]


def test_follow_takes_the_libraries_bar_only_while_the_stage_runs(monkeypatch):
    library = types.ModuleType("fake_separator")
    library.tqdm = original = object()
    monkeypatch.setitem(sys.modules, "fake_separator", library)
    seen = []
    with follow(("fake_separator", "not_installed"), part(seen.append, 0.1, 0.9)):
        for _ in library.tqdm([1, 2]):
            pass
    assert library.tqdm is original
    assert seen == pytest.approx([0.5, 0.9])


# --- the time each stage takes ------------------------------------------------------------------------------------

def test_until_it_knows_this_pc_it_goes_by_the_development_pcs_pace():
    pace = Pace()
    assert pace.seconds("separation", 240) == pytest.approx(DEFAULT_PACE["separation"] * 4)
    pace.learn({"metadata": {"duration_s": 120, "seconds": 1.0}, "separation": {"seconds": 60.0}})
    assert pace.seconds("separation", 240) == pytest.approx(60.0 * 2)  # 30 s a minute on this PC


def test_the_pace_comes_from_the_songs_already_prepared(tmp_path):
    for name, (status, seconds) in {"a": ("ready", 40.0), "b": ("failed", 999.0)}.items():
        (tmp_path / name).mkdir()
        manifest = {"status": status, "stages": {"metadata": {"duration_s": 60, "seconds": 1},
                                                  "alignment": {"seconds": seconds}}}
        (tmp_path / name / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert Pace.from_media(tmp_path).seconds("alignment", 60) == pytest.approx(40.0)  # a failed song does not count


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_the_bar_moves_with_the_time_each_stage_takes():
    clock, stages = Clock(), list(DEFAULT_PACE)
    tracker = Tracker(Pace(), stages, clock=clock)
    tracker.duration_s = 240
    for name in ("metadata", "lyrics", "download"):
        tracker.stage(name)
    tracker.stage("separation")
    start, left = tracker.now()
    assert start < 10 and 90 < left < 120  # most of a song's time is still ahead, at its start
    clock.now += 20  # the model loads: nothing reported, the bar goes by the usual time
    loading, _ = tracker.now()
    assert loading > start


def test_when_a_stage_starts_reporting_the_bar_carries_on_and_the_pace_starts_there():
    clock = Clock()
    later = ("language", "alignment", "key", "encode")
    tracker = Tracker(Pace(), ["separation", *later], clock=clock)
    tracker.duration_s = 240
    tracker.stage("separation")
    clock.now += 30  # loading the model took a while
    before, _ = tracker.now()
    tracker.inside(0.05)  # the first chunk
    assert tracker.now()[0] >= before  # never backwards (it went from 14% to 5% before this)
    clock.now += 20
    tracker.inside(0.45)  # 40% of the work in 20 s: 30 s to go here, the loading not counted
    middle, left = tracker.now()
    assert middle > before
    rest = sum(Pace().seconds(name, 240) for name in later)
    assert left == pytest.approx(20 * 0.55 / 0.40 + rest, abs=1)
    tracker.inside(0.2)
    assert tracker.now()[0] == middle  # never backwards


def test_a_short_stage_with_nothing_to_say_moves_with_its_usual_time_and_never_reaches_the_end():
    clock = Clock()
    tracker = Tracker(Pace(), ["encode"], clock=clock)
    tracker.duration_s = 240
    tracker.stage("encode")
    clock.now += 2
    middle, _ = tracker.now()
    clock.now += 60  # much longer than usual
    late, left = tracker.now()
    assert 0 < middle < late <= 95 and left > 0
