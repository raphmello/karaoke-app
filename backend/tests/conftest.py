import pytest
from helpers import PIN

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
