"""Songs, jobs and queue entries: the rules of "Ao adicionar uma música à fila" (docs/ARCHITECTURE.md, pipeline).

Shared by the API (adding to the queue), the worker (finishing a job) and the CLI (rebuild-index). Every function
runs inside the caller's transaction.
"""
from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from karaoke.core.config import Settings
from karaoke.core.models import (
    AWAITING_DECISION,
    PENDING,
    QUEUED,
    READY,
    REMOVED,
    Job,
    QueueEntry,
    Room,
    Song,
    SongEvent,
    utcnow,
)
from karaoke.core.storage import VIDEO_ID, Manifest, SongFolder, read_json

HOST = "host"  # song_events.guest_id when the host did it


def record(session: Session, video_id: str, kind: str, by: str | None = None, details: dict | None = None) -> None:
    session.add(SongEvent(video_id=video_id, kind=kind, guest_id=by, details=details))


def ensure_job(session: Session, video_id: str, options: dict | None = None) -> bool:
    """Create a `process` job unless one is already pending or running; True when this call created it."""
    created = session.execute(
        insert(Job).values(kind="process", video_id=video_id, options=options or {}).on_conflict_do_nothing()
    )
    return created.rowcount == 1


def add_to_queue(
    session: Session,
    settings: Settings,
    room: Room,
    video_id: str,
    *,
    guest_id: str | None,
    singer_name: str | None,
    semitones: int = 0,
) -> QueueEntry:
    """A new entry every time (repeats are allowed); what it triggers depends on the song's state."""
    by = guest_id or HOST
    # Only the transaction that inserts the song creates its job (INSERT ... ON CONFLICT DO NOTHING).
    inserted = session.execute(
        insert(Song).values(video_id=video_id, status=PENDING).on_conflict_do_nothing()
    ).rowcount == 1
    song = session.get(Song, video_id)
    if inserted:
        record(session, video_id, "created", by)
        ensure_job(session, video_id)
    elif song.status == REMOVED:
        reactivate(session, settings, song, by)

    last = session.scalar(select(func.max(QueueEntry.position)).where(QueueEntry.room_id == room.id))
    entry = QueueEntry(
        room_id=room.id,
        video_id=video_id,
        guest_id=guest_id,
        singer_name=singer_name,
        semitones=semitones,
        position=(last or 0) + 1,
        status=AWAITING_DECISION if song.status == AWAITING_DECISION else QUEUED,
    )
    session.add(entry)
    session.flush()
    return entry


def reactivate(session: Session, settings: Settings, song: Song, by: str) -> None:
    """A removed song comes back. With its files complete it is ready at once; otherwise processing resumes, and
    a song whose transcription was declined searches for lyrics again."""
    manifest = Manifest.load(SongFolder(settings.media_dir, song.video_id))
    song.removed_at = song.removed_reason = None
    if manifest.status == "ready":
        song.status = READY
    else:
        song.status, song.error = PENDING, None
        lyrics_missing = manifest.done("lyrics") and not manifest.info("lyrics").get("found")
        ensure_job(session, song.video_id, {"redo": ["lyrics"]} if lyrics_missing else None)
    record(session, song.video_id, "reactivated", by, {"status": song.status})


def hold_for_decision(session: Session, video_id: str) -> list[int]:
    """The song has no lyrics: its waiting entries wait for the owner's answer too. Returns their ids."""
    entries = session.scalars(
        update(QueueEntry)
        .where(QueueEntry.video_id == video_id, QueueEntry.status == QUEUED)
        .values(status=AWAITING_DECISION)
        .returning(QueueEntry.id)
    ).all()
    return list(entries)


def sync_from_manifest(song: Song, settings: Settings) -> Manifest:
    """Copy what the pipeline learned (metadata, lyrics, language, key) from manifest.json into the row."""
    folder = SongFolder(settings.media_dir, song.video_id)
    manifest = Manifest.load(folder)
    meta, lyrics, alignment = manifest.info("metadata"), manifest.info("lyrics"), manifest.info("alignment")
    for field in ("title", "channel", "duration_s", "thumbnail_url"):
        if meta.get(field) is not None:
            setattr(song, field, meta[field])
    song.artist = meta.get("artist") or lyrics.get("artist") or song.artist
    song.track = meta.get("track") or lyrics.get("track") or song.track
    if alignment.get("mode") == "transcription":
        song.lyrics_source = "transcrita"
    elif lyrics.get("found"):
        song.lyrics_source = lyrics["source"]
    elif manifest.done("lyrics"):
        song.lyrics_source = "nenhuma"
    song.language = alignment.get("language") or manifest.info("language").get("language") or song.language
    key = manifest.info("key")
    if key.get("key"):
        song.original_key = f"{key['key']} {key['scale']}"
    song.alignment_confidence = mean_confidence(folder) if manifest.done("alignment") else None
    song.pipeline_version = manifest.data.get("pipeline_version")
    return manifest


def mean_confidence(folder: SongFolder) -> float | None:
    aligned = read_json(folder.aligned) or {}
    scores = [word["c"] for line in aligned.get("lines", []) for word in line["words"] if word.get("c") is not None]
    return round(sum(scores) / len(scores), 3) if scores else None


def rebuild_index(session: Session, settings: Settings) -> dict[str, int]:
    """Recreate the `songs` rows from the manifests in media/. Existing rows keep their status (a removal is
    recorded only in the database); new rows take the manifest's, and unfinished songs get a job to resume."""
    counts = {"created": 0, "updated": 0}
    for path in sorted(settings.media_dir.glob("*/manifest.json")):
        video_id = path.parent.name
        if not VIDEO_ID.match(video_id):
            continue
        song = session.get(Song, video_id)
        if song is None:
            song = Song(video_id=video_id, status=PENDING)
            session.add(song)
            session.flush()  # the job and the event point at it
            manifest = sync_from_manifest(song, settings)
            if manifest.status == "ready":
                song.status, song.ready_at = READY, utcnow()
            elif manifest.status == "awaiting_decision":
                song.status = AWAITING_DECISION
            else:
                ensure_job(session, video_id)
            record(session, video_id, "created", None, {"by": "rebuild-index"})
            counts["created"] += 1
        else:
            sync_from_manifest(song, settings)
            counts["updated"] += 1
    return counts
