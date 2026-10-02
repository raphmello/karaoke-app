"""Who is calling, resolved from the cookies before any permission check. Ids sent by the client are never trusted."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from karaoke.core.auth import GUEST_COOKIE, HOST_COOKIE, HostSigner, token_hash
from karaoke.core.config import Settings
from karaoke.core.models import Guest, Room

SEEN_EVERY = timedelta(minutes=1)


@dataclass(frozen=True)
class Actor:
    """The host, or a guest of an active room. A request with the host cookie acts as the host."""

    guest: Guest | None = None

    @property
    def is_host(self) -> bool:
        return self.guest is None

    @property
    def owner_id(self) -> str | None:
        """queue_entries.guest_id for what this actor adds: the guest's id, or None for the host."""
        return self.guest.id if self.guest else None


def settings(request: Request) -> Settings:
    return request.app.state.settings


def sessions(request: Request) -> sessionmaker[Session]:
    return request.app.state.sessions


def host_signer(request: Request) -> HostSigner:
    return request.app.state.host_signer


def find_actor(request: Request, session: Session) -> Actor | None:
    if host_signer(request).verify(request.cookies.get(HOST_COOKIE)):
        return Actor()
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
    return Actor(guest)


def require_actor(request: Request, session: Session) -> Actor:
    actor = find_actor(request, session)
    if actor is None:
        raise HTTPException(401, "Entre numa sala pelo QR Code primeiro.")
    return actor


def require_host(request: Request, session: Session) -> Actor:
    actor = find_actor(request, session)
    if actor is None or not actor.is_host:
        raise HTTPException(401, "Só o host pode fazer isso. Entre com o PIN.")
    return actor


def active_room(session: Session, code: str) -> Room:
    room = session.scalar(select(Room).where(Room.code == code.upper(), Room.is_active))
    if room is None:
        raise HTTPException(404, "Sala não encontrada ou encerrada.")
    return room


def room_actor(request: Request, session: Session, code: str) -> tuple[Room, Actor]:
    """The room, and a caller who belongs to it: the host, or one of its guests."""
    room = active_room(session, code)
    actor = require_actor(request, session)
    if not actor.is_host and actor.guest.room_id != room.id:
        raise HTTPException(403, "Você não está nesta sala.")
    return room, actor


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
