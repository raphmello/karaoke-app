"""How far a song's preparation is, and how long it still takes (docs/ARCHITECTURE.md, "Progresso da preparação").

Each stage's time grows with the song's length, so each is measured in seconds per minute of song. The worker
learns this PC's pace from the songs it already prepared (each manifest keeps every stage's seconds) and, until it
has any, uses the pace measured on the development PC (RTX 4060 Ti). The bar then moves in step with the time: a
stage weighs what it takes, and the long ones also report from inside (pipeline/progress.py)."""
from __future__ import annotations

import json
import logging
import statistics
import time
from collections import deque
from pathlib import Path

log = logging.getLogger("karaoke.worker")

# Seconds per minute of song on the development PC (RTX 4060 Ti), the median of the songs it prepared
DEFAULT_PACE = {
    "metadata": 0.6, "lyrics": 0.2, "download": 0.4, "separation": 15.6,
    "language": 0.05, "alignment": 8.9, "key": 0.5, "encode": 1.0,
}
DEFAULT_DURATION_S = 240.0  # before the metadata says how long the song is
SAMPLES = 30  # the latest songs, per stage: a new video card shows up fast


def song_duration(stages: dict) -> float | None:
    for stage in ("metadata", "download"):
        duration = (stages.get(stage) or {}).get("duration_s")
        if isinstance(duration, (int, float)) and duration > 0:
            return float(duration)
    return None


class Pace:
    """Seconds per minute of song for each stage, as this PC does them."""

    def __init__(self) -> None:
        self.samples: dict[str, deque[float]] = {name: deque(maxlen=SAMPLES) for name in DEFAULT_PACE}

    @classmethod
    def from_media(cls, media_dir: Path) -> Pace:
        """Learned from the manifests of the songs already prepared, the newest last."""
        pace = cls()
        manifests = sorted(media_dir.glob("*/manifest.json"), key=lambda path: path.stat().st_mtime)
        for path in manifests:
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if manifest.get("status") == "ready":
                pace.learn(manifest.get("stages") or {})
        return pace

    def learn(self, stages: dict) -> None:
        """A song's stage times, from its manifest."""
        duration = song_duration(stages)
        if not duration:
            return
        for name, info in stages.items():
            seconds = info.get("seconds") if isinstance(info, dict) else None
            if name in self.samples and isinstance(seconds, (int, float)) and seconds >= 0:
                self.samples[name].append(seconds / (duration / 60))

    def seconds(self, stage: str, duration_s: float | None) -> float:
        """How long `stage` should take for a song this long."""
        known = self.samples.get(stage)
        per_minute = statistics.median(known) if known else DEFAULT_PACE.get(stage, 1.0)
        return per_minute * (duration_s or DEFAULT_DURATION_S) / 60


class Tracker:
    """One job's progress: the stages it runs, which one runs now and how far inside it is.

    A long stage first loads its model, with nothing to report, and the bar moves with the time it usually takes.
    When the stage starts reporting from inside, the bar carries on from where it was, never backwards, and the
    pace is measured from that moment, so the loading does not make the time left jump."""

    def __init__(self, pace: Pace, stages: list[str], clock=time.monotonic) -> None:
        self.pace, self.stages, self.clock = pace, stages, clock
        self.duration_s: float | None = None
        self.current: str | None = None
        self.finished: list[str] = []
        self.started = clock()
        self.fraction = 0.0  # inside the current stage, as it reports it
        self.first: tuple[float, float, float] | None = None  # its first report: when, its fraction, the bar's then
        self.shown = 0.0  # the bar's fraction of the current stage, last time: it never goes back

    def stage(self, name: str) -> None:
        if self.current and self.current != name:
            self.finished.append(self.current)
        self.current, self.started, self.fraction = name, self.clock(), 0.0
        self.first, self.shown = None, 0.0

    def inside(self, fraction: float) -> None:
        fraction = min(fraction, 1.0)
        if self.first is None:  # the bar carries on from where the time had taken it
            self.first = (self.clock(), fraction, max(self.shown, self.by_time()))
        self.fraction = max(self.fraction, fraction)  # never backwards

    def by_time(self) -> float:
        """How far the current stage should be by now, from the time it usually takes."""
        current = self.pace.seconds(self.current, self.duration_s) if self.current else 0.0
        return min((self.clock() - self.started) / current, 0.95) if current else 0.0

    def now(self) -> tuple[int, int | None]:
        """The progress (0-99 %) and the seconds still to go."""
        expected = {name: self.pace.seconds(name, self.duration_s) for name in self.stages}
        total = sum(expected.values()) or 1.0
        current = expected.get(self.current, 0.0)
        now = self.clock()
        elapsed = now - self.started
        if self.first is None:  # nothing reported (yet): the time this stage usually takes
            shown = self.by_time()
            left_here = max(current - elapsed, current * 0.05)
        else:  # from where the bar was when the reports began, to the end, as the stage says
            when, base_fraction, base_shown = self.first
            moved = (self.fraction - base_fraction) / (1 - base_fraction) if base_fraction < 1 else 1.0
            shown = base_shown + (1 - base_shown) * moved
            reported = self.fraction - base_fraction
            usual = max(current - elapsed, current * 0.05)
            if reported > 0:
                # This PC's pace on this very song, since the work itself began, trusted more as more of it is
                # done: a few chunks alone would make the time left jump
                measured = (now - when) * (1 - self.fraction) / reported
                trust = min(reported / 0.2, 1.0)
                left_here = trust * measured + (1 - trust) * usual
            else:
                left_here = usual
        self.shown = max(self.shown, shown)
        done = sum(expected[name] for name in self.finished if name in expected) + current * self.shown
        later = self.stages[self.stages.index(self.current) + 1:] if self.current in self.stages else []
        left = left_here + sum(expected[name] for name in later)
        return min(int(100 * done / total), 99), max(round(left), 1)  # never "done" before it is
