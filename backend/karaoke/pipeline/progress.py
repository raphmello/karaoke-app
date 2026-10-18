"""Progress inside a stage (docs/ARCHITECTURE.md, "Progresso da preparação"): the two long stages, separation and
alignment, take ~85% of a song's time, so the screens follow them from inside. The libraries already count their
own work with tqdm progress bars (the separator's chunks, stable-ts's seconds of audio); while a stage runs,
`follow` puts a stand-in in those libraries' place that, instead of drawing a bar, reports how far it got."""
from __future__ import annotations

import importlib
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager

log = logging.getLogger("karaoke.pipeline")

# Where the long stages count their work (each module did `from tqdm import tqdm`)
SEPARATION = ("audio_separator.separator.architectures.mdxc_separator",)
ALIGNMENT = ("stable_whisper.alignment", "stable_whisper.whisper_word_level.original_whisper")


def bar_class(report: Callable[[float], None]) -> type:
    """A tqdm look-alike that reports n / total, for iterating (`for x in tqdm(items)`) or counting by hand
    (`with tqdm(total=...) as bar: bar.update(n)`). It draws nothing."""

    class Bar:
        def __init__(self, iterable=None, *args, total=None, **kwargs):
            self.iterable = iterable
            if total is None and iterable is not None and hasattr(iterable, "__len__"):
                total = len(iterable)
            self.total, self.n = total, 0

        def __iter__(self) -> Iterator:
            for item in self.iterable:
                yield item
                self.update(1)

        def update(self, n: float = 1) -> None:
            self.n += n
            if self.total:
                report(min(self.n / self.total, 1.0))

        def __enter__(self):
            return self

        def __exit__(self, *exc) -> bool:
            return False

        def __getattr__(self, name: str):  # set_description, refresh, close and the like: nothing to draw
            return lambda *args, **kwargs: None

    return Bar


@contextmanager
def follow(modules: tuple[str, ...], report: Callable[[float], None]) -> Iterator[None]:
    """While inside, the libraries' tqdm in `modules` reports its fraction to `report`."""
    bar, patched = bar_class(report), []
    for name in modules:
        try:
            module = importlib.import_module(name)
        except ImportError:
            continue
        if hasattr(module, "tqdm"):
            patched.append((module, module.tqdm))
            module.tqdm = bar
    try:
        yield
    finally:
        for module, original in patched:
            module.tqdm = original


def part(report: Callable[[float], None], start: float, end: float) -> Callable[[float], None]:
    """`report` for one part of a stage: a fraction of the part, as a fraction of the stage."""
    return lambda fraction: report(start + (end - start) * fraction)
