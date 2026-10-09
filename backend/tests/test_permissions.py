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
    (Action.ADD, True, True, True, True),
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


def test_a_phone_that_is_the_tv_and_a_guest_has_both_sets_of_rights():
    both = Actor(Guest(id="owner", room_id=1, nickname="Ana", token_hash="a"), tv=True)
    others = QueueEntry(id=4, room_id=1, video_id="dQw4w9WgXcQ", guest_id="other", position=2, status="queued")
    assert can(both, Action.ADD)
    assert can(both, Action.REMOVE_ENTRY, ENTRY) and can(both, Action.CHANGE_KEY, ENTRY)  # its own entry
    assert can(both, Action.PLAYER)
    assert not can(both, Action.REMOVE_ENTRY, others) and not can(both, Action.CHANGE_KEY, others)
    assert not can(both, Action.REORDER) and not can(both, Action.REPROCESS)
    assert not both.is_host and both.owner_id == "owner"


def test_the_tv_owns_what_its_room_guest_added():
    tv_guest = Guest(id="tv-guest", room_id=1, nickname="TV", token_hash="tv:1")
    tv = Actor(tv=True, tv_guest=tv_guest)
    its = QueueEntry(id=5, room_id=1, video_id="dQw4w9WgXcQ", guest_id="tv-guest", position=3, status="queued")
    assert can(tv, Action.REMOVE_ENTRY, its) and can(tv, Action.CHANGE_KEY, its) and tv.owns(its)
    assert not can(tv, Action.REMOVE_ENTRY, ENTRY) and not tv.owns(ENTRY)
    assert not can(OWNER, Action.REMOVE_ENTRY, its)  # a guest is never the TV's guest
    assert not Actor(tv_guest=tv_guest).owner_ids  # without the TV cookie the TV's guest counts for nothing


def test_the_tv_without_its_guest_owns_nothing():
    assert not TV.is_host and not TV.owner_ids and not TV.owns(ENTRY)
