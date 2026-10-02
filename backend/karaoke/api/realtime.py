"""The WebSocket of each room (docs/ARCHITECTURE.md, "WebSocket"): state changes go back to every screen.

Commands go by REST; this hub passes the results on. The queue always goes whole (queue.snapshot): it is small, and
sending everything avoids sync bugs. The API runs as one process, so the connections live in memory.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import WebSocket
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from starlette.concurrency import run_in_threadpool

from karaoke.api.schemas import QueueEntryOut
from karaoke.core.db import transaction
from karaoke.core.models import QueueEntry, Room, Song
from karaoke.core.permissions import Actor
from karaoke.core.songs import queue_rows, set_playing

log = logging.getLogger("karaoke.api")

Rows = list[tuple[QueueEntry, Song, str | None]]


@dataclass(eq=False)
class Connection:
    websocket: WebSocket
    room_id: int
    actor: Actor
    tv: bool  # the TV receives player.command and is the only one that reports player.state

    async def send(self, message: dict) -> None:
        try:
            await self.websocket.send_json(message)
        except Exception:  # a phone that went away; its own loop removes it
            log.debug("envio falhou para uma conexão da sala %s", self.room_id)


def snapshot(rows: Rows, actor: Actor) -> dict:
    entries = [QueueEntryOut.of(entry, song, nickname, actor).model_dump() for entry, song, nickname in rows]
    return {"type": "queue.snapshot", "entries": entries}


class Hub:
    def __init__(self, sessions: sessionmaker[Session]):
        self.sessions = sessions
        self.rooms: dict[int, set[Connection]] = defaultdict(set)
        self.player_state: dict[int, dict] = {}  # the TV's last report, for screens that connect later

    def join(self, connection: Connection) -> None:
        self.rooms[connection.room_id].add(connection)

    def leave(self, connection: Connection) -> None:
        self.rooms[connection.room_id].discard(connection)

    async def send(self, room_id: int, message: dict, to: Callable[[Connection], bool] = lambda c: True) -> None:
        for connection in list(self.rooms.get(room_id, ())):
            if to(connection):
                await connection.send(message)

    async def send_everywhere(self, message: dict) -> None:
        for room_id in list(self.rooms):
            await self.send(room_id, message)

    async def command(self, room_id: int, action: str, fields: dict | None = None) -> None:
        """player.command, to the TV only: play, pause, skip; key with the entry's semitones; guide and delay with
        their value."""
        await self.send(room_id, {"type": "player.command", "action": action, **(fields or {})}, to=lambda c: c.tv)

    async def close_rooms(self, room_ids: list[int]) -> None:
        """A room the host closed: its screens are told with close code 4404 (the TV then offers the new room)."""
        for room_id in room_ids:
            self.player_state.pop(room_id, None)
            for connection in list(self.rooms.pop(room_id, ())):
                try:
                    await connection.websocket.close(code=4404)
                except Exception:  # already gone
                    log.debug("conexão da sala %s já estava fechada", room_id)

    def _rows(self, room_id: int) -> Rows:
        with transaction(self.sessions) as session:
            room = session.get(Room, room_id)
            return queue_rows(session, room) if room else []

    async def queue_changed(self, room_id: int | None = None) -> None:
        """A fresh queue.snapshot for every screen of the room (or of every room), each with its own "mine"."""
        for rid in [room_id] if room_id is not None else list(self.rooms):
            if not self.rooms.get(rid):
                continue
            rows = await run_in_threadpool(self._rows, rid)
            for connection in list(self.rooms[rid]):
                await connection.send(snapshot(rows, connection.actor))

    async def greet(self, connection: Connection) -> None:
        rows = await run_in_threadpool(self._rows, connection.room_id)
        await connection.send(snapshot(rows, connection.actor))
        if state := self.player_state.get(connection.room_id):
            await connection.send(state)

    async def lyrics_missing(self, video_id: str, entry_ids: list[int]) -> None:
        """Only the owners of the waiting entries and the host get the question."""
        def owners() -> dict[int, tuple[int, str | None]]:
            with transaction(self.sessions) as session:
                rows = session.execute(
                    select(QueueEntry.id, QueueEntry.room_id, QueueEntry.guest_id).where(QueueEntry.id.in_(entry_ids))
                ).all()
                return {entry_id: (room_id, guest_id) for entry_id, room_id, guest_id in rows}

        found = await run_in_threadpool(owners)
        for room_id in {room_id for room_id, _ in found.values()}:
            for connection in list(self.rooms.get(room_id, ())):
                actor = connection.actor
                mine = [i for i, (r, g) in found.items() if r == room_id and (actor.is_host or g == actor.owner_id)]
                if mine:
                    await connection.send({"type": "song.lyrics_missing", "video_id": video_id, "entries": mine})

    async def worker_event(self, event: dict) -> None:
        kind = event["type"]
        if kind == "song.lyrics_missing":
            await self.lyrics_missing(event["video_id"], event.get("entries") or [])
        else:
            await self.send_everywhere(event)
        # Progress also refreshes the queue: the song's title and artist arrive with the first stages.
        if kind in ("song.progress", "song.ready", "song.failed", "song.lyrics_missing"):
            await self.queue_changed()

    async def tv_state(self, room_id: int, message: dict) -> None:
        """player.state from the TV: recorded (the entry it plays is playing, the previous one done) and passed on."""
        entry_id = message.get("entry_id")
        state = {
            "type": "player.state",
            "entry_id": entry_id if isinstance(entry_id, int) else None,
            "position": float(message.get("position") or 0),
            "paused": bool(message.get("paused")),
            "semitones": int(message.get("semitones") or 0),
        }

        def record() -> bool:
            with transaction(self.sessions) as session:
                return set_playing(session, session.get(Room, room_id), state["entry_id"])

        if await run_in_threadpool(record):
            await self.queue_changed(room_id)
        self.player_state[room_id] = state
        await self.send(room_id, state, to=lambda c: not c.tv)
