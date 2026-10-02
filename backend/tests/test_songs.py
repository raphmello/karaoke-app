"""Adding to the queue (the table "Ao adicionar uma música à fila"), the job guarantees and rebuild-index."""
import threading

import pytest
from helpers import write_manifest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from karaoke.core.db import transaction
from karaoke.core.models import (
    AWAITING_DECISION,
    JOB_DONE,
    PENDING,
    QUEUED,
    READY,
    REMOVED,
    Job,
    QueueEntry,
    Song,
    SongEvent,
)
from karaoke.core.songs import add_to_queue, ensure_job, rebuild_index, sync_from_manifest

VIDEO = "dQw4w9WgXcQ"
READY_STAGES = {
    "metadata": {"title": "Rick Astley - Never Gonna Give You Up", "channel": "Rick Astley", "duration_s": 213,
                 "thumbnail_url": "https://i.ytimg.com/vi/x/hqdefault.jpg", "artist": None, "track": None},
    "lyrics": {"found": True, "source": "lrclib", "artist": "Rick Astley", "track": "Never Gonna Give You Up"},
    "language": {"language": "en"},
    "alignment": {"mode": "lrc_skeleton", "language": "en"},
    "key": {"key": "Ab", "scale": "major", "strength": 0.8},
    "encode": {},
}
NO_LYRICS = {"metadata": READY_STAGES["metadata"], "lyrics": {"found": False}}


def add(db, settings, room, video=VIDEO, guest_id=None, semitones=0) -> QueueEntry:
    with transaction(db) as session:
        return add_to_queue(session, settings, room, video, guest_id=guest_id, singer_name="Ana", semitones=semitones)


def count(db, model, *where) -> int:
    with db() as session:
        return session.scalar(select(func.count()).select_from(model).where(*where))


def song(db, video=VIDEO) -> Song:
    with db() as session:
        return session.get(Song, video)


def test_the_database_runs_in_wal_mode(db):
    with db() as session:
        assert session.execute(text("PRAGMA journal_mode")).scalar() == "wal"


def test_a_new_video_creates_the_song_and_one_job(db, settings, room):
    entry = add(db, settings, room, semitones=-2)
    assert entry.status == QUEUED and entry.semitones == -2 and entry.position == 1
    assert song(db).status == PENDING
    assert count(db, Job) == 1
    assert count(db, SongEvent, SongEvent.kind == "created") == 1


def test_repeats_get_new_entries_but_never_a_second_job(db, settings, room):
    first, second = add(db, settings, room), add(db, settings, room)
    assert (first.position, second.position) == (1, 2)
    assert count(db, QueueEntry) == 2
    assert count(db, Job) == 1


def test_adding_the_same_video_five_times_at_once_creates_one_job(db, settings, room):
    """The phase 2 criterion (docs/ARCHITECTURE.md, roadmap)."""
    start = threading.Barrier(5)
    errors = []

    def add_concurrently():
        try:
            start.wait()
            add(db, settings, room)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=add_concurrently) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert count(db, Song) == 1
    assert count(db, Job) == 1
    assert count(db, QueueEntry) == 5
    with db() as session:
        assert sorted(session.scalars(select(QueueEntry.position))) == [1, 2, 3, 4, 5]


def test_two_equal_active_jobs_are_impossible(db, settings, room):
    add(db, settings, room)
    with pytest.raises(IntegrityError), transaction(db) as session:
        session.add(Job(kind="process", video_id=VIDEO))
    with transaction(db) as session:
        assert not ensure_job(session, VIDEO)


def test_a_finished_job_lets_a_new_one_start(db, settings, room):
    add(db, settings, room)
    with transaction(db) as session:
        session.scalar(select(Job)).status = JOB_DONE
        assert ensure_job(session, VIDEO, {"transcribe": True})
    assert count(db, Job) == 2


def test_a_ready_song_is_ready_at_once(db, settings, room):
    add(db, settings, room)
    with transaction(db) as session:
        session.get(Song, VIDEO).status = READY
        session.scalar(select(Job)).status = JOB_DONE
    entry = add(db, settings, room)
    assert entry.status == QUEUED
    assert count(db, Job) == 1


def test_a_song_waiting_for_the_decision_makes_the_new_entry_wait_too(db, settings, room):
    add(db, settings, room)
    with transaction(db) as session:
        session.get(Song, VIDEO).status = AWAITING_DECISION
    assert add(db, settings, room).status == AWAITING_DECISION


def remove(db):
    with transaction(db) as session:
        row = session.get(Song, VIDEO)
        row.status, row.removed_reason = REMOVED, "transcrição recusada"
        for job in session.scalars(select(Job)):
            job.status = JOB_DONE


def test_a_removed_song_with_its_files_comes_back_ready_without_processing(db, settings, room):
    add(db, settings, room)
    remove(db)
    write_manifest(settings, VIDEO, "ready", READY_STAGES)

    assert add(db, settings, room).status == QUEUED
    restored = song(db)
    assert restored.status == READY and restored.removed_reason is None
    assert count(db, Job) == 1  # only the first one
    assert count(db, SongEvent, SongEvent.kind == "reactivated") == 1


def test_a_removed_song_never_processed_searches_for_lyrics_again(db, settings, room):
    add(db, settings, room)
    remove(db)
    write_manifest(settings, VIDEO, "awaiting_decision", NO_LYRICS)

    add(db, settings, room)
    assert song(db).status == PENDING
    with db() as session:
        job = session.scalar(select(Job).where(Job.status == "pending"))
    assert job.options == {"redo": ["lyrics"]}


def test_sync_copies_what_the_pipeline_learned(db, settings, room):
    add(db, settings, room)
    write_manifest(settings, VIDEO, "ready", READY_STAGES)
    with transaction(db) as session:
        row = session.get(Song, VIDEO)
        sync_from_manifest(row, settings)
    row = song(db)
    assert row.title == "Rick Astley - Never Gonna Give You Up"
    assert (row.artist, row.track) == ("Rick Astley", "Never Gonna Give You Up")  # from the lyrics search
    assert (row.lyrics_source, row.language, row.original_key) == ("lrclib", "en", "Ab major")
    assert row.pipeline_version == 1


def test_rebuild_index_recreates_songs_from_the_manifests(db, settings, room):
    write_manifest(settings, "aaaaaaaaaaa", "ready", READY_STAGES)
    write_manifest(settings, "bbbbbbbbbbb", "awaiting_decision", NO_LYRICS)
    write_manifest(settings, "ccccccccccc", "failed", {"metadata": READY_STAGES["metadata"]})
    (settings.media_dir / "not-a-song").mkdir()
    (settings.media_dir / "not-a-song" / "manifest.json").write_text("{}")

    with transaction(db) as session:
        assert rebuild_index(session, settings) == {"created": 3, "updated": 0}
    assert song(db, "aaaaaaaaaaa").status == READY
    assert song(db, "bbbbbbbbbbb").status == AWAITING_DECISION
    assert song(db, "ccccccccccc").status == PENDING
    with db() as session:
        assert session.scalars(select(Job.video_id)).all() == ["ccccccccccc"]  # unfinished: resumes


def test_rebuild_index_keeps_a_removal(db, settings, room):
    add(db, settings, room)
    remove(db)
    write_manifest(settings, VIDEO, "ready", READY_STAGES)
    with transaction(db) as session:
        assert rebuild_index(session, settings) == {"created": 0, "updated": 1}
    assert song(db).status == REMOVED
    assert song(db).title == "Rick Astley - Never Gonna Give You Up"
