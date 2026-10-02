import pytest
from fastapi.testclient import TestClient
from helpers import PIN, Caller, cookie_of

from karaoke.api.app import create_app
from karaoke.core.config import Settings
from karaoke.core.db import make_engine, make_sessionmaker, migrate
from karaoke.core.models import Room


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path, host_pin=PIN)


@pytest.fixture
def db(settings):
    """A migrated database file in the test's folder, as the API and the worker see it."""
    engine = make_engine(settings.database_url)
    migrate(engine)
    yield make_sessionmaker(engine)
    engine.dispose()


@pytest.fixture
def room(db) -> Room:
    with db() as session, session.begin():
        room = Room(code="ABC234", host_pin_hash="x")
        session.add(room)
    return room


# --- the API through one client (see helpers.Caller) ---

@pytest.fixture
def app(settings):
    return create_app(settings, search=lambda q: [])


@pytest.fixture
def client(app):
    with TestClient(app) as client:  # runs the lifespan; never logs in itself, so its cookie jar stays empty
        yield client


@pytest.fixture
def host(app, client):
    login = TestClient(app).post("/api/host/login", json={"pin": PIN})
    assert login.status_code == 204
    return Caller(client, cookie_of(login))


@pytest.fixture
def code(host):
    return host.post("/api/rooms", json={"name": "Sexta"}).json()["code"]


@pytest.fixture
def phone(app, client):
    def join(code, nickname) -> Caller:
        response = TestClient(app).post(f"/api/rooms/{code}/join", json={"nickname": nickname})
        assert response.status_code == 200
        return Caller(client, cookie_of(response))

    return join
