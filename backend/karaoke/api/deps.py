"""Who is calling, resolved from the cookies before any permission check. Ids sent by the client are never trusted."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import HTTPConnection

from karaoke.core.auth import ALL_ROOMS, GUEST_COOKIE, HOST_COOKIE, TV_COOKIE, HostSigner, token_hash
from karaoke.core.config import Settings
from karaoke.core.models import Guest, Room
from karaoke.core.permissions import Actor, tv_token
from karaoke.core.songs import open_rooms

SEEN_EVERY = timedelta(minutes=1)


def settings(request: HTTPConnection) -> Settings:
    return request.app.state.settings


def sessions(request: HTTPConnection) -> sessionmaker[Session]:
    return request.app.state.sessions


def host_signer(request: HTTPConnection) -> HostSigner:
    return request.app.state.host_signer


def open_room(session: Session, code: str) -> Room:
    room = session.scalar(select(Room).where(Room.code == code.upper(), *open_rooms()))
    if room is None:
        raise HTTPException(404, "Sala não encontrada, encerrada ou expirada.")
    return room


def find_actor(request: HTTPConnection, session: Session, room: Room | None = None) -> Actor | None:
    """Who calls, in `room`; without a room, for what every room shares (the library, the search, the media)."""
    if host_signer(request).verify(request.cookies.get(HOST_COOKIE)):
        return Actor()
    # The TV's cookie and a guest's are read together: the phone that is the TV may also have joined as a guest
    scope = host_signer(request).tv_scope(request.cookies.get(TV_COOKIE))
    if room is not None:
        tv = scope == ALL_ROOMS or scope == str(room.id)
    else:
        tv = scope == ALL_ROOMS or (scope is not None and scope.isdigit() and session.scalar(
            select(Room.id).where(Room.id == int(scope), *open_rooms())) is not None)
    guest = find_guest(request, session, room)
    if guest is None and not tv:
        return None
    owner = room is not None and guest is not None and room.owner_guest_id == guest.id
    # The TV's own guest is there from the start, so its live queue already shows what it adds as its own
    return Actor(guest, tv=tv, tv_guest=tv_guest(session, room, create=True) if tv and room else None, room_owner=owner)


TV_NICKNAME = "TV"


def tv_guest(session: Session, room: Room, create: bool = False) -> Guest | None:
    """The room's "TV" guest, who owns the songs the TV adds."""
    guest = session.scalar(select(Guest).where(Guest.room_id == room.id, Guest.token_hash == tv_token(room.id)))
    if guest is None and create:
        guest = Guest(id=str(uuid.uuid4()), room_id=room.id, nickname=TV_NICKNAME, token_hash=tv_token(room.id))
        session.add(guest)
        session.flush()
    return guest


def phone_token(request: HTTPConnection) -> str | None:
    """The phone's anonymous token: one per phone, the same in every room it joins."""
    return request.cookies.get(GUEST_COOKIE) or None


def find_guest(request: HTTPConnection, session: Session, room: Room | None = None) -> Guest | None:
    """The phone's guest in `room`; without a room, its guest in any open room (the most recently seen)."""
    token = phone_token(request)
    if not token:
        return None
    query = select(Guest).join(Room, Room.id == Guest.room_id).where(Guest.token_hash == token_hash(token), *open_rooms())
    if room is not None:
        query = query.where(Guest.room_id == room.id)
    guest = session.scalar(query.order_by(Guest.last_seen_at.desc().nulls_last()))
    if guest is None:  # unknown token, not in this room, or a room that has closed: the old QR stops working
        return None
    now = datetime.now(UTC)
    if guest.last_seen_at is None or guest.last_seen_at.replace(tzinfo=UTC) < now - SEEN_EVERY:
        guest.last_seen_at = now  # SQLite returns datetimes without the zone; they are all UTC
    return guest


def require_actor(request: HTTPConnection, session: Session, room: Room | None = None) -> Actor:
    actor = find_actor(request, session, room)
    if actor is None:
        raise HTTPException(401, "Entre numa sala primeiro.")
    return actor


def require_host(request: HTTPConnection, session: Session) -> Actor:
    actor = find_actor(request, session)
    if actor is None or not actor.is_host:
        raise HTTPException(401, "Só o host pode fazer isso. Entre com o PIN.")
    return actor


def room_actor(request: HTTPConnection, session: Session, code: str) -> tuple[Room, Actor]:
    """The open room, and a caller who belongs to it: the host, its TV, or one of its guests."""
    room = open_room(session, code)
    actor = find_actor(request, session, room)
    if actor is None:
        raise HTTPException(401, "Entre nesta sala primeiro.")
    return room, actor


def client_address(request: HTTPConnection) -> str:
    """Who is asking, for the login limit. Through the tunnel the Cloudflare edge sets CF-Connecting-IP (a client
    can't forge it there); on the home network the request comes straight from the phone or the PC."""
    return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")


def set_cookie(request: Request, response: Response, name: str, value: str, max_age: int) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",  # behind Caddy, uvicorn takes the scheme from X-Forwarded-Proto
        path="/",
    )


def clear_cookie(request: Request, response: Response, name: str) -> None:
    """The browser drops a cookie only when the attributes match the ones it was set with."""
    response.delete_cookie(name, httponly=True, samesite="lax", secure=request.url.scheme == "https", path="/")
