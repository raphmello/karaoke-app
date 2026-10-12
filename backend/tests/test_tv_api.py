"""A room's TV (docs/ARCHITECTURE.md, "Como alguém entra"): opened by the room's owner or the admin, it plays the
queue and adds songs, and nothing of /host."""
from fastapi.testclient import TestClient
from helpers import PIN, Caller, cookie_of

VIDEO = "dQw4w9WgXcQ"


def add(caller, code, video=VIDEO, **body):
    response = caller.post(f"/api/rooms/{code}/queue", json={"video_id": video, **body})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def receive(ws, kind):
    while True:
        message = ws.receive_json()
        if message["type"] == kind:
            return message


def test_there_is_no_tv_pin_any_more(client):
    # Only the room's owner and the admin open a room's TV (docs/ARCHITECTURE.md, "Como alguém entra")
    assert client.post("/api/tv/login", json={"pin": "8765"}).status_code in (404, 405)


def test_an_old_tv_cookie_for_every_room_opens_nothing(app, client, code):
    old = Caller(client, f"karaoke_tv={app.state.host_signer.issue_tv('all')}")
    assert not old.get(f"/api/rooms/{code}").json()["tv"]
    assert old.post(f"/api/rooms/{code}/player/pause").status_code == 401


def test_the_tv_finds_the_room_and_plays_the_queue(tv, phone, code, db):
    assert tv.get(f"/api/rooms/{code}").json()["tv"]
    ana = phone(code, "Ana")
    anas = add(ana, code)
    with tv.websocket_connect(f"/ws/rooms/{code}?role=tv") as ws:
        receive(ws, "queue.snapshot")
        ws.send_json({"type": "player.state", "entry_id": anas, "position": 1, "paused": False, "semitones": 0})
        assert receive(ws, "queue.snapshot")["entries"][0]["status"] == "playing"
        assert tv.patch(f"/api/rooms/{code}/queue/{anas}", json={"semitones": -2}).status_code == 200
        assert receive(ws, "player.command") == {"type": "player.command", "action": "key", "semitones": -2}
        assert tv.post(f"/api/rooms/{code}/player/pause").status_code == 204
        assert tv.post(f"/api/rooms/{code}/player/skip").status_code == 204


def test_the_tv_changes_only_the_key_of_the_song_that_plays(tv, phone, code):
    ana = phone(code, "Ana")
    waiting = add(ana, code)
    assert tv.patch(f"/api/rooms/{code}/queue/{waiting}", json={"semitones": 2}).status_code == 403


def test_the_phone_that_is_the_tv_can_also_join_and_sing(app, client, tv, phone, code):
    # An iPhone mirrored to the TV: it is the room's TV, then it reads the QR and joins as a guest
    joined = TestClient(app).post(f"/api/rooms/{code}/join", json={"nickname": "Raphael"}, headers=tv.headers)
    assert joined.status_code == 200
    both = Caller(client, f"{tv.headers['cookie']}; {cookie_of(joined)}")
    mine = add(both, code)
    assert both.get(f"/api/rooms/{code}/queue").json()[0]["mine"]
    assert both.patch(f"/api/rooms/{code}/queue/{mine}", json={"semitones": 1}).status_code == 200
    assert both.get(f"/api/rooms/{code}").json()["tv"]  # still the TV
    assert both.post(f"/api/rooms/{code}/player/pause").status_code == 204
    anas = add(phone(code, "Ana"), code)
    assert both.delete(f"/api/rooms/{code}/queue/{anas}").status_code == 403  # not someone else's
    assert both.delete(f"/api/rooms/{code}/queue/{mine}").status_code == 204


def test_the_tv_owns_the_songs_it_adds(tv, phone, host, code, db):
    # The TV's menu: "Adicionar Música". The TV owns what it adds, through the room's "TV" guest: it changes the key
    # and removes it; a guest cannot, and the refusal names the TV
    entry_id = add(tv, code, singer_name="Vó Maria")
    entries = tv.get(f"/api/rooms/{code}/queue").json()
    assert [(e["singer_name"], e["added_by"], e["mine"]) for e in entries] == [("Vó Maria", "TV", True)]
    assert tv.patch(f"/api/rooms/{code}/queue/{entry_id}", json={"semitones": -2}).status_code == 200
    ana = phone(code, "Ana")
    refused = ana.delete(f"/api/rooms/{code}/queue/{entry_id}")
    assert refused.status_code == 403 and refused.json()["detail"].startswith("Só a TV, que adicionou")
    assert not ana.get(f"/api/rooms/{code}/queue").json()[0]["mine"]
    assert tv.delete(f"/api/rooms/{code}/queue/{entry_id}").status_code == 204
    hosts = add(tv, code)
    assert host.delete(f"/api/rooms/{code}/queue/{hosts}").status_code == 204  # the host still may


def test_the_tv_still_cannot_touch_a_guests_song(tv, phone, code):
    anas = add(phone(code, "Ana"), code)
    assert tv.delete(f"/api/rooms/{code}/queue/{anas}").status_code == 403
    assert tv.patch(f"/api/rooms/{code}/queue/{anas}", json={"semitones": 1}).status_code == 403
    assert not tv.get(f"/api/rooms/{code}/queue").json()[0]["mine"]


def test_leaving_the_admin_drops_the_host_cookie_and_keeps_the_tv(app, client, tv, code):
    # The TV unlocks Acervo and Painel with the host's PIN, then "Sair do admin"
    host_login = TestClient(app).post("/api/host/login", json={"pin": PIN})
    both = Caller(client, f"{tv.headers['cookie']}; {cookie_of(host_login)}")
    assert both.get("/api/jobs").status_code == 200
    out = both.post("/api/host/logout")
    assert out.status_code == 204 and 'karaoke_host=""' in out.headers["set-cookie"] and "Max-Age=0" in out.headers["set-cookie"]
    tv_only = tv  # what the browser keeps
    assert tv_only.get("/api/jobs").status_code == 401
    assert tv_only.get(f"/api/rooms/{code}").json()["tv"]


def test_the_tv_cannot_do_what_belongs_to_the_host_or_the_guests(tv, phone, code):
    ana = phone(code, "Ana")
    anas = add(ana, code)
    assert tv.post("/api/rooms", json={"name": "Da TV"}).status_code == 422  # like anyone, with a nickname only
    assert tv.delete(f"/api/rooms/{code}/queue/{anas}").status_code == 403
    assert tv.patch(f"/api/rooms/{code}/queue/{anas}", json={"position": 1}).status_code == 403
    assert tv.post(f"/api/rooms/{code}/player/guide", json={"value": 50}).status_code == 403
    assert tv.get("/api/jobs").status_code == 401
    assert tv.get("/api/disk").status_code == 401
    assert tv.get("/api/library?removed=true").status_code in (401, 403)
    assert tv.post(f"/api/songs/{VIDEO}/reprocess", json={"stages": []}).status_code in (401, 403)
