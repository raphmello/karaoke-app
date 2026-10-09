"""Phase 4 through the API: changing, removing, the transcription answer, the player and the room's WebSocket."""
import pytest
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from karaoke.core.db import transaction
from karaoke.core.models import Job, QueueEntry, Song, SongEvent

VIDEO, OTHER_VIDEO = "dQw4w9WgXcQ", "aaaaaaaaaaa"


def add(caller, code, video=VIDEO, **body):
    response = caller.post(f"/api/rooms/{code}/queue", json={"video_id": video, **body})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def set_status(db, video, status):
    with transaction(db) as session:
        session.get(Song, video).status = status


def entry(db, entry_id) -> QueueEntry:
    with db() as session:
        return session.get(QueueEntry, entry_id)


# --- the phase 4 criterion, first half ----------------------------------------------------------------------------

def test_one_phone_cannot_remove_the_others_song(phone, code, db):
    ana, bia = phone(code, "Ana"), phone(code, "Bia")
    anas = add(ana, code)

    assert bia.delete(f"/api/rooms/{code}/queue/{anas}").status_code == 403
    assert bia.patch(f"/api/rooms/{code}/queue/{anas}", json={"semitones": 2}).status_code == 403
    assert entry(db, anas).status == "queued"

    assert ana.delete(f"/api/rooms/{code}/queue/{anas}").status_code == 204
    removed = entry(db, anas)
    assert (removed.status, removed.removed_reason) == ("removed", "dono")  # logical: the row stays
    assert ana.get(f"/api/rooms/{code}/queue").json() == []
    assert ana.delete(f"/api/rooms/{code}/queue/{anas}").status_code == 409


def test_the_host_removes_anyones_entry(phone, host, code, db):
    anas = add(phone(code, "Ana"), code)
    assert host.delete(f"/api/rooms/{code}/queue/{anas}").status_code == 204
    assert entry(db, anas).removed_reason == "host"


def test_the_owner_changes_the_key_but_only_the_host_reorders(phone, host, code, db):
    ana = phone(code, "Ana")
    first, second, third = add(ana, code), add(ana, code, OTHER_VIDEO), add(host, code)

    assert ana.patch(f"/api/rooms/{code}/queue/{first}", json={"semitones": -3}).json()["semitones"] == -3
    assert ana.patch(f"/api/rooms/{code}/queue/{first}", json={"semitones": 7}).status_code == 422
    assert ana.patch(f"/api/rooms/{code}/queue/{second}", json={"position": 0}).status_code == 403

    assert host.patch(f"/api/rooms/{code}/queue/{third}", json={"position": 0}).status_code == 200
    assert [e["id"] for e in host.get(f"/api/rooms/{code}/queue").json()] == [third, first, second]
    host.patch(f"/api/rooms/{code}/queue/{third}", json={"position": 99})
    assert [e["id"] for e in host.get(f"/api/rooms/{code}/queue").json()] == [first, second, third]


def test_entries_of_another_room_are_not_found(phone, host, code):
    anas = add(phone(code, "Ana"), code)
    new_code = host.post("/api/rooms", json={}).json()["code"]
    assert host.delete(f"/api/rooms/{new_code}/queue/{anas}").status_code == 404


# --- the phase 4 criterion, second half ---------------------------------------------------------------------------

def test_no_takes_the_entry_out_and_removes_the_song_without_downloading(phone, code, db):
    ana, bia = phone(code, "Ana"), phone(code, "Bia")
    anas = add(ana, code)
    set_status(db, VIDEO, "awaiting_decision")
    with transaction(db) as session:
        session.get(QueueEntry, anas).status = "awaiting_decision"
        session.scalar(select(Job)).status = "done"  # the lyrics stage ended the job

    assert bia.post(f"/api/rooms/{code}/queue/{anas}/transcription", json={"accept": False}).status_code == 403
    assert ana.post(f"/api/rooms/{code}/queue/{anas}/transcription", json={"accept": False}).status_code == 204

    assert (entry(db, anas).status, entry(db, anas).removed_reason) == ("removed", "transcrição recusada")
    with db() as session:
        song = session.get(Song, VIDEO)
        assert (song.status, song.removed_reason) == ("removed", "transcrição recusada")
        assert session.scalars(select(Job.status)).all() == ["done"]  # no new job: nothing is downloaded
        kinds = session.scalars(select(SongEvent.kind).order_by(SongEvent.id)).all()
    assert kinds == ["created", "transcription_declined", "removed"]


