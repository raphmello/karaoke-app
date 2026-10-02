"""REST routes and the room's WebSocket (docs/ARCHITECTURE.md, "API REST e eventos em tempo real").

Each route runs in one short transaction (karaoke.core.db): it resolves the caller from the cookies, checks the
permission with `can()` and answers after the commit; then the screens hear of it through the hub. The YouTube
search runs outside any transaction.
"""
from __future__ import annotations

import logging
import secrets
import shutil
import uuid
from typing import Annotated

import anyio
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from karaoke.api import deps
from karaoke.api.realtime import Connection, Hub
from karaoke.api.schemas import (
    ActiveRoomOut,
    DiskOut,
    EventIn,
    GuestOut,
    JobOut,
    JoinIn,
    LoginIn,
    LyricsIn,
    PlayerValueIn,
    QueueEntryIn,
    QueueEntryOut,
    QueueEntryPatch,
    ReprocessIn,
    ReprocessOut,
    RoomIn,
    RoomOut,
    SearchResult,
    SongEventOut,
    SongOut,
    TranscriptionIn,
)
from karaoke.core.auth import GUEST_COOKIE, HOST_COOKIE, hash_pin, new_guest_token, pin_matches
from karaoke.core.config import Settings
from karaoke.core.db import transaction
from karaoke.core.models import (
    AWAITING_DECISION,
    PLAYING,
    READY,
    REMOVED,
    Guest,
    Job,
    QueueEntry,
    Room,
    Song,
    SongEvent,
)
from karaoke.core.permissions import Action, Actor, can
from karaoke.core.songs import (
    BY_HOST,
    BY_OWNER,
    HOST,
    QueueError,
    add_to_queue,
    answer_transcription,
    move_entry,
    queue_rows,
    remove_entry,
    remove_song,
    replace_lyrics,
    reprocess,
    restore_song,
    skip_playing,
)
from karaoke.core.storage import VIDEO_ID

log = logging.getLogger("karaoke.api")

api = APIRouter(prefix="/api")
internal = APIRouter(prefix="/internal")
sockets = APIRouter()

Sessions = Annotated[sessionmaker[Session], Depends(deps.sessions)]
AppSettings = Annotated[Settings, Depends(deps.settings)]

GUEST_COOKIE_AGE = 7 * 24 * 3600  # the room's code changes every night anyway
HOST_COOKIE_AGE = 24 * 3600
ROOM_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I, so a code read aloud still works


# --- songs ---------------------------------------------------------------------------------------------------------

@api.get("/search")
def search(
    request: Request, db: Sessions, q: Annotated[str, Query(min_length=1, max_length=200)]
) -> list[SearchResult]:
    with transaction(db) as session:
        deps.require_actor(request, session)
    results = request.app.state.search(q)
    with transaction(db) as session:
        ids = [r["video_id"] for r in results]
        ready = set(session.scalars(select(Song.video_id).where(Song.video_id.in_(ids), Song.status == READY)))
    return [SearchResult(**r, in_library=r["video_id"] in ready) for r in results]


@api.get("/songs/{video_id}")
def song(request: Request, db: Sessions, video_id: str) -> SongOut:
    with transaction(db) as session:
        deps.require_actor(request, session)
        row = session.get(Song, video_id) if VIDEO_ID.match(video_id) else None
        if row is None:
            raise HTTPException(404, "Música não encontrada.")
        return SongOut.of(row)


@api.get("/library")
def library(
    request: Request, db: Sessions, q: Annotated[str | None, Query(max_length=200)] = None, removed: bool = False
) -> list[SongOut]:
    """The songs that play right away. Removed ones stay in the database but out of the library; `removed=true`
    lists them instead, for the host to restore."""
    with transaction(db) as session:
        actor = deps.require_actor(request, session)
        if removed and not can(actor, Action.RESTORE_SONG):
            raise HTTPException(403, "Só o host vê as músicas removidas.")
        query = select(Song).where(Song.status == (REMOVED if removed else READY))
        for word in (q or "").split():
            pattern = f"%{word}%"
            query = query.where(or_(Song.title.ilike(pattern), Song.artist.ilike(pattern), Song.track.ilike(pattern)))
        rows = session.scalars(query.order_by(Song.artist, Song.track, Song.title)).all()
        return [SongOut.of(row) for row in rows]


# --- host and rooms ------------------------------------------------------------------------------------------------

@api.post("/host/login", status_code=204)
def host_login(request: Request, response: Response, body: LoginIn, settings: AppSettings) -> None:
    if not pin_matches(body.pin, settings.host_pin):
        raise HTTPException(401, "PIN incorreto.")
    deps.set_cookie(request, response, HOST_COOKIE, deps.host_signer(request).issue(), HOST_COOKIE_AGE)


