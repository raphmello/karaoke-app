"""SQLite in WAL mode, shared by the API and the worker.

Every transaction starts with BEGIN IMMEDIATE: it takes the write lock up front, so two writers queue up instead
of both reading and then failing to upgrade to a write ("database is locked"). At this app's scale (one host, a
few phones, one worker) serializing writes costs nothing and removes every race, including the one in
"add the same video five times at once". Transactions must stay short: nothing slow (YouTube, the GPU) runs
inside one.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def make_engine(url: str) -> Engine:
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, _record):
        dbapi_connection.isolation_level = None  # SQLAlchemy, not pysqlite, decides when transactions begin
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    @event.listens_for(engine, "begin")
    def _on_begin(connection):
        connection.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


def make_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@contextmanager
def transaction(factory: sessionmaker[Session]) -> Iterator[Session]:
    """One unit of work: commits on success, rolls back on error."""
    with factory() as session, session.begin():
        yield session


def migrate(engine: Engine) -> None:
    """Bring the schema to the newest migration. The API and the worker both call it at start; it is idempotent,
    and BEGIN IMMEDIATE keeps two of them from running it at the same time.

    SQLite changes a table by rebuilding it, and a rebuild of a table others point at (guests, in 0002) trips the
    foreign keys halfway. As SQLite prescribes, they are off while migrating, which only works outside a
    transaction; before the commit, foreign_key_check confirms nothing was left pointing nowhere."""
    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    with engine.connect() as connection:
        raw = connection.connection.driver_connection  # pysqlite, outside SQLAlchemy's transaction
        raw.execute("PRAGMA foreign_keys=OFF")
        try:
            with connection.begin():
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
                broken = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
                if broken:
                    raise RuntimeError(f"a migração deixou chaves estrangeiras quebradas: {broken[:5]}")
        finally:
            raw.execute("PRAGMA foreign_keys=ON")