def test_a_no_keeps_the_song_while_another_owner_still_waits(phone, code, db):
    ana, bia = phone(code, "Ana"), phone(code, "Bia")
    anas, bias = add(ana, code), add(bia, code)
    set_status(db, VIDEO, "awaiting_decision")
    with transaction(db) as session:
        for entry_id in (anas, bias):
            session.get(QueueEntry, entry_id).status = "awaiting_decision"

    ana.post(f"/api/rooms/{code}/queue/{anas}/transcription", json={"accept": False})
    with db() as session:
        assert session.get(Song, VIDEO).status == "awaiting_decision"


def test_yes_starts_a_transcription_for_every_waiting_entry(phone, code, db):
    ana, bia = phone(code, "Ana"), phone(code, "Bia")
    anas, bias = add(ana, code), add(bia, code)
    set_status(db, VIDEO, "awaiting_decision")
    with transaction(db) as session:
        session.scalar(select(Job)).status = "done"
        for entry_id in (anas, bias):
            session.get(QueueEntry, entry_id).status = "awaiting_decision"

    assert bia.post(f"/api/rooms/{code}/queue/{bias}/transcription", json={"accept": True}).status_code == 204
    assert {entry(db, anas).status, entry(db, bias).status} == {"queued"}
    with db() as session:
        assert session.get(Song, VIDEO).status == "pending"
        job = session.scalar(select(Job).where(Job.status == "pending"))
    assert job.options == {"transcribe": True}
    assert bia.post(f"/api/rooms/{code}/queue/{bias}/transcription", json={"accept": True}).status_code == 409


# --- rooms and player ---------------------------------------------------------------------------------------------

def test_the_tv_finds_the_active_room(phone, host, code):
    room = host.get("/api/rooms/active").json()
    assert room["code"] == code and room["join_path"] == f"/j/{code}" and room["public_base_url"] == ""
    assert phone(code, "Ana").get("/api/rooms/active").status_code == 401


def test_only_the_host_controls_the_player(phone, host, code):
    ana = phone(code, "Ana")
    assert ana.post(f"/api/rooms/{code}/player/pause").status_code == 403
    assert host.post(f"/api/rooms/{code}/player/pause").status_code == 204
    assert host.post(f"/api/rooms/{code}/player/explode").status_code == 404


# --- WebSocket ----------------------------------------------------------------------------------------------------

def receive(ws, kind):
    while True:
        message = ws.receive_json()
        if message["type"] == kind:
            return message


def test_the_socket_needs_a_cookie_of_the_room(client, host, code):
    with pytest.raises(WebSocketDisconnect) as closed, client.websocket_connect(f"/ws/rooms/{code}") as ws:
        ws.receive_json()
    assert closed.value.code == 4401


def test_screens_get_the_queue_on_connect_and_on_every_change(phone, host, code):
    ana = phone(code, "Ana")
    with ana.websocket_connect(f"/ws/rooms/{code}") as ws:
        assert receive(ws, "queue.snapshot")["entries"] == []
        add(ana, code)
        entries = receive(ws, "queue.snapshot")["entries"]
        assert [(e["video_id"], e["mine"]) for e in entries] == [(VIDEO, True)]


def test_the_tv_reports_what_plays_and_the_previous_entry_is_done(phone, host, code, db):
    ana = phone(code, "Ana")
    first, second = add(ana, code), add(ana, code, OTHER_VIDEO)
    with host.websocket_connect(f"/ws/rooms/{code}?role=tv") as tv, ana.websocket_connect(f"/ws/rooms/{code}") as ws:
        receive(ws, "queue.snapshot")
        tv.send_json({"type": "player.state", "entry_id": first, "position": 1.5, "paused": False, "semitones": -1})
        assert receive(ws, "queue.snapshot")["entries"][0]["status"] == "playing"
        state = receive(ws, "player.state")
        assert (state["entry_id"], state["semitones"]) == (first, -1)

        tv.send_json({"type": "player.state", "entry_id": second, "position": 0, "paused": False, "semitones": 0})
        receive(ws, "player.state")
    assert entry(db, first).status == "done"
    assert entry(db, second).status == "playing"


