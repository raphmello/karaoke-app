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
    """The host, the TV, a guest of an active room, or the TV and a guest at once. A request with the host cookie
    acts as the host. The TV cookie (TV_PIN) plays the queue and owns the songs it adds, through the room's "TV" guest
    (`tv_guest`, None until the TV adds one); a phone that is the TV and also joined as a guest (an iPhone mirrored
    to the TV, say) carries both cookies and has both sets of rights."""

    guest: Guest | None = None
    tv: bool = False
    tv_guest: Guest | None = None

    @property
    def is_host(self) -> bool:
        return self.guest is None and not self.tv

    @property
    def is_tv(self) -> bool:
        return self.tv

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
TV = {Action.PLAYER, Action.ADD}  # the key of the entry that is playing; and, as an owner, the songs it added


def can(actor: Actor, action: Action, entry: QueueEntry | None = None) -> bool:
    if actor.is_host:
        return True
    if actor.is_tv and (action in TV or (action == Action.CHANGE_KEY and entry is not None and entry.status == PLAYING)):
        return True
    if actor.guest is not None and action in EVERYONE:
        return True
    if action in OWNER:
        return entry is not None and entry.guest_id is not None and entry.guest_id in actor.owner_ids
    return False
