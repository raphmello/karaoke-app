"""The permission matrix of docs/ARCHITECTURE.md, row by row: owner of the entry, another guest, the TV, host."""
import pytest

from karaoke.core.models import Guest, QueueEntry
from karaoke.core.permissions import Action, Actor, can

OWNER = Actor(Guest(id="owner", room_id=1, nickname="Ana", token_hash="a"))
OTHER = Actor(Guest(id="other", room_id=1, nickname="Bia", token_hash="b"))
TV = Actor(tv=True)
HOST = Actor()
ENTRY = QueueEntry(id=1, room_id=1, video_id="dQw4w9WgXcQ", guest_id="owner", position=1, status="queued")

MATRIX = [
    # action, owner, other guest, TV, host (the TV's key change of the entry that plays has its own test)
    (Action.ADD, True, True, False, True),
    (Action.REMOVE_ENTRY, True, False, False, True),
    (Action.CHANGE_KEY, True, False, False, True),
    (Action.ANSWER_TRANSCRIPTION, True, False, False, True),
    (Action.REORDER, False, False, False, True),
    (Action.PLAYER, False, False, True, True),
    (Action.PLAYER_SETTINGS, False, False, False, True),
    (Action.REPROCESS, False, False, False, True),
    (Action.REMOVE_SONG, False, False, False, True),
    (Action.RESTORE_SONG, False, False, False, True),
]


@pytest.mark.parametrize(("action", "owner", "other", "tv", "host"), MATRIX, ids=[row[0].value for row in MATRIX])
def test_matrix(action, owner, other, tv, host):
    assert can(OWNER, action, ENTRY) is owner
    assert can(OTHER, action, ENTRY) is other
    assert can(TV, action, ENTRY) is tv
    assert can(HOST, action, ENTRY) is host


def test_every_action_is_in_the_matrix():
    assert {row[0] for row in MATRIX} == set(Action)


def test_an_entry_the_host_added_belongs_to_no_guest():
    host_entry = QueueEntry(id=2, room_id=1, video_id="dQw4w9WgXcQ", guest_id=None, position=2)
    assert not can(OWNER, Action.REMOVE_ENTRY, host_entry)
    assert can(HOST, Action.REMOVE_ENTRY, host_entry)


def test_the_tv_changes_the_key_only_of_the_entry_that_plays():
    playing = QueueEntry(id=3, room_id=1, video_id="dQw4w9WgXcQ", guest_id="owner", position=1, status="playing")
    assert can(TV, Action.CHANGE_KEY, playing)
    assert not can(TV, Action.CHANGE_KEY, ENTRY)
    assert not can(TV, Action.CHANGE_KEY)


def test_nothing_in_the_queue_is_the_tvs():
    assert not TV.is_host and TV.owner_id not in (None, "owner", "other")