def test_a_phone_cannot_pretend_to_be_the_tv(phone, host, code, db):
    ana = phone(code, "Ana")
    anas = add(ana, code)
    with ana.websocket_connect(f"/ws/rooms/{code}?role=tv") as ws:
        receive(ws, "queue.snapshot")
        ws.send_json({"type": "player.state", "entry_id": anas})
    assert entry(db, anas).status == "queued"


def test_commands_reach_only_the_tv(phone, host, code, db):
    ana = phone(code, "Ana")
    anas = add(ana, code)
    with host.websocket_connect(f"/ws/rooms/{code}?role=tv") as tv:
        receive(tv, "queue.snapshot")
        tv.send_json({"type": "player.state", "entry_id": anas, "position": 3, "paused": False, "semitones": 0})
        receive(tv, "queue.snapshot")

        ana.patch(f"/api/rooms/{code}/queue/{anas}", json={"semitones": 2})
        assert receive(tv, "player.command") == {"type": "player.command", "action": "key", "semitones": 2}

        host.post(f"/api/rooms/{code}/player/skip")
        assert receive(tv, "player.command")["action"] == "skip"
    assert entry(db, anas).status == "skipped"


def test_removing_the_song_that_plays_skips_it(phone, host, code, db):
    ana = phone(code, "Ana")
    anas = add(ana, code)
    with host.websocket_connect(f"/ws/rooms/{code}?role=tv") as tv:
        tv.send_json({"type": "player.state", "entry_id": anas, "position": 3, "paused": False, "semitones": 0})
        receive(tv, "queue.snapshot")
        assert ana.delete(f"/api/rooms/{code}/queue/{anas}").status_code == 204
        assert receive(tv, "player.command")["action"] == "skip"


def test_the_lyrics_question_goes_only_to_the_owner_and_the_host(phone, host, code, db):
    ana, bia = phone(code, "Ana"), phone(code, "Bia")
    anas = add(ana, code)
    with (
        ana.websocket_connect(f"/ws/rooms/{code}") as ana_ws,
        bia.websocket_connect(f"/ws/rooms/{code}") as bia_ws,
        host.websocket_connect(f"/ws/rooms/{code}") as host_ws,
    ):
        host.post("/internal/events", json={"type": "song.lyrics_missing", "video_id": VIDEO, "entries": [anas]})
        assert receive(ana_ws, "song.lyrics_missing")["entries"] == [anas]
        assert receive(host_ws, "song.lyrics_missing")["entries"] == [anas]
        host.post("/internal/events", json={"type": "song.progress", "video_id": VIDEO, "stage": "x", "progress": 1})
        assert receive(bia_ws, "song.progress")["progress"] == 1  # Bia saw progress, but never the question


def test_adding_a_song_that_waits_asks_the_new_owner(phone, host, code, db):
    ana, bia = phone(code, "Ana"), phone(code, "Bia")
    add(ana, code)
    set_status(db, VIDEO, "awaiting_decision")
    with bia.websocket_connect(f"/ws/rooms/{code}") as ws:
        bias = add(bia, code)
        assert receive(ws, "song.lyrics_missing")["entries"] == [bias]


# --- a new room while the old one is in use -----------------------------------------------------------------------

def test_a_new_room_tells_the_old_rooms_screens_and_finishes_what_played(phone, host, code, db):
    ana = phone(code, "Ana")
    playing, waiting = add(ana, code), add(ana, code, OTHER_VIDEO)
    with host.websocket_connect(f"/ws/rooms/{code}?role=tv") as tv, ana.websocket_connect(f"/ws/rooms/{code}") as ws:
        tv.send_json({"type": "player.state", "entry_id": playing, "position": 30, "paused": False, "semitones": 0})
        receive(ws, "player.state")
        new = host.post("/api/rooms", json={"name": "Nova"}).json()["code"]
        for socket in (tv, ws):
            with pytest.raises(WebSocketDisconnect) as closed:
                while True:
                    socket.receive_json()
            assert closed.value.code == 4404
    assert entry(db, playing).status == "done"
    assert (entry(db, waiting).status, entry(db, waiting).room_id) == ("queued", 1)  # stays behind, in the old room
    assert host.get(f"/api/rooms/{new}/queue").json() == []