@api.post("/rooms", status_code=201)
def open_room(request: Request, db: Sessions, settings: AppSettings, body: RoomIn) -> RoomOut:
    """Opens tonight's room. One active room at a time in v1: the previous one closes, and its QR stops working."""
    with transaction(db) as session:
        deps.require_host(request, session)
        session.execute(update(Room).where(Room.is_active).values(is_active=False))
        taken = set(session.scalars(select(Room.code)))
        code = new_room_code()
        while code in taken:
            code = new_room_code()
        room = Room(code=code, name=body.name, host_pin_hash=hash_pin(settings.host_pin))
        session.add(room)
    log.info("sala %s aberta", code)
    return RoomOut(code=room.code, name=room.name, join_path=f"/j/{room.code}")


@api.get("/rooms/active")
def active(request: Request, db: Sessions, settings: AppSettings) -> ActiveRoomOut:
    """The open room, for the TV: where its queue is and what goes in the QR."""
    with transaction(db) as session:
        deps.require_host(request, session)
        room = session.scalar(select(Room).where(Room.is_active).order_by(Room.id.desc()))
        if room is None:
            raise HTTPException(404, "Nenhuma sala aberta. Abra a sala na tela do host.")
        return ActiveRoomOut(
            code=room.code, name=room.name, join_path=f"/j/{room.code}", public_base_url=settings.public_base_url
        )


def new_room_code() -> str:
    return "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(6))


@api.post("/rooms/{code}/join")
def join(request: Request, response: Response, db: Sessions, code: str, body: JoinIn) -> GuestOut:
    """A phone joins with a nickname and gets an anonymous token in a cookie. Joining again keeps the same guest,
    and with it the ownership of the entries already added."""
    with transaction(db) as session:
        room = deps.active_room(session, code)
        actor = deps.find_actor(request, session)
        if actor and actor.guest and actor.guest.room_id == room.id:
            actor.guest.nickname = body.nickname
            guest = actor.guest
        else:
            token, token_hash = new_guest_token()
            guest = Guest(id=str(uuid.uuid4()), room_id=room.id, nickname=body.nickname, token_hash=token_hash)
            session.add(guest)
            deps.set_cookie(request, response, GUEST_COOKIE, token, GUEST_COOKIE_AGE)
    return GuestOut(id=guest.id, nickname=guest.nickname, room_code=room.code)


# --- queue ---------------------------------------------------------------------------------------------------------

def hub(connection: Request | WebSocket) -> Hub:
    return connection.app.state.hub


def notify(fn, *args) -> None:
    """Run a hub coroutine from a route (routes run in worker threads); always after the transaction committed."""
    anyio.from_thread.run(fn, *args)


def require(actor: Actor, action: Action, entry: QueueEntry | None = None) -> None:
    if not can(actor, action, entry):
        raise HTTPException(403, "Só quem adicionou esta música, ou o host, pode fazer isso.")


def room_entry(session: Session, room: Room, entry_id: int) -> QueueEntry:
    entry = session.get(QueueEntry, entry_id)
    if entry is None or entry.room_id != room.id:
        raise HTTPException(404, "Entrada não encontrada.")
    return entry


@api.get("/rooms/{code}/queue")
def queue(request: Request, db: Sessions, code: str) -> list[QueueEntryOut]:
    with transaction(db) as session:
        room, actor = deps.room_actor(request, session, code)
        return [QueueEntryOut.of(entry, song, nickname, actor) for entry, song, nickname in queue_rows(session, room)]


@api.post("/rooms/{code}/queue", status_code=201)
def add(request: Request, db: Sessions, settings: AppSettings, code: str, body: QueueEntryIn) -> QueueEntryOut:
    with transaction(db) as session:
        room, actor = deps.room_actor(request, session, code)
        require(actor, Action.ADD)
        nickname = actor.guest.nickname if actor.guest else None
        entry = add_to_queue(
            session,
            settings,
            room,
            body.video_id,
            guest_id=actor.owner_id,
            singer_name=body.singer_name or nickname,
            semitones=body.semitones,
            known=request.app.state.search.find(body.video_id),
        )
        out = QueueEntryOut.of(entry, session.get(Song, entry.video_id), nickname, actor)
    notify(hub(request).queue_changed, room.id)
    if entry.status == AWAITING_DECISION:  # the question goes to the new owner too
        notify(hub(request).lyrics_missing, entry.video_id, [entry.id])
    return out


