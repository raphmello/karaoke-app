"""many rooms: an owner, an optional password and an expiry per room; a guest's token unique per room

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-09
"""
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROOM_LIFETIME = timedelta(hours=24)


def upgrade() -> None:
    # rooms: new columns only, so the table (which guests and queue_entries point at) stays as it is
    op.add_column("rooms", sa.Column("owner_guest_id", sa.String(length=36), nullable=True))
    op.add_column("rooms", sa.Column("password_hash", sa.Text(), nullable=True))
    op.add_column("rooms", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    # The room open now is the host's, public, and lasts 24 h from now; closed ones expired a day after they opened
    now = datetime.now(UTC)
    rooms = sa.table(
        "rooms",
        sa.column("id", sa.Integer),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("expires_at", sa.DateTime(timezone=True)),
    )
    connection = op.get_bind()
    for room_id, active, created in connection.execute(sa.select(rooms.c.id, rooms.c.is_active, rooms.c.created_at)):
        expires = now + ROOM_LIFETIME if active else (created or now) + ROOM_LIFETIME
        connection.execute(rooms.update().where(rooms.c.id == room_id).values(expires_at=expires))

    # guests: the same phone is a guest in every room it joins, with the same token, so token_hash becomes unique per
    # room. SQLite cannot drop the old unique constraint in place: the table is rebuilt (with the foreign keys off,
    # see core.db.migrate, since queue_entries points at it).
    op.create_table(
        "guests_new",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("nickname", sa.String(length=40), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "token_hash", name="uq_guests_room_token"),
    )
    op.execute(
        "INSERT INTO guests_new (id, room_id, nickname, token_hash, created_at, last_seen_at) "
        "SELECT id, room_id, nickname, token_hash, created_at, last_seen_at FROM guests"
    )
    op.drop_table("guests")
    op.rename_table("guests_new", "guests")
    op.create_index("ix_guests_room_id", "guests", ["room_id"], unique=False)
    op.create_index("ix_guests_token_hash", "guests", ["token_hash"], unique=False)


def downgrade() -> None:
    raise NotImplementedError("Many rooms cannot go back to one: guests may share a token across rooms.")
