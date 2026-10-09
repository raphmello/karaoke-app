"""The TV's own PIN (docs/ARCHITECTURE.md, "Como alguém entra"): it plays the queue and adds songs, and nothing of
/host."""
from fastapi.testclient import TestClient
from helpers import PIN, TV_PIN, Caller, cookie_of

from karaoke.api.app import create_app
from karaoke.core.config import Settings

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


def test_the_tv_pin_gives_the_tvs_cookie_and_the_hosts_pin_the_hosts(client):
    tv = client.post("/api/tv/login", json={"pin": TV_PIN})
    assert tv.status_code == 204 and "karaoke_tv=" in tv.headers["set-cookie"]
    host = client.post("/api/tv/login", json={"pin": PIN})
    assert host.status_code == 204 and "karaoke_host=" in host.headers["set-cookie"]
    assert client.post("/api/tv/login", json={"pin": "0000"}).status_code == 401


def test_the_tv_pin_does_not_open_the_hosts_login(client):
    assert client.post("/api/host/login", json={"pin": TV_PIN}).status_code == 401


def test_wrong_pins_on_both_screens_count_together(client):
    for path in ["/api/tv/login", "/api/host/login"] * 2 + ["/api/tv/login"]:
        assert client.post(path, json={"pin": "0000"}).status_code == 401
    assert client.post("/api/tv/login", json={"pin": TV_PIN}).status_code == 429


def test_without_a_tv_pin_only_the_hosts_pin_opens_the_tv(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, host_pin=PIN), search=lambda q: [])
    with TestClient(app) as client:
        assert client.post("/api/tv/login", json={"pin": ""}).status_code == 401
        assert client.post("/api/tv/login", json={"pin": PIN}).status_code == 204


def test_the_tv_finds_the_room_and_plays_the_queue(tv, phone, code, db):
    assert tv.get("/api/rooms/active").json()["code"] == code
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


def test_the_phone_that_is_the_tv_can_also_join_and_sing(app, client, phone, code):
    # An iPhone mirrored to the TV: logged in with TV_PIN, then it reads the QR and joins as a guest
    login = TestClient(app).post("/api/tv/login", json={"pin": TV_PIN})
    joined = TestClient(app).post(f"/api/rooms/{code}/join", json={"nickname": "Raphael"},
                                  headers={"cookie": cookie_of(login)})
    assert joined.status_code == 200
    both = Caller(client, f"{cookie_of(login)}; {cookie_of(joined)}")
    mine = add(both, code)
    assert both.get(f"/api/rooms/{code}/queue").json()[0]["mine"]
    assert both.patch(f"/api/rooms/{code}/queue/{mine}", json={"semitones": 1}).status_code == 200
    assert both.get("/api/rooms/active").json()["code"] == code  # still the TV
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


def test_leaving_the_admin_drops_the_host_cookie_and_keeps_the_tv(app, client, code):
    # The TV unlocks Acervo and Painel with the host's PIN, then "Sair do admin"
    tv_login = TestClient(app).post("/api/tv/login", json={"pin": TV_PIN})
    host_login = TestClient(app).post("/api/host/login", json={"pin": PIN})
    both = Caller(client, f"{cookie_of(tv_login)}; {cookie_of(host_login)}")
    assert both.get("/api/jobs").status_code == 200
    out = both.post("/api/host/logout")
    assert out.status_code == 204 and 'karaoke_host=""' in out.headers["set-cookie"] and "Max-Age=0" in out.headers["set-cookie"]
    tv_only = Caller(client, cookie_of(tv_login))  # what the browser keeps
    assert tv_only.get("/api/jobs").status_code == 401
    assert tv_only.get("/api/rooms/active").json()["code"] == code


def test_the_tv_cannot_do_what_belongs_to_the_host_or_the_guests(tv, phone, code):
    ana = phone(code, "Ana")
    anas = add(ana, code)
    assert tv.post("/api/rooms", json={}).status_code == 401
    assert tv.delete(f"/api/rooms/{code}/queue/{anas}").status_code == 403
    assert tv.patch(f"/api/rooms/{code}/queue/{anas}", json={"position": 1}).status_code == 403
    assert tv.post(f"/api/rooms/{code}/player/guide", json={"value": 50}).status_code == 403
    assert tv.get("/api/jobs").status_code == 401
    assert tv.get("/api/disk").status_code == 401
    assert tv.get("/api/library?removed=true").status_code in (401, 403)
    assert tv.post(f"/api/songs/{VIDEO}/reprocess", json={"stages": []}).status_code in (401, 403)
