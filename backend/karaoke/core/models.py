"""The six tables of the architecture's data model (docs/ARCHITECTURE.md, "Modelo de dados")."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


# songs.status
PENDING, AWAITING_DECISION, PROCESSING, READY, FAILED, REMOVED = (
    "pending", "awaiting_decision", "processing", "ready", "failed", "removed"
)
# queue_entries.status, besides AWAITING_DECISION and REMOVED above
QUEUED, PLAYING, DONE, SKIPPED = "queued", "playing", "done", "skipped"
ACTIVE_ENTRY = (QUEUED, AWAITING_DECISION, PLAYING)  # entries still in the queue
# jobs.status
JOB_PENDING, JOB_RUNNING, JOB_DONE, JOB_FAILED = "pending", "running", "done", "failed"


class Song(Base):
    """One row per YouTube video, never deleted."""

    __tablename__ = "songs"

    video_id: Mapped[str] = mapped_column(String(11), primary_key=True)
    title: Mapped[str | None] = mapped_column(Text)
    artist: Mapped[str | None] = mapped_column(Text)
    track: Mapped[str | None] = mapped_column(Text)
    channel: Mapped[str | None] = mapped_column(Text)
    duration_s: Mapped[float | None] = mapped_column(Float)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=PENDING)
    stage: Mapped[str | None] = mapped_column(String(20))
    original_key: Mapped[str | None] = mapped_column(String(20))
    language: Mapped[str | None] = mapped_column(String(8))
    lyrics_source: Mapped[str | None] = mapped_column(String(20))  # lrclib, syncedlyrics, transcrita, manual, nenhuma
    alignment_confidence: Mapped[float | None] = mapped_column(Float)
    pipeline_version: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_reason: Mapped[str | None] = mapped_column(String(40))


class SongEvent(Base):
    """Append-only history of a song: created, lyrics missing, transcription accepted or declined, ready, ..."""

    __tablename__ = "song_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("songs.video_id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    guest_id: Mapped[str | None] = mapped_column(String(36))  # who did it; None for the system, "host" for the host
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        # two equal jobs can never be active at once (architecture, "Garantias contra reprocessamento")
        Index(
            "ix_jobs_one_active",
            "video_id",
            "kind",
            unique=True,
            sqlite_where=text("status IN ('pending', 'running')"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(20), default="process")
    video_id: Mapped[str] = mapped_column(ForeignKey("songs.video_id"), index=True)
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default=JOB_PENDING)
    stage: Mapped[str | None] = mapped_column(String(20))
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(12), unique=True)
    name: Mapped[str | None] = mapped_column(Text)
    host_pin_hash: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Guest(Base):
    __tablename__ = "guests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    nickname: Mapped[str] = mapped_column(String(40))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QueueEntry(Base):
    __tablename__ = "queue_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("songs.video_id"), index=True)
    guest_id: Mapped[str | None] = mapped_column(ForeignKey("guests.id"))  # the owner; None when the host added it
    singer_name: Mapped[str | None] = mapped_column(String(40))
    semitones: Mapped[int] = mapped_column(Integer, default=0)  # current key relative to the original, -6..+6
    position: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default=QUEUED)
    removed_reason: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