@api.patch("/rooms/{code}/queue/{entry_id}")
def change(request: Request, db: Sessions, code: str, entry_id: int, body: QueueEntryPatch) -> QueueEntryOut:
    """The owner changes the key; the host changes the key and the position."""
    with transaction(db) as session:
        room, actor = deps.room_actor(request, session, code)
        entry = room_entry(session, room, entry_id)
        if body.semitones is not None:
            require(actor, Action.CHANGE_KEY, entry)
            entry.semitones = body.semitones
        if body.position is not None:
            require(actor, Action.REORDER, entry)
            move_entry(session, room, entry, body.position)
        song = session.get(Song, entry.video_id)
        nickname = session.get(Guest, entry.guest_id).nickname if entry.guest_id else None
        out = QueueEntryOut.of(entry, song, nickname, actor)
        playing = entry.status == PLAYING
    notify(hub(request).queue_changed, room.id)
    if playing and body.semitones is not None:
        notify(hub(request).command, room.id, "key", {"semitones": body.semitones})
    return out


@api.delete("/rooms/{code}/queue/{entry_id}", status_code=204)
def remove(request: Request, db: Sessions, code: str, entry_id: int) -> None:
    """Logical removal, by the owner or the host. If it is playing, the TV skips it."""
    with transaction(db) as session:
        room, actor = deps.room_actor(request, session, code)
        entry = room_entry(session, room, entry_id)
        require(actor, Action.REMOVE_ENTRY, entry)
        try:
            was_playing = remove_entry(session, entry, BY_HOST if actor.is_host else BY_OWNER)
        except QueueError as exc:
            raise HTTPException(409, str(exc)) from exc
    notify(hub(request).queue_changed, room.id)
    if was_playing:
        notify(hub(request).command, room.id, "skip")


@api.post("/rooms/{code}/queue/{entry_id}/transcription", status_code=204)
def transcription(request: Request, db: Sessions, code: str, entry_id: int, body: TranscriptionIn) -> None:
    """The answer to "transcrever?": yes transcribes; no takes the entry out of the queue, with nothing downloaded."""
    with transaction(db) as session:
        room, actor = deps.room_actor(request, session, code)
        entry = room_entry(session, room, entry_id)
        require(actor, Action.ANSWER_TRANSCRIPTION, entry)
        try:
            answer_transcription(session, entry, body.accept, actor.owner_id or HOST)
        except QueueError as exc:
            raise HTTPException(409, str(exc)) from exc
    notify(hub(request).queue_changed, None)  # every entry of the video changes, in any room


PLAYER_VALUES = {"guide": (0.0, 100.0), "delay": (-2000.0, 2000.0)}  # % of the guide voice; TV delay in ms


@api.post("/rooms/{code}/player/{action}", status_code=204)
def player(request: Request, db: Sessions, code: str, action: str, body: PlayerValueIn | None = None) -> None:
    """play, pause, skip (between songs: the one about to start); guide and delay with {"value": ...}."""
    if action not in ("play", "pause", "skip", *PLAYER_VALUES):
        raise HTTPException(404, "Ação desconhecida: use play, pause, skip, guide ou delay.")
    fields = None
    if action in PLAYER_VALUES:
        low, high = PLAYER_VALUES[action]
        if body is None or not low <= body.value <= high:
            raise HTTPException(422, f"Informe value entre {low:g} e {high:g}.")
        fields = {"value": body.value}
    with transaction(db) as session:
        room, actor = deps.room_actor(request, session, code)
        require(actor, Action.PLAYER_SETTINGS if fields else Action.PLAYER)
        skipped = action == "skip" and skip_playing(session, room)
    if skipped:
        notify(hub(request).queue_changed, room.id)
    notify(hub(request).command, room.id, action, fields)


@sockets.websocket("/ws/rooms/{code}")
async def room_socket(websocket: WebSocket, code: str, role: str | None = None) -> None:
    """Authenticated by the same cookie as REST. `?role=tv` (host only) marks the TV: it gets player.command and
    reports player.state."""
    db = deps.sessions(websocket)

    def resolve() -> tuple[Room, Actor] | int:
        with transaction(db) as session:
            try:
                return deps.room_actor(websocket, session, code)
            except HTTPException as exc:
                return 4000 + exc.status_code  # 4401 no cookie, 4403 another room, 4404 no such room

    found = await anyio.to_thread.run_sync(resolve)
    await websocket.accept()
    if isinstance(found, int):
        await websocket.close(code=found)
        return
    room, actor = found
    connection = Connection(websocket, room.id, actor, tv=role == "tv" and actor.is_host)
    rooms = hub(websocket)
    rooms.join(connection)
    try:
        await rooms.greet(connection)
        while True:
            message = await websocket.receive_json()
            if isinstance(message, dict) and message.get("type") == "player.state" and connection.tv:
                await rooms.tv_state(room.id, message)
    except (WebSocketDisconnect, ValueError):
        pass
    finally:
        rooms.leave(connection)


# --- the host's library and panel (phase 5) -----------------------------------------------------------------------

def host_song(request: Request, session: Session, video_id: str, action: Action) -> tuple[Actor, Song]:
    actor = deps.require_actor(request, session)
    require(actor, action)
    song = session.get(Song, video_id) if VIDEO_ID.match(video_id) else None
    if song is None:
        raise HTTPException(404, "Música não encontrada.")
    return actor, song


