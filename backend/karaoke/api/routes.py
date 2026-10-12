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
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

import anyio
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, sessionmaker
from starlette.websockets import WebSocketDisconnected

from karaoke.api import deps
from karaoke.api.realtime import Connection, Hub
from karaoke.api.schemas import (
    RoomInfoOut,
    RoomTvIn,
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
from karaoke.core.auth import (
    ALL_ROOMS,
    GUEST_COOKIE,
    HOST_COOKIE,
    TV_COOKIE,
    hash_pin,
    new_guest_token,
    pin_matches,
    token_hash,
    verify_pin,
)
from karaoke.core.config import Settings
from karaoke.core.db import transaction
from karaoke.core.models import (
    AWAITING_DECISION,
    PLAYING,
    READY,
    ROOM_LIFETIME,
    REMOVED,
    Guest,
    Job,
    QueueEntry,
    Room,
    Song,
    SongEvent,
    utcnow,
)
from karaoke.core.permissions import Action, Actor, can, tv_token
from karaoke.core.songs import (
    BY_HOST,
    BY_OWNER,
    HOST,
    QueueError,
    TooLong,
    add_to_queue,
    answer_transcription,
    close_room,
    move_entry,
    queue_rows,
    remove_entry,
    remove_song,
    replace_lyrics,
    reprocess,
    restore_song,
    skip_playing,
)
from karaoke.core.storage import VIDEO_ID, SongFolder

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


@api.get("/preview/{video_id}")
def preview(request: Request, db: Sessions, video_id: str) -> StreamingResponse:
    """Hear a video before adding it: its audio from YouTube, passed on with Range so the player can seek."""
    with transaction(db) as session:
        deps.require_actor(request, session)
    if not VIDEO_ID.match(video_id):
        raise HTTPException(404, "Vídeo não encontrado.")
    try:
        upstream = request.app.state.preview.open(video_id, request.headers.get("range"))
    except Exception as exc:  # yt-dlp or YouTube: the screen says the preview is unavailable
        log.warning("prévia de %s falhou: %s", video_id, exc)
        raise HTTPException(502, "Não foi possível tocar a prévia deste vídeo.") from exc
    return StreamingResponse(upstream.body, status_code=upstream.status, headers=upstream.headers)


@api.get("/library")
def library(
    request: Request,
    db: Sessions,
    settings: AppSettings,
    q: Annotated[str | None, Query(max_length=200)] = None,
    removed: bool = False,
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
        return [SongOut.of(row, original_name(settings, row.video_id)) for row in rows]


def original_name(settings: Settings, video_id: str) -> str | None:
    source = SongFolder(settings.media_dir, video_id).source_audio()
    return source.name if source else None


# --- host and rooms ------------------------------------------------------------------------------------------------

def check_pin(request: Request, pin: str, *expected: str) -> int:
    """Which of the expected PINs this is (its index); a wrong one counts against the caller's address."""
    return limited(
        request,
        lambda: next((i for i, candidate in enumerate(expected) if pin_matches(pin, candidate)), None),
        "PIN incorreto.",
    )


@api.post("/host/login", status_code=204)
def host_login(request: Request, response: Response, body: LoginIn, settings: AppSettings) -> None:
    check_pin(request, body.pin, settings.host_pin)
    deps.set_cookie(request, response, HOST_COOKIE, deps.host_signer(request).issue(), HOST_COOKIE_AGE)


@api.post("/host/logout", status_code=204)
def host_logout(request: Request, response: Response) -> None:
    """"Sair do admin" on the TV's menu: the host's cookie goes, the TV's and a guest's stay."""
    deps.clear_cookie(request, response, HOST_COOKIE)


def limited(request: Request, matches: Callable[[], int | None], wrong: str) -> int:
    """Runs a PIN or password check, counting wrong ones against the caller's address. The host's PIN, the TV's and
    the rooms' passwords share the limit, so none of them is a way around it."""
    limiter = request.app.state.login_limiter
    address = deps.client_address(request)
    if wait := limiter.retry_after(address):
        minutes = max(1, round(wait / 60))
        raise HTTPException(
            429,
            f"Muitas tentativas erradas. Tente de novo em {minutes} minuto{'s' if minutes > 1 else ''}.",
            headers={"Retry-After": str(wait)},
        )
    found = matches()
    if found is None:
        limiter.failed(address)
        log.warning("%s vindo de %s", wrong, address)
        raise HTTPException(401, wrong)
    limiter.succeeded(address)
    return found


@api.post("/tv/login", status_code=204)
def tv_login(request: Request, response: Response, body: LoginIn, settings: AppSettings) -> None:
    """The TV's PIN screen. TV_PIN gives a TV cookie for every room; the host's PIN, typed there, gives the host's
    cookie, since the host may do everything."""
    if check_pin(request, body.pin, settings.tv_pin, settings.host_pin) == 0:
        deps.set_cookie(request, response, TV_COOKIE, deps.host_signer(request).issue_tv(ALL_ROOMS), HOST_COOKIE_AGE)
    else:
        deps.set_cookie(request, response, HOST_COOKIE, deps.host_signer(request).issue(), HOST_COOKIE_AGE)


def as_utc(when: datetime) -> datetime:
    """SQLite hands datetimes back without their zone; they are all UTC, and the screens must know it."""
    return when if when.tzinfo else when.replace(tzinfo=UTC)


def room_out(room: Room, session: Session, actor: Actor | None, settings: Settings) -> RoomInfoOut:
    """A room as the list and its screens show it, with what the caller may do in it."""
    owner = session.get(Guest, room.owner_guest_id) if room.owner_guest_id else None
    return RoomInfoOut(
        code=room.code,
        name=room.name,
        join_path=f"/j/{room.code}",
        public_base_url=settings.public_base_url,
        owner=owner.nickname if owner else "Host",
        protected=room.password_hash is not None,
        created_at=as_utc(room.created_at),
        expires_at=as_utc(room.expires_at),
        mine=bool(actor and actor.room_owner),
        manage=bool(actor and actor.manages),
        tv=bool(actor and (actor.is_host or actor.is_tv)),
        joined=bool(actor and (actor.is_host or actor.guest is not None)),
    )


@api.get("/rooms")
def rooms(request: Request, db: Sessions, settings: AppSettings) -> list[RoomInfoOut]:
    """The open rooms, newest first. Anyone may see the list; a room with a password asks for it to enter."""
    with transaction(db) as session:
        found = session.scalars(select(Room).where(*deps.open_rooms()).order_by(Room.created_at.desc())).all()
        return [room_out(room, session, deps.find_actor(request, session, room), settings) for room in found]


@api.get("/rooms/{code}")
def room(request: Request, db: Sessions, settings: AppSettings, code: str) -> RoomInfoOut:
    """One open room: what its screens show (name, the QR's origin) and what the caller may do in it."""
    with transaction(db) as session:
        found = deps.open_room(session, code)
        return room_out(found, session, deps.find_actor(request, session, found), settings)


MAX_OPEN_ROOMS = 20  # beyond it only the host makes another (docs/ARCHITECTURE.md, "Salas")


@api.post("/rooms", status_code=201)
def create_room(request: Request, response: Response, db: Sessions, body: RoomIn) -> RoomOut:
    """A new room, beside the others. Anyone may make one: the host makes it as no one's; anyone else becomes its
    owner and its guest, with the phone's token (a new one for a phone that had none), so it stays the owner after
    joining other rooms. Someone in no room yet gives a nickname. Except for the host, an address makes a few rooms
    an hour, and none once many are open."""
    with transaction(db) as session:
        actor = deps.find_actor(request, session)
        is_host = actor is not None and actor.is_host
        if actor is not None and not can(actor, Action.CREATE_ROOM):
            raise HTTPException(403, "Você não pode criar uma sala.")
        nickname = None
        if not is_host:
            nickname = body.nickname or (actor.guest.nickname if actor and actor.guest else None)
            if not nickname:
                raise HTTPException(422, "Informe o seu apelido para criar a sala.")
            if session.scalar(select(func.count()).select_from(Room).where(*deps.open_rooms())) >= MAX_OPEN_ROOMS:
                raise HTTPException(429, f"Já há {MAX_OPEN_ROOMS} salas abertas. Tente de novo quando alguma fechar.")
            if wait := request.app.state.creation_limiter.take(deps.client_address(request)):
                minutes = max(1, round(wait / 60))
                raise HTTPException(
                    429,
                    f"Muitas salas criadas daqui. Tente de novo em {minutes} minuto{'s' if minutes > 1 else ''}.",
                    headers={"Retry-After": str(wait)},
                )
        taken = set(session.scalars(select(Room.code)))
        code = new_room_code()
        while code in taken:
            code = new_room_code()
        now = utcnow()
        room = Room(
            code=code,
            name=body.name,
            password_hash=hash_pin(body.password) if body.password else None,
            created_at=now,
            expires_at=now + ROOM_LIFETIME,
        )
        session.add(room)
        session.flush()
        if not is_host:
            token = deps.phone_token(request)
            if token is None:
                token, _ = new_guest_token()
                deps.set_cookie(request, response, GUEST_COOKIE, token, GUEST_COOKIE_AGE)
            owner = Guest(id=str(uuid.uuid4()), room_id=room.id, nickname=nickname, token_hash=token_hash(token))
            session.add(owner)
            session.flush()
            room.owner_guest_id = owner.id
    log.info("sala %s criada por %s (%s)", code, "host" if is_host else "convidado",
             "com senha" if body.password else "pública")
    return RoomOut(code=room.code, name=room.name, join_path=f"/j/{room.code}")


@api.delete("/rooms/{code}", status_code=204)
def remove_room(request: Request, db: Sessions, code: str) -> None:
    """By its owner or the host: it leaves the list, its QR stops working and its screens are told (4404)."""
    with transaction(db) as session:
        room, actor = deps.room_actor(request, session, code)
        require(actor, Action.REMOVE_ROOM)
        close_room(session, room)
    log.info("sala %s removida", code)
    notify(hub(request).close_rooms, [room.id])


def new_room_code() -> str:
    return "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(6))


def check_room_password(request: Request, room: Room, password: str | None) -> None:
    if room.password_hash is None:
        return
    limited(request, lambda: 0 if password and verify_pin(password, room.password_hash) else None, "Senha incorreta.")


@api.post("/rooms/{code}/join")
def join(request: Request, response: Response, db: Sessions, code: str, body: JoinIn) -> GuestOut:
    """A phone joins with a nickname (and the room's password, when it has one). The phone keeps one anonymous
    token for every room; joining again keeps the same guest, and with it the ownership of the entries added."""
    with transaction(db) as session:
        room = deps.open_room(session, code)
        actor = deps.find_actor(request, session, room)
        if actor and actor.guest:
            actor.guest.nickname = body.nickname
            guest = actor.guest
        else:
            if not (actor and actor.is_host):
                check_room_password(request, room, body.password)
            token = deps.phone_token(request)
            if token is None:
                token, _ = new_guest_token()
                deps.set_cookie(request, response, GUEST_COOKIE, token, GUEST_COOKIE_AGE)
            guest = Guest(id=str(uuid.uuid4()), room_id=room.id, nickname=body.nickname, token_hash=token_hash(token))
            session.add(guest)
    return GuestOut(id=guest.id, nickname=guest.nickname, room_code=room.code)


@api.post("/rooms/{code}/tv", status_code=204)
def room_tv(request: Request, response: Response, db: Sessions, code: str, body: RoomTvIn) -> None:
    """The room's TV: its password gives a TV cookie for this room, and its owner needs no password. A room without
    a password has none to check, so only its owner (and the admin) may be its TV. The host, or a TV cookie for
    every room, already is the TV here."""
    with transaction(db) as session:
        room = deps.open_room(session, code)
        actor = deps.find_actor(request, session, room)
        if actor and (actor.is_host or actor.is_tv):
            return
        if not (actor and actor.room_owner):
            if room.password_hash is None:
                raise HTTPException(403, "Só o dono da sala ou o admin abrem a TV de uma sala sem senha.")
            check_room_password(request, room, body.password)
    deps.set_cookie(request, response, TV_COOKIE, deps.host_signer(request).issue_tv(str(room.id)), HOST_COOKIE_AGE)


# --- queue ---------------------------------------------------------------------------------------------------------

def hub(connection: Request | WebSocket) -> Hub:
    return connection.app.state.hub


def notify(fn, *args) -> None:
    """Run a hub coroutine from a route (routes run in worker threads); always after the transaction committed."""
    anyio.from_thread.run(fn, *args)


REFUSED_VERB = {
    Action.REMOVE_ENTRY: "remover esta música",
    Action.CHANGE_KEY: "mudar o tom desta música",
    Action.ANSWER_TRANSCRIPTION: "responder sobre a letra desta música",
}


def require(actor: Actor, action: Action, entry: QueueEntry | None = None, session: Session | None = None) -> None:
    """Refuses what the permission matrix doesn't allow, saying who may: the entry's owner, by nickname, or the
    host."""
    if can(actor, action, entry):
        return
    verb = REFUSED_VERB.get(action)
    if entry is None or verb is None:
        raise HTTPException(403, "Só o host pode fazer isso.")
    owner = session.get(Guest, entry.guest_id) if session is not None and entry.guest_id else None
    if owner is None:
        raise HTTPException(403, f"Só o host pode {verb}.")
    who = "a TV" if owner.token_hash == tv_token(owner.room_id) else owner.nickname
    raise HTTPException(403, f"Só {who}, que adicionou esta música, ou o host podem {verb}.")


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
        # The owner: the guest; the TV adds as the room's "TV" guest, so it can remove the song or change its key
        owner = actor.guest or (actor.tv_guest if actor.is_tv else None)
        nickname = owner.nickname if owner else None
        try:
            entry = add_to_queue(
                session,
                settings,
                room,
                body.video_id,
                guest_id=owner.id if owner else None,
                singer_name=body.singer_name or (actor.guest.nickname if actor.guest else None),
                semitones=body.semitones,
                known=request.app.state.search.find(body.video_id),
            )
        except TooLong as exc:
            raise HTTPException(422, str(exc)) from exc
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
            require(actor, Action.CHANGE_KEY, entry, session)
            entry.semitones = body.semitones
        if body.position is not None:
            require(actor, Action.REORDER, entry)
            try:
                move_entry(session, room, entry, body.position)
            except QueueError as exc:
                raise HTTPException(409, str(exc)) from exc
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
        require(actor, Action.REMOVE_ENTRY, entry, session)
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
        require(actor, Action.ANSWER_TRANSCRIPTION, entry, session)
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
    """Authenticated by the same cookie as REST. `?role=tv` (the TV's cookie or the host's) marks the TV: it gets
    player.command and reports player.state."""
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
    connection = Connection(websocket, room.id, actor, tv=role == "tv" and (actor.is_host or actor.is_tv))
    rooms = hub(websocket)
    rooms.join(connection)
    try:
        await rooms.greet(connection)
        while True:
            message = await websocket.receive_json()
            if isinstance(message, dict) and message.get("type") == "player.state" and connection.tv:
                await rooms.tv_state(room.id, message)
    except (WebSocketDisconnect, WebSocketDisconnected, ValueError):
        pass  # the phone left, or the server closed the socket (the room was removed or expired)
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

@internal.get("/media-auth", status_code=204)
def media_auth(request: Request, db: Sessions) -> None:
    """Caddy asks before serving /media (forward_auth): only the host or a guest of an open room gets the audio and
    the lyrics. Not routed by Caddy itself."""
    with transaction(db) as session:
        if deps.find_actor(request, session) is None:
            raise HTTPException(401, "Entre numa sala pelo QR Code primeiro.")


@internal.post("/events", status_code=204)
def worker_event(request: Request, event: EventIn) -> None:
    """Job progress from the worker, passed on to the screens. Not routed by Caddy."""
    log.info("evento %s", event.model_dump())
    notify(hub(request).worker_event, event.model_dump())
