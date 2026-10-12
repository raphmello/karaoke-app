"""Many rooms (docs/ARCHITECTURE.md, "Salas"): a list anyone sees, rooms anyone makes (within limits), an optional
password, an owner who runs the room, a TV per room, removal and the 24 h expiry."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from helpers import TV_PIN, Caller, cookie_of
from starlette.websockets import WebSocketDisconnect

from karaoke.api.app import close_expired
from karaoke.core.db import transaction
from karaoke.core.models import Room, utcnow
from karaoke.core.songs import expire_rooms

VIDEO, OTHER_VIDEO = "dQw4w9WgXcQ", "aaaaaaaaaaa"


def add(caller, code, video=VIDEO):
    response = caller.post(f"/api/rooms/{code}/queue", json={"video_id": video})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def receive(ws, kind):
    while True:
        message = ws.receive_json()
        if message["type"] == kind:
            return message


@pytest.fixture
def stranger(app, client):
    """A phone with no cookie yet; its cookies pile up on it as a browser keeps them."""

    class Phone(Caller):
        def __init__(self):
            super().__init__(client, "")
            self.jar: dict[str, str] = {}

        def _call(self, method, path, headers=None, **kw):
            self.headers = {"cookie": "; ".join(f"{k}={v}" for k, v in self.jar.items())}
            response = super()._call(method, path, headers, **kw)
            for name, value in response.cookies.items():
                self.jar[name] = value
            return response

    return Phone


def test_anyone_sees_the_list_and_a_password_is_never_shown(client, host, code):
    host.post("/api/rooms", json={"name": "Família", "password": "segredo"})
    rooms = client.get("/api/rooms").json()  # no cookie at all
    assert [(r["name"], r["owner"], r["protected"]) for r in rooms] == [("Família", "Host", True), ("Sexta", "Host", False)]
    assert all("password" not in key for room in rooms for key in room)


def test_a_guest_makes_a_room_and_owns_it_even_after_joining_another(host, code, stranger):
    ana = stranger()
    assert ana.post(f"/api/rooms/{code}/join", json={"nickname": "Ana"}).status_code == 200
    made = ana.post("/api/rooms", json={"name": "Aniversário da Ana", "password": "bolo"})
    assert made.status_code == 201
    mine = made.json()["code"]
    other = host.post("/api/rooms", json={"name": "Outra"}).json()["code"]
    ana.post(f"/api/rooms/{other}/join", json={"nickname": "Ana"})  # the same phone token, in a third room
    info = ana.get(f"/api/rooms/{mine}").json()
    assert (info["owner"], info["mine"], info["manage"], info["protected"]) == ("Ana", True, True, True)
    assert not ana.get(f"/api/rooms/{other}").json()["mine"]


def test_a_visitor_in_no_room_makes_one_with_a_nickname_and_owns_it(app, stranger):
    bia = stranger()
    refused = bia.post("/api/rooms", json={"name": "Da Bia", "nickname": "  "})
    assert refused.status_code == 422 and "apelido" in refused.json()["detail"]
    made = bia.post("/api/rooms", json={"name": "Da Bia", "nickname": "Bia"})
    assert made.status_code == 201, made.text
    code = made.json()["code"]
    room = bia.get(f"/api/rooms/{code}").json()
    assert (room["owner"], room["mine"], room["joined"], room["manage"]) == ("Bia", True, True, True)
    add(bia, code)  # already its guest: no join needed
    assert TestClient(app).get(f"/api/rooms/{code}").json()["mine"] is False  # another browser, no cookie


def test_an_address_makes_three_rooms_an_hour_and_the_host_is_not_counted(host, stranger):
    for n in range(3):
        assert stranger().post("/api/rooms", json={"name": f"Sala {n}", "nickname": "Ana"}).status_code == 201
    over = stranger().post("/api/rooms", json={"name": "Mais uma", "nickname": "Ana"})
    assert over.status_code == 429 and "Muitas salas" in over.json()["detail"]
    assert int(over.headers["retry-after"]) > 0
    assert host.post("/api/rooms", json={"name": "Do host"}).status_code == 201


def test_with_twenty_open_rooms_only_the_host_makes_another(host, stranger):
    for n in range(20):
        assert host.post("/api/rooms", json={"name": f"Sala {n}"}).status_code == 201
    full = stranger().post("/api/rooms", json={"name": "Lotada", "nickname": "Ana"})
    assert full.status_code == 429 and "20 salas abertas" in full.json()["detail"]
    assert host.post("/api/rooms", json={"name": "Do host, mesmo assim"}).status_code == 201


def test_a_room_with_a_password_asks_for_it_and_counts_wrong_ones(host, stranger):
    code = host.post("/api/rooms", json={"name": "Fechada", "password": "1234"}).json()["code"]
    bia = stranger()
    assert bia.post(f"/api/rooms/{code}/join", json={"nickname": "Bia"}).status_code == 401
    assert bia.post(f"/api/rooms/{code}/join", json={"nickname": "Bia", "password": "0000"}).json()["detail"] == "Senha incorreta."
    assert bia.post(f"/api/rooms/{code}/join", json={"nickname": "Bia", "password": "1234"}).status_code == 200
    assert bia.post(f"/api/rooms/{code}/join", json={"nickname": "Bia B"}).status_code == 200  # already in: no password
    for _ in range(5):  # a right password clears the count, so five wrong ones in a row
        stranger().post(f"/api/rooms/{code}/join", json={"nickname": "X", "password": "nope"})
    assert stranger().post(f"/api/rooms/{code}/join", json={"nickname": "X", "password": "1234"}).status_code == 429


def test_an_empty_password_makes_a_public_room(host):
    code = host.post("/api/rooms", json={"name": "Aberta", "password": ""}).json()["code"]
    assert not host.get(f"/api/rooms/{code}").json()["protected"]


def test_the_room_owner_runs_the_room_and_a_guest_only_their_songs(host, code, stranger):
    owner = stranger()
    owner.post(f"/api/rooms/{code}/join", json={"nickname": "Cris"})
    room = owner.post("/api/rooms", json={"name": "Da Cris"}).json()["code"]
    ana = stranger()
    ana.post(f"/api/rooms/{room}/join", json={"nickname": "Ana"})
    bia = stranger()
    bia.post(f"/api/rooms/{room}/join", json={"nickname": "Bia"})
    anas, bias = add(ana, room), add(bia, room, OTHER_VIDEO)

    # Ana: her own song only, and no reordering
    assert ana.patch(f"/api/rooms/{room}/queue/{anas}", json={"semitones": 2}).status_code == 200
    assert ana.patch(f"/api/rooms/{room}/queue/{bias}", json={"semitones": 2}).status_code == 403
    assert ana.patch(f"/api/rooms/{room}/queue/{bias}", json={"position": 0}).status_code == 403
    assert ana.post(f"/api/rooms/{room}/player/pause").status_code == 403
    # Cris, the owner: any song, the order and the player
    assert owner.patch(f"/api/rooms/{room}/queue/{bias}", json={"semitones": -1}).status_code == 200
    assert owner.patch(f"/api/rooms/{room}/queue/{bias}", json={"position": 0}).status_code == 200
    assert owner.post(f"/api/rooms/{room}/player/pause").status_code == 204
    assert owner.post(f"/api/rooms/{room}/player/guide", json={"value": 50}).status_code == 204
    assert owner.delete(f"/api/rooms/{room}/queue/{anas}").status_code == 204
    # ...but only in their room: in the host's room Cris is a guest like any other
    hosts_room_song = add(host, code)
    assert owner.delete(f"/api/rooms/{code}/queue/{hosts_room_song}").status_code == 403
    assert owner.delete(f"/api/rooms/{code}").status_code == 403


def test_a_room_is_removed_by_its_owner_or_the_host_only(host, code, stranger):
    owner = stranger()
    owner.post(f"/api/rooms/{code}/join", json={"nickname": "Cris"})
    room = owner.post("/api/rooms", json={"name": "Da Cris"}).json()["code"]
    ana = stranger()
    ana.post(f"/api/rooms/{room}/join", json={"nickname": "Ana"})
    assert ana.delete(f"/api/rooms/{room}").status_code == 403
    assert owner.delete(f"/api/rooms/{room}").status_code == 204
    assert ana.get(f"/api/rooms/{room}").status_code == 404
    assert room not in {r["code"] for r in host.get("/api/rooms").json()}
    another = owner.post("/api/rooms", json={"name": "De novo"}).json()["code"]  # still a guest of the host's room
    assert host.delete(f"/api/rooms/{another}").status_code == 204


def test_each_room_has_its_own_queue(host, code, stranger):
    other = host.post("/api/rooms", json={"name": "Outra"}).json()["code"]
    add(host, code)
    assert host.get(f"/api/rooms/{other}/queue").json() == []
    assert len(host.get(f"/api/rooms/{code}/queue").json()) == 1


def test_the_rooms_password_opens_its_tv_and_no_other(app, client, host, stranger):
    locked = host.post("/api/rooms", json={"name": "Fechada", "password": "1234"}).json()["code"]
    public = host.post("/api/rooms", json={"name": "Aberta"}).json()["code"]
    tv = stranger()
    assert tv.post(f"/api/rooms/{locked}/tv", json={}).status_code == 401
    assert tv.post(f"/api/rooms/{locked}/tv", json={"password": "1234"}).status_code == 204
    assert tv.get(f"/api/rooms/{locked}").json()["tv"]
    assert not tv.get(f"/api/rooms/{public}").json()["tv"]  # that cookie is for the locked room only
    assert tv.post(f"/api/rooms/{locked}/player/skip").status_code == 204
    with tv.websocket_connect(f"/ws/rooms/{locked}?role=tv") as ws:
        receive(ws, "queue.snapshot")
    # A room without a password has nothing to check: only its owner and the admin are its TV; TV_PIN opens all
    other_tv = stranger()
    assert other_tv.post(f"/api/rooms/{public}/tv", json={}).status_code == 403
    assert other_tv.post(f"/api/rooms/{public}/tv", json={"password": "qualquer"}).status_code == 403
    pin_tv = stranger()
    pin_tv.post("/api/tv/login", json={"pin": TV_PIN})
    assert pin_tv.get(f"/api/rooms/{locked}").json()["tv"] and pin_tv.get(f"/api/rooms/{public}").json()["tv"]


def test_the_owner_opens_the_tv_of_their_room_without_the_password(host, code, stranger):
    owner = stranger()
    owner.post(f"/api/rooms/{code}/join", json={"nickname": "Cris"})
    room = owner.post("/api/rooms", json={"name": "Da Cris", "password": "abc"}).json()["code"]
    assert owner.post(f"/api/rooms/{room}/tv", json={}).status_code == 204
    assert owner.get(f"/api/rooms/{room}").json()["tv"]
    public = owner.post("/api/rooms", json={"name": "Da Cris, aberta"}).json()["code"]
    assert owner.post(f"/api/rooms/{public}/tv", json={}).status_code == 204  # their room without a password too


def test_a_room_expires_after_24_hours_and_its_screens_are_told(app, client, host, code, db):
    with host.websocket_connect(f"/ws/rooms/{code}") as ws:
        receive(ws, "queue.snapshot")
        with transaction(db) as session:
            session.query(Room).filter(Room.code == code).one().expires_at = utcnow() - timedelta(seconds=1)
        # Expired already counts as closed, before the minute's sweep
        assert host.get(f"/api/rooms/{code}").status_code == 404
        assert code not in {r["code"] for r in host.get("/api/rooms").json()}
        assert client.portal.call(close_expired, app) == [1]  # the sweep, once, on the app's own loop
        with pytest.raises(WebSocketDisconnect) as gone:
            while True:
                ws.receive_json()
        assert gone.value.code == 4404
    with transaction(db) as session:
        assert not expire_rooms(session)  # nothing left to close


def test_a_new_room_lasts_24_hours(host, code, db):
    with transaction(db) as session:
        room = session.query(Room).filter(Room.code == code).one()
        assert timedelta(hours=23, minutes=59) < room.expires_at - room.created_at <= timedelta(hours=24)
