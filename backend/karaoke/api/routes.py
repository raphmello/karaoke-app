"""REST routes of phase 2: search, songs and library, host login, rooms, joining and the queue.

Each route runs in one short transaction (karaoke.core.db): it resolves the caller from the cookies, checks the
permission and answers after the commit. The YouTube search runs outside any transaction.
"""
from __future__ import annotations

import logging
import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from karaoke.api import deps
from karaoke.api.schemas import (
    EventIn,
    GuestOut,
    JoinIn,
    LoginIn,
    QueueEntryIn,
    QueueEntryOut,
    RoomIn,
    RoomOut,
    SearchResult,
    SongOut,
)
from karaoke.core.auth import GUEST_COOKIE, HOST_COOKIE, hash_pin, new_guest_token, pin_matches
from karaoke.core.config import Settings
from karaoke.core.db import transaction
from karaoke.core.models import ACTIVE_ENTRY, READY, Guest, QueueEntry, Room, Song
from karaoke.core.songs import add_to_queue
from karaoke.core.storage import VIDEO_ID

log = logging.getLogger("karaoke.api")

api = APIRouter(prefix="/api")
internal = APIRouter(prefix="/internal")

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
def library(request: Request, db: Sessions, q: Annotated[str | None, Query(max_length=200)] = None) -> list[SongOut]:
    """The songs that play right away. Removed ones stay in the database but out of the library."""
    with transaction(db) as session:
        deps.require_actor(request, session)
        query = select(Song).where(Song.status == READY)
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

@api.get("/rooms/{code}/queue")
def queue(request: Request, db: Sessions, code: str) -> list[QueueEntryOut]:
    with transaction(db) as session:
        room, actor = deps.room_actor(request, session, code)
        rows = session.execute(
            select(QueueEntry, Song, Guest.nickname)
            .join(Song, Song.video_id == QueueEntry.video_id)
            .outerjoin(Guest, Guest.id == QueueEntry.guest_id)
            .where(QueueEntry.room_id == room.id, QueueEntry.status.in_(ACTIVE_ENTRY))
            .order_by(QueueEntry.position)
        ).all()
        return [entry_out(entry, song, nickname, actor) for entry, song, nickname in rows]


@api.post("/rooms/{code}/queue", status_code=201)
def add(request: Request, db: Sessions, settings: AppSettings, code: str, body: QueueEntryIn) -> QueueEntryOut:
    with transaction(db) as session:
        room, actor = deps.room_actor(request, session, code)
        nickname = actor.guest.nickname if actor.guest else None
        entry = add_to_queue(
            session,
            settings,
            room,
            body.video_id,
            guest_id=actor.owner_id,
            singer_name=body.singer_name or nickname,
            semitones=body.semitones,
        )
        return entry_out(entry, session.get(Song, entry.video_id), nickname, actor)


def entry_out(entry: QueueEntry, song: Song, nickname: str | None, actor: deps.Actor) -> QueueEntryOut:
    return QueueEntryOut(
        id=entry.id,
        video_id=entry.video_id,
        position=entry.position,
        status=entry.status,
        singer_name=entry.singer_name,
        semitones=entry.semitones,
        added_by=nickname or "host",
        mine=entry.guest_id == actor.owner_id,
        song=SongOut.of(song),
    )


# --- worker → API --------------------------------------------------------------------------------------------------

@internal.post("/events", status_code=204)
def worker_event(event: EventIn) -> None:
    """Job progress from the worker. Not routed by Caddy. The WebSocket that passes it on to the screens comes in
    phase 4; until then the API only logs it."""
    log.info("evento %s", event.model_dump())
