"""The permission matrix (docs/ARCHITECTURE.md, "Matriz de permissões"), in one function every route calls."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from karaoke.core.models import PLAYING, Guest, QueueEntry


def tv_token(room_id: int) -> str:
    """guests.token_hash of a room's "TV" guest, who owns the songs the TV adds. A real guest's is a sha256 in hex,
    which never has a colon, so no phone can ever be this guest."""
    return f"tv:{room_id}"


@dataclass(frozen=True)
class Actor:
    """Who calls, in one room (or in none, for what all rooms share: the library, the search, the media).

    The host's cookie acts as the host everywhere. Otherwise the caller may be, at once: the guest of this room (the
    phone's token, which it keeps across rooms), the room's owner (the guest who made it), and the room's TV (a TV
    cookie for this room or for all). The TV owns the songs it adds through the room's "TV" guest (`tv_guest`). A
    phone that is the TV and also joined as a guest (an iPhone mirrored to the TV, say) has both sets of rights."""

    guest: Guest | None = None
    tv: bool = False
    tv_guest: Guest | None = None
    room_owner: bool = False

    @property
    def is_host(self) -> bool:
        return self.guest is None and not self.tv

    @property
    def is_tv(self) -> bool:
        return self.tv

    @property
    def manages(self) -> bool:
        """The host, or the owner of this room: the queue's and the player's controls are theirs."""
        return self.is_host or self.room_owner

    @property
    def owner_ids(self) -> set[str]:
        """The queue_entries.guest_id this actor owns: its guest's, and the room's "TV" guest's when it is the TV."""
        return {g.id for g in (self.guest, self.tv_guest if self.tv else None) if g is not None}

    @property
    def owner_id(self) -> str | None:
        """Who answers or adds, for the records: the guest, else the TV's guest, else None for the host."""
        if self.guest:
            return self.guest.id
        return self.tv_guest.id if self.tv and self.tv_guest else None

    def owns(self, entry: QueueEntry) -> bool:
        """Whether the entry shows as this actor's ("mine"): its guest's or the TV's; the host's are the ones no guest
        added."""
        if entry.guest_id is None:
            return self.is_host
        return entry.guest_id in self.owner_ids


class Action(StrEnum):
    CREATE_ROOM = "create_room"
    REMOVE_ROOM = "remove_room"
    ADD = "add"  # search and add a song
    REMOVE_ENTRY = "remove_entry"  # if it is playing, it is skipped
    CHANGE_KEY = "change_key"
    ANSWER_TRANSCRIPTION = "answer_transcription"
    REORDER = "reorder"
    PLAYER = "player"  # play, pause, skip
    PLAYER_SETTINGS = "player_settings"  # guide voice and the TV's delay
    REPROCESS = "reprocess"  # change the lyrics or redo stages
    REMOVE_SONG = "remove_song"  # remove a song from the library, deleting its files


GUEST = {Action.ADD, Action.CREATE_ROOM}
OWNER = {Action.REMOVE_ENTRY, Action.CHANGE_KEY, Action.ANSWER_TRANSCRIPTION}  # of the entry
TV = {Action.PLAYER, Action.ADD, Action.CREATE_ROOM}  # the key of the entry that is playing; and, as an owner, the songs it added
# The room's owner is the "host" of that room; the library and the panel stay the host's
ROOM_OWNER = {
    Action.REMOVE_ROOM, Action.ADD, Action.REMOVE_ENTRY, Action.CHANGE_KEY, Action.ANSWER_TRANSCRIPTION,
    Action.REORDER, Action.PLAYER, Action.PLAYER_SETTINGS, Action.CREATE_ROOM,
}


def can(actor: Actor, action: Action, entry: QueueEntry | None = None) -> bool:
    if actor.is_host:
        return True
    if actor.room_owner and action in ROOM_OWNER:
        return True
    if actor.is_tv and (action in TV or (action == Action.CHANGE_KEY and entry is not None and entry.status == PLAYING)):
        return True
    if actor.guest is not None and action in GUEST:
        return True
    if action in OWNER:
        return entry is not None and entry.guest_id is not None and entry.guest_id in actor.owner_ids
    return False
