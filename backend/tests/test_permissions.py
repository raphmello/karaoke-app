"""The permission matrix of docs/ARCHITECTURE.md, row by row: owner of the entry, another guest, host."""
import pytest

from karaoke.core.models import Guest, QueueEntry
from karaoke.core.permissions import Action, Actor, can

OWNER = Actor(Guest(id="owner", room_id=1, nickname="Ana", token_hash="a"))
OTHER = Actor(Guest(id="other", room_id=1, nickname="Bia", token_hash="b"))
HOST = Actor()
ENTRY = QueueEntry(id=1, room_id=1, video_id="dQw4w9WgXcQ", guest_id="owner", position=1)

MATRIX = [
    # action, owner, other guest, host
    (Action.ADD, True, True, True),
    (Action.REMOVE_ENTRY, True, False, True),
    (Action.CHANGE_KEY, True, False, True),
    (Action.ANSWER_TRANSCRIPTION, True, False, True),
    (Action.REORDER, False, False, True),
    (Action.PLAYER, False, False, True),
    (Action.PLAYER_SETTINGS, False, False, True),
    (Action.REPROCESS, False, False, True),
    (Action.REMOVE_SONG, False, False, True),
    (Action.RESTORE_SONG, False, False, True),
]


@pytest.mark.parametrize(("action", "owner", "other", "host"), MATRIX, ids=[row[0].value for row in MATRIX])
def test_matrix(action, owner, other, host):
    assert can(OWNER, action, ENTRY) is owner
    assert can(OTHER, action, ENTRY) is other
    assert can(HOST, action, ENTRY) is host


def test_every_action_is_in_the_matrix():
    assert {row[0] for row in MATRIX} == set(Action)


def test_an_entry_the_host_added_belongs_to_no_guest():
    host_entry = QueueEntry(id=2, room_id=1, video_id="dQw4w9WgXcQ", guest_id=None, position=2)
    assert not can(OWNER, Action.REMOVE_ENTRY, host_entry)
    assert can(HOST, Action.REMOVE_ENTRY, host_entry)
