"""The job loop: takes the next job by priority, runs the phase 1 pipeline and records the outcome.

One job at a time, because the GPU holds one model at a time. Progress goes to the database and, best effort, to
the API (/internal/events), which passes it on to the screens.
"""
from __future__ import annotations

import logging
import math
import signal
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass

import requests
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from karaoke.core.config import Settings
from karaoke.core.db import make_engine, make_sessionmaker, migrate, transaction
from karaoke.core.models import (
    AWAITING_DECISION,
    FAILED,
    JOB_DONE,
    JOB_FAILED,
    JOB_PENDING,
    JOB_RUNNING,
    PENDING,
    PLAYING,
    PROCESSING,
    QUEUED,
    READY,
    REMOVED,
    Job,
    QueueEntry,
    Room,
    Song,
    utcnow,
)
from karaoke.core.songs import hold_for_decision, record, sync_from_manifest
from karaoke.core.storage import Manifest, SongFolder
from karaoke.pipeline.process import Stage, process

log = logging.getLogger("karaoke.worker")

Notify = Callable[[dict], None]


def http_notifier(api_url: str) -> Notify:
    def notify(event: dict) -> None:
        try:
            requests.post(f"{api_url}/internal/events", json=event, timeout=2).raise_for_status()
        except requests.RequestException as exc:  # the database already has it; the screens catch up on reload
            log.warning("evento %s não chegou à API: %s", event["type"], exc)

    return notify


def next_job(session: Session) -> Job | None:
    """The pending job whose song is nearest to playing; ties, and jobs no queue waits for, by creation order."""
    jobs = session.scalars(
        select(Job).where(Job.status == JOB_PENDING).order_by(Job.created_at, Job.id)
    ).all()
    if not jobs:
        return None
    waiting = session.execute(
        select(QueueEntry.room_id, QueueEntry.video_id)
        .join(Room, Room.id == QueueEntry.room_id)
        .where(Room.is_active, QueueEntry.status.in_((QUEUED, PLAYING)))
        .order_by(QueueEntry.room_id, QueueEntry.position)
    ).all()
    turns: dict[str, float] = {}  # video_id -> how many entries play before its first one
    ahead: dict[int, int] = {}  # room_id -> entries seen so far in that room
    for room_id, video_id in waiting:
        turns[video_id] = min(turns.get(video_id, math.inf), ahead.get(room_id, 0))
        ahead[room_id] = ahead.get(room_id, 0) + 1
    order = {job.id: i for i, job in enumerate(jobs)}
    return min(jobs, key=lambda job: (turns.get(job.video_id, math.inf), order[job.id]))


def claim_next(factory: sessionmaker[Session]) -> Job | None:
    with transaction(factory) as session:
        job = next_job(session)
        if job is None:
            return None
        job.status, job.started_at, job.attempts, job.error = JOB_RUNNING, utcnow(), job.attempts + 1, None
        song = session.get(Song, job.video_id)
        if song.status != REMOVED:
            song.status, song.error = PROCESSING, None
        return job


def reset_interrupted(factory: sessionmaker[Session]) -> None:
    """A job left running belonged to a worker that died; it goes back to the queue and resumes from the manifest."""
    with transaction(factory) as session:
        stale = session.scalars(select(Job.video_id).where(Job.status == JOB_RUNNING)).all()
        if stale:
            log.info("retomando jobs interrompidos: %s", ", ".join(stale))
        session.execute(update(Job).where(Job.status == JOB_RUNNING).values(status=JOB_PENDING))
        session.execute(update(Song).where(Song.status == PROCESSING).values(status=PENDING))


@dataclass
class Worker:
    settings: Settings
    factory: sessionmaker[Session]
    notify: Notify
    stages: Callable[[], list[Stage]] | None = None  # tests swap the real pipeline for stand-ins

    def run_job(self, job: Job) -> str:
        log.info("job %s: %s", job.id, job.video_id)
        redo = job.options.get("redo") or []
        if redo:
            Manifest.load(SongFolder(self.settings.media_dir, job.video_id)).redo(*redo)

        def on_stage(name: str, index: int, total: int) -> None:
            progress = index / total
            with transaction(self.factory) as session:
                row = session.get(Job, job.id)
                row.stage, row.progress = name, progress
                song = session.get(Song, job.video_id)
                song.stage = name
                sync_from_manifest(song, self.settings)  # title and artist show up as soon as the metadata stage ends
            self.notify({"type": "song.progress", "video_id": job.video_id, "stage": name,
                         "progress": round(progress * 100)})

        try:
            status = process(
                job.video_id,
                self.settings,
                transcribe=bool(job.options.get("transcribe")),
                stages=self.stages() if self.stages else None,
                on_stage=on_stage,
            )
            error = None
        except Exception as exc:
            log.exception("job %s falhou", job.id)
            # messages meant for people (a video too long) go as they are; the rest carry the exception's name
            status, error = FAILED, str(exc) if getattr(exc, "user_facing", False) else f"{type(exc).__name__}: {exc}"
        self.finish(job, status, error)
        return status

    def finish(self, job: Job, status: str, error: str | None) -> None:
        with transaction(self.factory) as session:
            row = session.get(Job, job.id)
            song = session.get(Song, job.video_id)
            sync_from_manifest(song, self.settings)
            row.finished_at = utcnow()
            row.status = JOB_FAILED if status == FAILED else JOB_DONE
            row.error = error
            if status == READY:
                row.progress = 1.0
            removed = song.status == REMOVED  # removed while it ran: the files stay, the removal stands
            song.stage = None
            if status == READY:
                event = {"type": "song.ready", "video_id": song.video_id}
                if not removed:
                    song.status, song.error, song.ready_at = READY, None, utcnow()
                record(session, song.video_id, "ready")
            elif status == AWAITING_DECISION:
                if not removed:
                    song.status = AWAITING_DECISION
                entries = hold_for_decision(session, song.video_id)
                event = {"type": "song.lyrics_missing", "video_id": song.video_id, "entries": entries}
                record(session, song.video_id, "lyrics_missing")
            else:
                if not removed:
                    song.status, song.error = FAILED, error
                event = {"type": "song.failed", "video_id": song.video_id, "error": error}  # the job keeps it
        log.info("job %s: %s", job.id, status)
        self.notify(event)

    def run(self, poll_s: float = 2.0, stop_when_idle: bool = False) -> None:
        reset_interrupted(self.factory)
        log.info("worker pronto")
        while True:
            job = claim_next(self.factory)
            if job is not None:
                self.run_job(job)
            elif stop_when_idle:
                return
            else:
                time.sleep(poll_s)


def main(settings: Settings) -> None:
    # `docker compose stop` sends SIGTERM: exit through SystemExit, so the manifest records the interruption
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    engine = make_engine(settings.database_url)
    migrate(engine)
    Worker(settings, make_sessionmaker(engine), http_notifier(settings.api_url)).run()