def test_the_queue_can_move_to_the_new_room_where_only_the_host_removes_it(phone, host, code, db):
    ana = phone(code, "Ana")
    first, second = add(ana, code), add(ana, code, OTHER_VIDEO)
    new = host.post("/api/rooms", json={"move_queue": True}).json()["code"]

    moved = host.get(f"/api/rooms/{new}/queue").json()
    assert [(e["id"], e["position"], e["added_by"]) for e in moved] == [(first, 1, "Ana"), (second, 2, "Ana")]
    ana_again = phone(new, "Ana")  # back through the new QR: a new guest
    assert not ana_again.get(f"/api/rooms/{new}/queue").json()[0]["mine"]
    assert ana_again.delete(f"/api/rooms/{new}/queue/{first}").status_code == 403
    assert host.delete(f"/api/rooms/{new}/queue/{first}").status_code == 204


# --- the 10-minute limit -------------------------------------------------------------------------------------------

def test_a_video_too_long_for_the_tv_is_refused_when_its_length_is_known(phone, code, db):
    with transaction(db) as session:  # a long interview already in the library
        session.add(Song(video_id=OTHER_VIDEO, title="Entrevista", status="ready", duration_s=1648))
    response = phone(code, "Ana").post(f"/api/rooms/{code}/queue", json={"video_id": OTHER_VIDEO})
    assert response.status_code == 422
    assert response.json()["detail"] == "Vídeo longo demais para o karaokê (27 min; o limite é 10 min)."
    with db() as session:
        assert session.scalar(select(QueueEntry).where(QueueEntry.video_id == OTHER_VIDEO)) is None


def test_the_search_tells_the_length_before_anything_is_created(app, client, phone, code, db):
    client.app.state.search._search = lambda q: [
        {"video_id": VIDEO, "title": "Ao vivo", "channel": "C", "duration_s": 1673, "thumbnail_url": "t"}
    ]
    ana = phone(code, "Ana")
    ana.get("/api/search", params={"q": "ao vivo"})
    assert ana.post(f"/api/rooms/{code}/queue", json={"video_id": VIDEO}).status_code == 422
    with db() as session:
        assert session.get(Song, VIDEO) is None and session.scalar(select(Job)) is None  # nothing to process



def test_a_refusal_says_who_may_remove_the_song(phone, host, code):
    ana, bruno = phone(code, "Ana"), phone(code, "Bruno")
    anas, hosts = add(ana, code), add(host, code, OTHER_VIDEO)
    refused = bruno.delete(f"/api/rooms/{code}/queue/{anas}")
    assert refused.status_code == 403
    assert refused.json()["detail"] == "Só Ana, que adicionou esta música, ou o host podem remover esta música."
    key = bruno.patch(f"/api/rooms/{code}/queue/{anas}", json={"semitones": 2}).json()["detail"]
    assert key == "Só Ana, que adicionou esta música, ou o host podem mudar o tom desta música."
    assert bruno.delete(f"/api/rooms/{code}/queue/{hosts}").json()["detail"] == "Só o host pode remover esta música."


def test_the_song_that_plays_keeps_its_place(phone, host, code, db):
    ana = phone(code, "Ana")
    first, second = add(ana, code), add(ana, code, OTHER_VIDEO)
    with host.websocket_connect(f"/ws/rooms/{code}?role=tv") as tv:
        receive(tv, "queue.snapshot")
        tv.send_json({"type": "player.state", "entry_id": first, "position": 1, "paused": False, "semitones": 0})
        receive(tv, "queue.snapshot")
    assert host.patch(f"/api/rooms/{code}/queue/{first}", json={"position": 1}).status_code == 409
    # The next one cannot go above it either: asked to be first, it stays right below what plays
    assert host.patch(f"/api/rooms/{code}/queue/{second}", json={"position": 0}).status_code == 200
    assert [e["id"] for e in host.get(f"/api/rooms/{code}/queue").json()] == [first, second]
