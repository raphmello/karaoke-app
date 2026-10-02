"""The REST API of phase 2, through FastAPI's test client, with a stand-in YouTube search."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from helpers import PIN
from sqlalchemy import func, select

from karaoke.api.app import create_app
from karaoke.core.db import make_engine, make_sessionmaker, transaction
from karaoke.core.models import READY, Job, QueueEntry, Room, Song

VIDEO = "dQw4w9WgXcQ"


class FakeSearch:
    def __init__(self):
        self.queries: list[str] = []

    def __call__(self, query):
        self.queries.append(query)
        return [
            {"video_id": VIDEO, "title": "Never Gonna Give You Up", "channel": "Rick Astley", "duration_s": 213,
             "thumbnail_url": f"https://i.ytimg.com/vi/{VIDEO}/hqdefault.jpg"},
            {"video_id": "aaaaaaaaaaa", "title": "Outra", "channel": "Canal", "duration_s": 100,
             "thumbnail_url": "https://i.ytimg.com/vi/aaaaaaaaaaa/hqdefault.jpg"},
        ]


@pytest.fixture
def search():
    return FakeSearch()


@pytest.fixture
def app(settings, search):
    return create_app(settings, search=search)


@pytest.fixture
def client(app):
    with TestClient(app) as client:  # runs the lifespan: the migrations
        yield client


@pytest.fixture
def db(settings, client):
    engine = make_engine(settings.database_url)
    yield make_sessionmaker(engine)
    engine.dispose()


def new_client(app) -> TestClient:
    return TestClient(app)


def host(client) -> TestClient:
    assert client.post("/api/host/login", json={"pin": PIN}).status_code == 204
    return client


def open_room(client) -> str:
    response = client.post("/api/rooms", json={"name": "Sexta"})
    assert response.status_code == 201
    return response.json()["code"]


def guest(app, code, nickname="Ana") -> TestClient:
    phone = new_client(app)
    response = phone.post(f"/api/rooms/{code}/join", json={"nickname": nickname})
    assert response.status_code == 200, response.text
    return phone


# --- who may call --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/api/library", "/api/search?q=x", f"/api/songs/{VIDEO}", "/api/rooms/ABC234/queue"])
def test_without_a_cookie_nothing_is_answered(client, path):
    assert client.get(path).status_code in (401, 404)


def test_the_host_logs_in_with_the_pin(client):
    assert client.post("/api/host/login", json={"pin": "0000"}).status_code == 401
    response = client.post("/api/host/login", json={"pin": PIN})
    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert "karaoke_host=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert "Secure" not in cookie  # plain HTTP on the home network


def test_without_host_pin_nobody_is_the_host(settings, search):
    app = create_app(settings.__class__(data_dir=settings.data_dir, host_pin=""), search=search)
    with TestClient(app) as client:
        assert client.post("/api/host/login", json={"pin": ""}).status_code == 401


def test_only_the_host_opens_a_room(app, client):
    code = open_room(host(client))
    phone = guest(app, code)
    assert phone.post("/api/rooms", json={}).status_code == 401


def test_a_new_room_closes_the_old_one(app, client):
    old = open_room(host(client))
    phone = guest(app, old)
    new = open_room(client)
    assert old != new and len(new) == 6
    assert phone.get(f"/api/rooms/{old}/queue").status_code == 404
    assert phone.get("/api/library").status_code == 401  # the old room's cookie is worthless now
    assert new_client(app).post(f"/api/rooms/{old}/join", json={"nickname": "Bia"}).status_code == 404


def test_a_guest_of_another_room_is_kept_out(app, client, db):
    code = open_room(host(client))
    phone = guest(app, code)
    with transaction(db) as session:
        session.add(Room(code="ZZZ999", host_pin_hash="x"))  # a second active room, which v1 never opens
    assert phone.get("/api/rooms/ZZZ999/queue").status_code == 403


def test_joining_again_keeps_the_same_guest(app, client):
    code = open_room(host(client))
    phone = guest(app, code)
    first = phone.post(f"/api/rooms/{code}/join", json={"nickname": "Ana"}).json()
    second = phone.post(f"/api/rooms/{code}/join", json={"nickname": "Ana Paula"}).json()
    assert first["id"] == second["id"] and second["nickname"] == "Ana Paula"


def test_a_blank_nickname_is_refused(app, client):
    code = open_room(host(client))
    assert new_client(app).post(f"/api/rooms/{code}/join", json={"nickname": "   "}).status_code == 422


# --- queue ---------------------------------------------------------------------------------------------------------

def test_guests_add_and_see_the_queue(app, client, db):
    code = open_room(host(client))
    ana, bia = guest(app, code, "Ana"), guest(app, code, "Bia")

    response = ana.post(f"/api/rooms/{code}/queue", json={"video_id": f"https://youtu.be/{VIDEO}", "semitones": -2})
    assert response.status_code == 201, response.text
    entry = response.json()
    assert entry["video_id"] == VIDEO and entry["singer_name"] == "Ana" and entry["semitones"] == -2
    assert entry["mine"] and entry["added_by"] == "Ana" and entry["song"]["status"] == "pending"

    bia.post(f"/api/rooms/{code}/queue", json={"video_id": VIDEO, "singer_name": "Bia e Caio"})
    queue = bia.get(f"/api/rooms/{code}/queue").json()
    assert [(e["singer_name"], e["mine"]) for e in queue] == [("Ana", False), ("Bia e Caio", True)]
    assert [e["mine"] for e in client.get(f"/api/rooms/{code}/queue").json()] == [False, False]  # the host's view
    with db() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 1


def test_adding_the_same_video_five_times_at_once_creates_one_job(app, client, db):
    """The phase 2 criterion, through the API: five phones press "add" at the same moment."""
    code = open_room(host(client))
    phones = [guest(app, code, f"Pessoa {i}") for i in range(5)]

    with ThreadPoolExecutor(5) as pool:
        responses = list(pool.map(lambda p: p.post(f"/api/rooms/{code}/queue", json={"video_id": VIDEO}), phones))

    assert [r.status_code for r in responses] == [201] * 5
    with db() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 1
        assert session.scalar(select(func.count()).select_from(QueueEntry)) == 5
        assert session.scalar(select(func.count()).select_from(Song)) == 1


@pytest.mark.parametrize("body", [{"video_id": "não é um vídeo"}, {"video_id": VIDEO, "semitones": 7},
                                  {"video_id": VIDEO, "semitones": -7}])
def test_bad_entries_are_refused(app, client, body):
    code = open_room(host(client))
    assert guest(app, code).post(f"/api/rooms/{code}/queue", json=body).status_code == 422


# --- songs ---------------------------------------------------------------------------------------------------------

def make_ready(db, video=VIDEO, title="Never Gonna Give You Up", artist="Rick Astley"):
    with transaction(db) as session:
        session.add(Song(video_id=video, title=title, artist=artist, status=READY))


def test_search_marks_what_is_in_the_library_and_caches_terms(app, client, db, search):
    code = open_room(host(client))
    phone = guest(app, code)
    make_ready(db)

    results = phone.get("/api/search", params={"q": "Rick  Astley"}).json()
    assert [(r["video_id"], r["in_library"]) for r in results] == [(VIDEO, True), ("aaaaaaaaaaa", False)]
    phone.get("/api/search", params={"q": "rick astley"})
    assert search.queries == ["rick astley"]  # the second search came from the cache


def test_a_song_shows_its_status_and_media(app, client, db):
    code = open_room(host(client))
    phone = guest(app, code)
    assert phone.get(f"/api/songs/{VIDEO}").status_code == 404
    assert phone.get("/api/songs/..%2F..%2Fetc").status_code == 404
    make_ready(db)

    song = phone.get(f"/api/songs/{VIDEO}").json()
    assert song["status"] == "ready"
    assert song["media"]["instrumental"] == f"/media/{VIDEO}/play/instrumental.opus"
    assert song["media"]["lyrics"] == f"/media/{VIDEO}/lyrics/aligned.json"


def test_the_library_lists_only_ready_songs(app, client, db):
    code = open_room(host(client))
    phone = guest(app, code)
    make_ready(db)
    make_ready(db, "aaaaaaaaaaa", "Garota de Ipanema", "Tom Jobim")
    with transaction(db) as session:
        session.add(Song(video_id="bbbbbbbbbbb", title="Removida", status="removed"))
        session.add(Song(video_id="ccccccccccc", title="Processando", status="processing"))

    assert [s["title"] for s in phone.get("/api/library").json()] == ["Never Gonna Give You Up", "Garota de Ipanema"]
    assert [s["title"] for s in phone.get("/api/library", params={"q": "jobim ipanema"}).json()] == [
        "Garota de Ipanema"]


def test_the_worker_reports_events(client):
    response = client.post("/internal/events", json={"type": "song.progress", "video_id": VIDEO, "stage": "lyrics",
                                                     "progress": 14})
    assert response.status_code == 204
