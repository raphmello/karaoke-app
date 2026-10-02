"""The job loop, with stand-in stages: priority, the outcome of each job and what reaches the API."""
from sqlalchemy import select

from karaoke.core.db import transaction
from karaoke.core.models import (
    AWAITING_DECISION,
    FAILED,
    JOB_DONE,
    JOB_FAILED,
    JOB_PENDING,
    JOB_RUNNING,
    PENDING,
    PROCESSING,
    QUEUED,
    READY,
    Job,
    QueueEntry,
    Room,
    Song,
)
from karaoke.core.songs import add_to_queue
from karaoke.pipeline.process import Stage, lyrics_gate
from karaoke.worker.main import Worker, claim_next, next_job, reset_interrupted

A, B, C = "aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"


class Pipeline:
    """Stand-in stages that record what ran."""

    def __init__(self, lyrics_found=True, fail_at=None):
        self.lyrics_found, self.fail_at = lyrics_found, fail_at
        self.calls: list[str] = []

    def stages(self) -> list[Stage]:
        def stage(name):
            def run(ctx):
                self.calls.append(name)
                if name == self.fail_at:
                    raise RuntimeError(f"{name} broke")
                if name == "metadata":
                    return {"title": "Artista - Música", "duration_s": 200.0}
                if name == "lyrics":
                    return {"found": self.lyrics_found, "source": "lrclib", "artist": "Artista", "track": "Música"}
                if name == "key":
                    return {"key": "A", "scale": "minor"}
                return {}

            return Stage(name, run, stop=lyrics_gate if name == "lyrics" else (lambda ctx: None))

        return [stage(n) for n in ("metadata", "lyrics", "download", "separation", "alignment", "key", "encode")]


def worker(settings, db, pipeline):
    events = []
    return Worker(settings, db, events.append, stages=pipeline.stages), events


def add(db, settings, room, video, guest_id=None):
    with transaction(db) as session:
        return add_to_queue(session, settings, room, video, guest_id=guest_id, singer_name=None)


def get(db, model, key):
    with db() as session:
        return session.get(model, key)


def test_the_song_nearest_to_playing_goes_first(db, settings, room):
    for video in (A, B, C):  # jobs created in this order...
        with transaction(db) as session:
            session.add(Song(video_id=video))
            session.flush()
            session.add(Job(video_id=video))
    add(db, settings, room, C)  # ...but the queue wants C, then A
    add(db, settings, room, A)

    claimed = [claim_next(db).video_id for _ in range(3)]
    assert claimed == [C, A, B]  # B waits for no one: last, by creation order
    assert claim_next(db) is None


def test_queues_of_closed_rooms_do_not_count(db, settings, room):
    with transaction(db) as session:
        old = Room(code="OLD234", host_pin_hash="x", is_active=False)
        session.add(old)
    add(db, settings, room, A)
    add(db, settings, old, B)  # B's job is newer, and only a closed room wants it
    with db() as session:
        assert next_job(session).video_id == A


def test_a_job_with_lyrics_ends_ready(db, settings, room):
    add(db, settings, room, A)
    pipeline = Pipeline()
    work, events = worker(settings, db, pipeline)

    work.run(stop_when_idle=True)

    song = get(db, Song, A)
    assert song.status == READY and song.stage is None and song.ready_at is not None
    assert (song.title, song.artist, song.original_key, song.lyrics_source) == (
        "Artista - Música", "Artista", "A minor", "lrclib")
    job = get(db, Job, 1)
    assert (job.status, job.progress, job.attempts) == (JOB_DONE, 1.0, 1)
    assert [e["type"] for e in events] == ["song.progress"] * 7 + ["song.ready"]
    assert events[2] == {"type": "song.progress", "video_id": A, "stage": "download", "progress": 29}


def test_missing_lyrics_hold_the_song_and_its_entries(db, settings, room):
    first = add(db, settings, room, A)
    second = add(db, settings, room, A)
    pipeline = Pipeline(lyrics_found=False)
    work, events = worker(settings, db, pipeline)

    work.run(stop_when_idle=True)

    assert pipeline.calls == ["metadata", "lyrics"]  # nothing was downloaded
    assert get(db, Song, A).status == AWAITING_DECISION
    assert get(db, Song, A).lyrics_source == "nenhuma"
    assert {get(db, QueueEntry, first.id).status, get(db, QueueEntry, second.id).status} == {AWAITING_DECISION}
    assert get(db, Job, 1).status == JOB_DONE
    assert events[-1] == {"type": "song.lyrics_missing", "video_id": A, "entries": [first.id, second.id]}


def test_a_failed_job_marks_the_song_failed(db, settings, room):
    entry = add(db, settings, room, A)
    work, events = worker(settings, db, Pipeline(fail_at="separation"))

    work.run(stop_when_idle=True)

    assert get(db, Song, A).status == FAILED
    assert get(db, Song, A).error == "RuntimeError: separation broke"
    assert get(db, Job, 1).status == JOB_FAILED
    assert get(db, QueueEntry, entry.id).status == QUEUED  # the entry shows the error; the host may retry
    assert events[-1] == {"type": "song.failed", "video_id": A, "error": "RuntimeError: separation broke"}


def test_an_accepted_transcription_resumes_after_the_lyrics(db, settings, room):
    add(db, settings, room, A)
    work, _ = worker(settings, db, Pipeline(lyrics_found=False))
    work.run(stop_when_idle=True)
    with transaction(db) as session:
        session.add(Job(video_id=A, options={"transcribe": True}))

    pipeline = Pipeline(lyrics_found=False)
    work, _ = worker(settings, db, pipeline)
    work.run(stop_when_idle=True)

    assert pipeline.calls == ["download", "separation", "alignment", "key", "encode"]
    assert get(db, Song, A).status == READY


def test_redo_runs_the_stage_again(db, settings, room):
    add(db, settings, room, A)
    work, _ = worker(settings, db, Pipeline(lyrics_found=False))
    work.run(stop_when_idle=True)
    with transaction(db) as session:
        session.add(Job(video_id=A, options={"redo": ["lyrics"]}))

    pipeline = Pipeline(lyrics_found=True)  # the lyrics showed up in LRCLIB since
    work, _ = worker(settings, db, pipeline)
    work.run(stop_when_idle=True)

    assert pipeline.calls == ["lyrics", "download", "separation", "alignment", "key", "encode"]
    assert get(db, Song, A).status == READY


def test_a_job_left_running_by_a_dead_worker_goes_back_to_the_queue(db, settings, room):
    add(db, settings, room, A)
    job = claim_next(db)
    assert get(db, Job, job.id).status == JOB_RUNNING and get(db, Song, A).status == PROCESSING

    reset_interrupted(db)

    assert get(db, Job, job.id).status == JOB_PENDING and get(db, Song, A).status == PENDING
    with db() as session:
        assert session.scalars(select(Job.id).where(Job.status == JOB_PENDING)).all() == [job.id]
