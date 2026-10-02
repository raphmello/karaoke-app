"""Alembic environment. The schema lives in karaoke.core.models; the database is the one in KARAOKE_DATA."""
from alembic import context

from karaoke.core.config import load_settings
from karaoke.core.db import make_engine
from karaoke.core.models import Base


def run(connection) -> None:
    # render_as_batch: SQLite can't ALTER most things, so changes rebuild the table
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    run(connection)
else:
    with make_engine(load_settings().database_url).begin() as connection:
        run(connection)
