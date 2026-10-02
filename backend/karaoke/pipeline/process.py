"""The `process` job: each stage runs at most once per video, in order, and its completion goes to manifest.json.

A finished stage is skipped on the next run, so processing a ready video does nothing (and never touches the GPU),
and a run interrupted halfway resumes at the first unfinished stage.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from karaoke.core.config import Settings
from karaoke.core.storage import Manifest, SongFolder

log = logging.getLogger("karaoke.pipeline")


@dataclass
class Context:
    settings: Settings
    folder: SongFolder
    manifest: Manifest
    transcribe: bool = False


@dataclass
class Stage:
    name: str
    run: Callable[[Context], dict]
    # Called after the stage (done now or earlier); a returned status stops the job there.
    stop: Callable[[Context], str | None] = field(default=lambda ctx: None)


def lyrics_gate(ctx: Context) -> str | None:
    """No lyrics found: nothing heavy runs until the owner agrees to a transcription."""
    if ctx.manifest.info("lyrics").get("found") or ctx.transcribe:
        return None
    return "awaiting_decision"


def default_stages() -> list[Stage]:
    from karaoke.pipeline import alignment, download, encode, key, language, lyrics, metadata, separation

    return [
        Stage("metadata", metadata.run),
        Stage("lyrics", lyrics.run, stop=lyrics_gate),
        Stage("download", download.run),
        Stage("separation", separation.run),
        Stage("language", language.run),
        Stage("alignment", alignment.run),
        Stage("key", key.run),
        Stage("encode", encode.run),
    ]


def process(
    video_id: str,
    settings: Settings,
    transcribe: bool = False,
    stages: list[Stage] | None = None,
    on_stage: Callable[[str, int, int], None] | None = None,
) -> str:
    """Run the job for one video and return its final status: ready or awaiting_decision.

    `on_stage(name, index, total)` is called before each stage that actually runs, for progress reports.
    """
    folder = SongFolder(settings.media_dir, video_id)
    folder.root.mkdir(parents=True, exist_ok=True)
    manifest = Manifest.load(folder)
    ctx = Context(settings=settings, folder=folder, manifest=manifest, transcribe=transcribe)
    stages = default_stages() if stages is None else stages

    if all(manifest.done(stage.name) for stage in stages) and manifest.status == "ready":
        log.info("%s: já processado, nada a fazer", folder.video_id)
        return "ready"

    manifest.set(status="processing", error=None, **({"transcribe": True} if transcribe else {}))
    try:
        for index, stage in enumerate(stages):
            if manifest.done(stage.name):
                log.info("%-10s já feito", stage.name)
            else:
                log.info("%-10s começando", stage.name)
                if on_stage:
                    on_stage(stage.name, index, len(stages))
                start = time.perf_counter()
                info = stage.run(ctx)
                elapsed = time.perf_counter() - start
                manifest.complete(stage.name, {**info, "seconds": round(elapsed, 2)})
                log.info("%-10s pronto em %.1f s", stage.name, elapsed)
            status = stage.stop(ctx)
            if status:
                manifest.set(status=status)
                return status
    except BaseException as exc:  # KeyboardInterrupt too: the manifest must not say "processing" forever
        manifest.set(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    manifest.set(status="ready")
    return "ready"
