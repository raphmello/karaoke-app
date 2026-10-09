"""Who is calling, resolved from the cookies before any permission check. Ids sent by the client are never trusted."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import HTTPConnection

from karaoke.core.auth import GUEST_COOKIE, HOST_COOKIE, TV_COOKIE, HostSigner, token_hash
from karaoke.core.config import Settings
from karaoke.core.models import Guest, Room
from karaoke.core.permissions import Actor, tv_token

SEEN_EVERY = timedelta(minutes=1)


def settings(request: HTTPConnection) -> Settings:
    return request.app.state.settings


def sessions(request: HTTPConnection) -> sessionmaker[Session]:
    return request.app.state.sessions


def host_signer(request: HTTPConnection) -> HostSigner:
    return request.app.state.host_signer


def find_actor(request: HTTPConnection, session: Session) -> Actor | None:
    if host_signer(request).verify(request.cookies.get(HOST_COOKIE)):
        return Actor()
    # The TV's cookie and a guest's are read together: the phone that is the TV may also have joined as a guest
    tv = host_signer(request).verify(request.cookies.get(TV_COOKIE), role="tv")
    guest = find_guest(request, session)
    if guest is None and not tv:
        return None
    # The TV's own guest is there from the start, so its live queue already shows what it adds as its own
    return Actor(guest, tv=tv, tv_guest=tv_guest(session, create=True) if tv else None)


TV_NICKNAME = "TV"


def tv_guest(session: Session, create: bool = False) -> Guest | None:
    """The open room's "TV" guest, who owns the songs the TV adds; made the first time the TV adds one."""
    room = session.scalar(select(Room).where(Room.is_active).order_by(Room.id.desc()))
    if room is None:
        return None
    guest = session.scalar(select(Guest).where(Guest.token_hash == tv_token(room.id)))
    if guest is None and create:
        guest = Guest(id=str(uuid.uuid4()), room_id=room.id, nickname=TV_NICKNAME, token_hash=tv_token(room.id))
        session.add(guest)
        session.flush()
    return guest


def find_guest(request: HTTPConnection, session: Session) -> Guest | None:
    token = request.cookies.get(GUEST_COOKIE)
    if not token:
        return None
    guest = session.scalar(
        select(Guest).join(Room, Room.id == Guest.room_id).where(Guest.token_hash == token_hash(token), Room.is_active)
    )
    if guest is None:  # unknown token, or a room that has closed: the old QR stops working
        return None
    now = datetime.now(UTC)
    if guest.last_seen_at is None or guest.last_seen_at.replace(tzinfo=UTC) < now - SEEN_EVERY:
        guest.last_seen_at = now  # SQLite returns datetimes without the zone; they are all UTC
    return guest


def require_actor(request: HTTPConnection, session: Session) -> Actor:
    actor = find_actor(request, session)
    if actor is None:
        raise HTTPException(401, "Entre numa sala pelo QR Code primeiro.")
    return actor


def require_host(request: HTTPConnection, session: Session) -> Actor:
    actor = find_actor(request, session)
    if actor is None or not actor.is_host:
        raise HTTPException(401, "Só o host pode fazer isso. Entre com o PIN.")
    return actor


def require_tv(request: HTTPConnection, session: Session) -> Actor:
    """The TV's own routes: the host, or the TV logged in with TV_PIN."""
    actor = find_actor(request, session)
    if actor is None or not (actor.is_host or actor.is_tv):
        raise HTTPException(401, "Entre com o PIN da TV.")
    return actor


def active_room(session: Session, code: str) -> Room:
    room = session.scalar(select(Room).where(Room.code == code.upper(), Room.is_active))
    if room is None:
        raise HTTPException(404, "Sala não encontrada ou encerrada.")
    return room


def room_actor(request: HTTPConnection, session: Session, code: str) -> tuple[Room, Actor]:
    """The room, and a caller who belongs to it: the host, the TV, or one of its guests."""
    room = active_room(session, code)
    actor = require_actor(request, session)
    if actor.guest is not None and actor.guest.room_id != room.id:
        raise HTTPException(403, "Você não está nesta sala.")
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
