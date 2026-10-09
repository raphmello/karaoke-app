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
    ACTIVE_ENTRY,
    AWAITING_DECISION,
    DONE,
    PENDING,
    PLAYING,
    QUEUED,
    READY,
    REMOVED,
    SKIPPED,
    Guest,
    Job,
    QueueEntry,
    Room,
    Song,
    SongEvent,
    utcnow,
)
from karaoke.core.storage import VIDEO_ID, Manifest, SongFolder, read_json, write_json

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
    known: dict | None = None,
) -> QueueEntry:
    """A new entry every time (repeats are allowed); what it triggers depends on the song's state. `known` is what
    a search already told about the video (title, channel, duration, thumbnail): a new song starts with it instead
    of showing only its id until the pipeline's metadata stage."""
    by = guest_id or HOST
    known = known or {}
    existing = session.get(Song, video_id)
    check_duration(existing.duration_s if existing and existing.duration_s else known.get("duration_s"), settings)
    shown = {k: known[k] for k in ("title", "channel", "duration_s", "thumbnail_url") if known.get(k)}
    # Only the transaction that inserts the song creates its job (INSERT ... ON CONFLICT DO NOTHING).
    inserted = session.execute(
        insert(Song).values(video_id=video_id, status=PENDING, **shown).on_conflict_do_nothing()
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


# --- the queue (phase 4) ---------------------------------------------------------------------------------------

# queue_entries.removed_reason
BY_OWNER, BY_HOST, TRANSCRIPTION_DECLINED = "dono", "host", "transcrição recusada"


class QueueError(Exception):
    """A queue change that the entry's state does not allow (the API answers 409)."""


class TooLong(QueueError):
    """A video longer than the TV can hold (the API answers 422; the pipeline fails the song with this message)."""

    user_facing = True  # the worker records the message as it is, without the exception's name


def check_duration(duration_s: float | None, settings: Settings) -> None:
    if duration_s and duration_s > settings.max_duration_s:
        raise TooLong(
            f"Vídeo longo demais para o karaokê ({round(duration_s / 60)} min; "
            f"o limite é {round(settings.max_duration_s / 60)} min)."
        )


def queue_rows(session: Session, room: Room) -> list[tuple[QueueEntry, Song, str | None]]:
    """The room's active entries in order, with each song and the owner's nickname."""
    return list(
        session.execute(
            select(QueueEntry, Song, Guest.nickname)
            .join(Song, Song.video_id == QueueEntry.video_id)
            .outerjoin(Guest, Guest.id == QueueEntry.guest_id)
            .where(QueueEntry.room_id == room.id, QueueEntry.status.in_(ACTIVE_ENTRY))
            .order_by(QueueEntry.position)
        ).all()
    )


def remove_entry(session: Session, entry: QueueEntry, reason: str) -> bool:
    """Logical removal: the row stays, out of the queue. True when the entry was playing (the TV must skip it)."""
    if entry.status not in ACTIVE_ENTRY:
        raise QueueError("Esta entrada já saiu da fila.")
    was_playing = entry.status == PLAYING
    entry.status, entry.removed_reason, entry.ended_at = REMOVED, reason, utcnow()
    return was_playing


def answer_transcription(session: Session, entry: QueueEntry, accept: bool, by: str) -> None:
    """The owner's (or the host's) answer to "transcrever?". Yes: one job transcribes, and every entry of the video
    goes back to waiting for it. No: this entry leaves the queue; with no active entry left, the song is removed and
    nothing is downloaded."""
    song = session.get(Song, entry.video_id)
    if entry.status != AWAITING_DECISION or song.status != AWAITING_DECISION:
        raise QueueError("Esta música não está esperando essa resposta.")
    if accept:
        song.status, song.error = PENDING, None
        ensure_job(session, song.video_id, {"transcribe": True})
        session.execute(
            update(QueueEntry)
            .where(QueueEntry.video_id == song.video_id, QueueEntry.status == AWAITING_DECISION)
            .values(status=QUEUED)
        )
        record(session, song.video_id, "transcription_accepted", by)
        return
    remove_entry(session, entry, TRANSCRIPTION_DECLINED)
    record(session, song.video_id, "transcription_declined", by)
    session.flush()
    still_waiting = session.scalar(
        select(func.count()).select_from(QueueEntry).where(
            QueueEntry.video_id == song.video_id, QueueEntry.status.in_(ACTIVE_ENTRY)
        )
    )
    if not still_waiting:
        song.status, song.removed_at, song.removed_reason = REMOVED, utcnow(), TRANSCRIPTION_DECLINED
        record(session, song.video_id, "removed", by, {"reason": TRANSCRIPTION_DECLINED})


def close_rooms(session: Session, new_room: Room, move_queue: bool) -> list[int]:
    """The rooms open until now close. The entry that was playing is done (the TV finishes it); with `move_queue`
    the entries still waiting go to the new room, in order. Their guest_id stays, so the history keeps who added
    them; the guests come back as new guests of the new room, so only the host can remove them. Returns the ids
    of the rooms closed."""
    closing = list(session.scalars(select(Room).where(Room.is_active, Room.id != new_room.id).order_by(Room.id)))
    for room in closing:
        room.is_active = False
        for entry, _, _ in queue_rows(session, room):
            if entry.status == PLAYING:
                entry.status, entry.ended_at = DONE, utcnow()
            elif move_queue:
                entry.room_id = new_room.id
    if move_queue:
        session.flush()
        for position, (entry, _, _) in enumerate(queue_rows(session, new_room), start=1):
            entry.position = position
    return [room.id for room in closing]


def move_entry(session: Session, room: Room, entry: QueueEntry, index: int) -> None:
    """Put the entry at `index` (0 = first) among the room's active entries, and renumber them all. The entry that
    is playing keeps its place, and nothing goes above it."""
    if entry.status == PLAYING:
        raise QueueError("A música que está tocando não muda de lugar na fila.")
    entries = [e for e, _, _ in queue_rows(session, room) if e.id != entry.id]
    first = sum(1 for e in entries if e.status == PLAYING)  # below what is playing
    entries.insert(max(first, min(index, len(entries))), entry)
    for position, item in enumerate(entries, start=1):
        item.position = position


def set_playing(session: Session, room: Room, entry_id: int | None) -> bool:
    """What the TV reports in player.state. When it reports another entry, or none, the one that was playing is
    done. Returns True when the queue changed."""
    playing = session.scalar(
        select(QueueEntry).where(QueueEntry.room_id == room.id, QueueEntry.status == PLAYING)
    )
    if playing is not None and playing.id == entry_id:
        return False
    changed = False
    if playing is not None:
        playing.status, playing.ended_at = DONE, utcnow()
        changed = True
    if entry_id is not None:
        entry = session.get(QueueEntry, entry_id)
        if entry is not None and entry.room_id == room.id and entry.status == QUEUED:
            entry.status, entry.started_at = PLAYING, utcnow()
            changed = True
    return changed


def skip_playing(session: Session, room: Room) -> bool:
    """The host skips the song that is playing; between songs, during the countdown, the one about to start (the
    first entry in the queue whose song is ready, as the TV picks it). True when something was skipped."""
    target = session.scalar(
        select(QueueEntry).where(QueueEntry.room_id == room.id, QueueEntry.status == PLAYING)
    ) or next((e for e, song, _ in queue_rows(session, room) if e.status == QUEUED and song.status == READY), None)
    if target is None:
        return False
    target.status, target.ended_at = SKIPPED, utcnow()
    return True


# --- the host's library (phase 5) ---------------------------------------------------------------------------------

# The `process` job's stages, in order (karaoke.pipeline.process.default_stages), and what each one reads.
STAGES = ("metadata", "lyrics", "download", "separation", "language", "alignment", "key", "encode")
NEEDS = {
    "lyrics": {"metadata"},
    "separation": {"download"},
    "language": {"lyrics"},
    "alignment": {"lyrics", "language", "separation"},
    "key": {"separation"},
    "encode": {"separation"},
}


def with_dependents(stages: set[str]) -> list[str]:
    """The stages asked for plus every stage that reads their output, in pipeline order: redoing the separation
    without the alignment would leave words timed against the old voice."""
    redo = set(stages)
    for stage in STAGES:
        if NEEDS.get(stage, set()) & redo:
            redo.add(stage)
    return [stage for stage in STAGES if stage in redo]


def reprocess(session: Session, song: Song, stages: list[str]) -> list[str]:
    """A job that redoes the chosen stages (and those that depend on them). No stages: the job resumes from the
    first unfinished stage, which is how a failed song is tried again."""
    unknown = set(stages) - set(STAGES)
    if unknown:
        raise QueueError(f"Etapas desconhecidas: {', '.join(sorted(unknown))}.")
    if song.status == REMOVED:
        raise QueueError("A música está removida. Desfaça a remoção antes.")
    redo = with_dependents(set(stages))
    if not ensure_job(session, song.video_id, {"redo": redo} if redo else None):
        raise QueueError("Esta música já está sendo processada.")
    song.status, song.error = PENDING, None
    return redo


def replace_lyrics(session: Session, settings: Settings, song: Song, text: str) -> None:
    """The host pastes lyrics: LRC (with [mm:ss] times) or plain text. Only the language and the alignment run
    again; a song that was waiting for the transcription answer goes on to download, with these lyrics."""
    from karaoke.pipeline.lyrics import parse_lrc

    if song.status == REMOVED:
        raise QueueError("A música está removida. Desfaça a remoção antes.")
    synced = parse_lrc(text)
    lines = synced or [{"t": None, "text": line.strip()} for line in text.splitlines() if line.strip()]
    if not any(line["text"] for line in lines):
        raise QueueError("A letra está vazia.")
    # The job first: if one is already running, nothing on disk changes under it.
    if not ensure_job(session, song.video_id, {"redo": ["language", "alignment"]}):
        raise QueueError("Esta música já está sendo processada; troque a letra quando o job terminar.")
    folder = SongFolder(settings.media_dir, song.video_id)
    write_json(folder.lyrics_source, {"source": "manual", "synced": bool(synced), "lines": lines})
    manifest = Manifest.load(folder)
    previous = manifest.info("lyrics")
    manifest.complete("lyrics", {
        "found": True, "source": "manual", "synced": bool(synced),
        "lines": sum(1 for line in lines if line["text"]),
        "artist": previous.get("artist"), "track": previous.get("track"),
    })
    if song.status == AWAITING_DECISION:
        session.execute(
            update(QueueEntry)
            .where(QueueEntry.video_id == song.video_id, QueueEntry.status == AWAITING_DECISION)
            .values(status=QUEUED)
        )
    song.status, song.error, song.lyrics_source = PENDING, None, "manual"


def remove_song(session: Session, song: Song, by: str) -> None:
    """Logical removal from the library: the row, the files and the history stay. Its entries waiting in the queue
    leave it too; one that is playing finishes."""
    if song.status == REMOVED:
        raise QueueError("A música já está removida.")
    song.status, song.removed_at, song.removed_reason = REMOVED, utcnow(), BY_HOST
    session.execute(
        update(QueueEntry)
        .where(QueueEntry.video_id == song.video_id, QueueEntry.status.in_((QUEUED, AWAITING_DECISION)))
        .values(status=REMOVED, removed_reason=BY_HOST, ended_at=utcnow())
    )
    record(session, song.video_id, "removed", by, {"reason": BY_HOST})


def restore_song(session: Session, settings: Settings, song: Song, by: str) -> None:
    if song.status != REMOVED:
        raise QueueError("A música não está removida.")
    reactivate(session, settings, song, by)


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