def conflict(fn, *args):
    try:
        return fn(*args)
    except QueueError as exc:
        raise HTTPException(409, str(exc)) from exc


@api.put("/songs/{video_id}/lyrics", status_code=204)
def lyrics(request: Request, db: Sessions, settings: AppSettings, video_id: str, body: LyricsIn) -> None:
    """The host's lyrics (LRC or plain); only the alignment runs again."""
    with transaction(db) as session:
        _, song = host_song(request, session, video_id, Action.REPROCESS)
        conflict(replace_lyrics, session, settings, song, body.text)
    notify(hub(request).queue_changed, None)


@api.post("/songs/{video_id}/reprocess")
def reprocess_song(request: Request, db: Sessions, video_id: str, body: ReprocessIn) -> ReprocessOut:
    with transaction(db) as session:
        _, song = host_song(request, session, video_id, Action.REPROCESS)
        stages = conflict(reprocess, session, song, body.stages)
    notify(hub(request).queue_changed, None)
    return ReprocessOut(stages=stages)


@api.delete("/songs/{video_id}", status_code=204)
def remove_from_library(request: Request, db: Sessions, video_id: str) -> None:
    """Marks the song as removed; the row, the files and the history stay."""
    with transaction(db) as session:
        _, song = host_song(request, session, video_id, Action.REMOVE_SONG)
        conflict(remove_song, session, song, HOST)
    notify(hub(request).queue_changed, None)


@api.post("/songs/{video_id}/restore", status_code=204)
def restore(request: Request, db: Sessions, settings: AppSettings, video_id: str) -> None:
    """Undoes the removal with the files kept, without reprocessing."""
    with transaction(db) as session:
        _, song = host_song(request, session, video_id, Action.RESTORE_SONG)
        conflict(restore_song, session, settings, song, HOST)
    notify(hub(request).queue_changed, None)


@api.get("/songs/{video_id}/history")
def history(request: Request, db: Sessions, video_id: str) -> list[SongEventOut]:
    with transaction(db) as session:
        host_song(request, session, video_id, Action.REPROCESS)
        rows = session.execute(
            select(SongEvent, Guest.nickname)
            .outerjoin(Guest, Guest.id == SongEvent.guest_id)
            .where(SongEvent.video_id == video_id)
            .order_by(SongEvent.id)
        ).all()
        return [
            SongEventOut(
                kind=event.kind,
                by=nickname or ("host" if event.guest_id == HOST else "sistema"),
                details=event.details,
                created_at=event.created_at,
            )
            for event, nickname in rows
        ]


@api.get("/jobs")
def jobs(request: Request, db: Sessions, limit: Annotated[int, Query(ge=1, le=200)] = 50) -> list[JobOut]:
    """The jobs panel: the most recent first."""
    with transaction(db) as session:
        deps.require_host(request, session)
        rows = session.execute(
            select(Job, Song.title).join(Song, Song.video_id == Job.video_id).order_by(Job.id.desc()).limit(limit)
        ).all()
        return [
            JobOut(
                id=job.id, video_id=job.video_id, title=title, status=job.status, stage=job.stage,
                progress=job.progress, attempts=job.attempts, options=job.options, error=job.error,
                created_at=job.created_at, started_at=job.started_at, finished_at=job.finished_at,
            )
            for job, title in rows
        ]


LOW_DISK_BYTES = 10 * 1024**3  # about 150 songs of room left
LOW_DISK_SHARE = 0.10


def folder_bytes(path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.exists() else 0


@api.get("/disk")
def disk(request: Request, db: Sessions, settings: AppSettings) -> DiskOut:
    """The disk panel: ~65 MB per song, and removed songs keep their files."""
    with transaction(db) as session:
        deps.require_host(request, session)
        statuses = dict(session.execute(select(Song.video_id, Song.status)).all())
    usage = shutil.disk_usage(settings.data_dir)
    removed = [video_id for video_id, status in statuses.items() if status == REMOVED]
    return DiskOut(
        total_bytes=usage.total,
        free_bytes=usage.free,
        media_bytes=folder_bytes(settings.media_dir),
        songs=len(statuses),
        removed_songs=len(removed),
        removed_bytes=sum(folder_bytes(settings.media_dir / video_id) for video_id in removed),
        low=usage.free < LOW_DISK_BYTES or usage.free < LOW_DISK_SHARE * usage.total,
    )


# --- worker → API --------------------------------------------------------------------------------------------------

@internal.post("/events", status_code=204)
def worker_event(request: Request, event: EventIn) -> None:
    """Job progress from the worker, passed on to the screens. Not routed by Caddy."""
    log.info("evento %s", event.model_dump())
    notify(hub(request).worker_event, event.model_dump())
