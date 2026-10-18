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

    def __init__(self, lyrics_found=True, fail_at=None, fail_times=None):
        self.lyrics_found, self.fail_at = lyrics_found, fail_at
        self.fail_times = fail_times  # None: fail_at fails every time
        self.calls: list[str] = []

    def stages(self) -> list[Stage]:
        def stage(name):
            def run(ctx):
                self.calls.append(name)
                if name == self.fail_at and (self.fail_times is None or self.calls.count(name) <= self.fail_times):
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
    # the progress clock stays quiet: the events are the stages' own, in order
    return Worker(settings, db, events.append, stages=pipeline.stages, retry_wait_s=0, tick_s=3600), events


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
    download = events[2]
    assert (download["stage"], download["new_stage"]) == ("download", True)
    # metadata and lyrics take ~3% of a song's time: the bar goes by the time, not by counting stages
    assert 0 < download["progress"] < 10 and download["eta_s"] > 60


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


def test_a_download_that_fails_now_and_then_is_tried_again_from_where_it_stopped(db, settings, room):
    add(db, settings, room, A)
    pipeline = Pipeline(fail_at="download", fail_times=2)
    work, events = worker(settings, db, pipeline)

    work.run(stop_when_idle=True)

    assert get(db, Song, A).status == READY
    assert pipeline.calls.count("download") == 3
    assert pipeline.calls.count("metadata") == 1  # the stages already done are not run again
    assert get(db, Job, 1).attempts == 3
    assert not [e for e in events if e["type"] == "song.failed"]


def test_after_three_retries_the_song_fails_once(db, settings, room):
    add(db, settings, room, A)
    pipeline = Pipeline(fail_at="download")
    work, events = worker(settings, db, pipeline)

    work.run(stop_when_idle=True)

    assert pipeline.calls.count("download") == 4  # the first try and three more
    assert get(db, Job, 1).attempts == 4
    assert get(db, Song, A).status == FAILED
    assert [e["type"] for e in events].count("song.failed") == 1


def test_the_retries_wait_between_tries(db, settings, room, monkeypatch):
    from karaoke.worker import main

    waits = []
    monkeypatch.setattr(main.time, "sleep", waits.append)
    add(db, settings, room, A)
    pipeline = Pipeline(fail_at="metadata")
    Worker(settings, db, lambda event: None, stages=pipeline.stages, tick_s=3600).run(stop_when_idle=True)
    assert waits == [3.0, 3.0, 3.0]


def test_the_gpu_stages_are_not_tried_again(db, settings, room):
    add(db, settings, room, A)
    pipeline = Pipeline(fail_at="separation")
    work, _ = worker(settings, db, pipeline)

    work.run(stop_when_idle=True)

    assert pipeline.calls.count("separation") == 1
    assert get(db, Job, 1).attempts == 1


def test_lrclib_down_is_tried_again_with_the_job_and_then_said_for_people(db, settings, room):
    from karaoke.pipeline.lyrics import SITE_DOWN, LyricsSiteDown

    add(db, settings, room, A)
    pipeline = Pipeline()
    runs = []

    def stages() -> list[Stage]:
        def down(ctx):
            runs.append("lyrics")
            raise LyricsSiteDown(SITE_DOWN)

        return [stage if stage.name != "lyrics" else Stage("lyrics", down) for stage in pipeline.stages()]

    Worker(settings, db, lambda event: None, stages=stages, retry_wait_s=0, tick_s=3600).run(stop_when_idle=True)

    assert runs == ["lyrics"] * 4  # the first try and three more, as for a download
    song = get(db, Song, A)
    assert song.status == FAILED and song.error == SITE_DOWN  # no exception's name: a message for people


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


def test_the_title_reaches_the_database_while_the_job_still_runs(db, settings, room):
    add(db, settings, room, A)
    seen = {}

    class Watching(Pipeline):
        def stages(self):
            stages = super().stages()

            def peek(ctx):
                seen["title"] = get(db, Song, A).title  # what the screens show during the separation
                return {}

            return [Stage(s.name, peek, s.stop) if s.name == "separation" else s for s in stages]

    work, _ = worker(settings, db, Watching())
    work.run(stop_when_idle=True)
    assert seen["title"] == "Artista - Música"


def test_a_video_too_long_stops_at_the_metadata_with_a_plain_message(db, settings, room):
    from karaoke.core.songs import check_duration

    add(db, settings, room, A)

    class Long(Pipeline):
        def stages(self):
            stages = super().stages()

            def metadata(ctx):
                self.calls.append("metadata")
                check_duration(1648, ctx.settings)
                return {}

            return [Stage("metadata", metadata), *stages[1:]]

    pipeline = Long()
    work, _ = worker(settings, db, pipeline)
    work.run(stop_when_idle=True)
    assert pipeline.calls == ["metadata"]  # nothing downloaded
    song = get(db, Song, A)
    assert (song.status, song.error) == ("failed", "Vídeo longo demais para o karaokê (27 min; o limite é 10 min).")
