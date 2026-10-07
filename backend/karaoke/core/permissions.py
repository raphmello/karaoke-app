"""The permission matrix (docs/ARCHITECTURE.md, "Matriz de permissões"), in one function every route calls."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from karaoke.core.models import PLAYING, Guest, QueueEntry

NOBODY = "tv"  # the TV's owner_id: no entry's guest_id is ever this, so nothing in the queue is the TV's


@dataclass(frozen=True)
class Actor:
    """The host, the TV, a guest of an active room, or the TV and a guest at once. A request with the host cookie
    acts as the host. The TV cookie (TV_PIN) plays the queue; a phone that is the TV and also joined as a guest (an
    iPhone mirrored to the TV, say) carries both cookies and has both sets of rights."""

    guest: Guest | None = None
    tv: bool = False

    @property
    def is_host(self) -> bool:
        return self.guest is None and not self.tv

    @property
    def is_tv(self) -> bool:
        return self.tv

    @property
    def owner_id(self) -> str | None:
        """queue_entries.guest_id for what this actor adds: the guest's id, or None for the host."""
        if self.guest:
            return self.guest.id
        return NOBODY if self.tv else None


class Action(StrEnum):
    ADD = "add"  # search and add a song
    REMOVE_ENTRY = "remove_entry"  # if it is playing, it is skipped
    CHANGE_KEY = "change_key"
    ANSWER_TRANSCRIPTION = "answer_transcription"
    REORDER = "reorder"
    PLAYER = "player"  # play, pause, skip
    PLAYER_SETTINGS = "player_settings"  # guide voice and the TV's delay
    REPROCESS = "reprocess"  # change the lyrics or redo stages
    REMOVE_SONG = "remove_song"  # mark a library song as removed
    RESTORE_SONG = "restore_song"


EVERYONE = {Action.ADD}
OWNER = {Action.REMOVE_ENTRY, Action.CHANGE_KEY, Action.ANSWER_TRANSCRIPTION}
TV = {Action.PLAYER}  # and the key of the entry that is playing


def can(actor: Actor, action: Action, entry: QueueEntry | None = None) -> bool:
    if actor.is_host:
        return True
    if actor.is_tv and (action in TV or (action == Action.CHANGE_KEY and entry is not None and entry.status == PLAYING)):
        return True
    if actor.guest is None:  # the TV alone: nothing a guest does
        return False
    if action in EVERYONE:
        return True
    if action in OWNER:
        return entry is not None and entry.guest_id is not None and entry.guest_id == actor.guest.id
    return False
