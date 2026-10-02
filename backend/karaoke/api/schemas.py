"""Request and response bodies of the REST API (docs/ARCHITECTURE.md, "API REST")."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from karaoke.core.models import READY, QueueEntry, Song
from karaoke.core.permissions import Actor
from karaoke.core.storage import parse_video_id


class Media(BaseModel):
    """Served by Caddy from the volume, with Range."""

    instrumental: str
    vocals: str
    lyrics: str
    thumb: str


class SongOut(BaseModel):
    video_id: str
    title: str | None
    artist: str | None
    track: str | None
    channel: str | None
    duration_s: float | None
    thumbnail_url: str | None
    status: str
    stage: str | None
    original_key: str | None
    language: str | None
    lyrics_source: str | None
    alignment_confidence: float | None
    error: str | None
    media: Media | None

    @classmethod
    def of(cls, song: Song) -> SongOut:
        base = f"/media/{song.video_id}"
        media = None
        if song.status == READY:
            media = Media(
                instrumental=f"{base}/play/instrumental.opus",
                vocals=f"{base}/play/vocals.opus",
                lyrics=f"{base}/lyrics/aligned.json",
                thumb=f"{base}/thumb.jpg",
            )
        return cls(
            video_id=song.video_id,
            title=song.title,
            artist=song.artist,
            track=song.track,
            channel=song.channel,
            duration_s=song.duration_s,
            thumbnail_url=song.thumbnail_url,
            status=song.status,
            stage=song.stage,
            original_key=song.original_key,
            language=song.language,
            lyrics_source=song.lyrics_source,
            alignment_confidence=song.alignment_confidence,
            error=song.error,
            media=media,
        )


class SearchResult(BaseModel):
    video_id: str
    title: str | None
    channel: str | None
    duration_s: float | None
    thumbnail_url: str
    in_library: bool  # ready now: plays without waiting for processing


class LoginIn(BaseModel):
    pin: str = Field(max_length=100)


class RoomIn(BaseModel):
    name: str | None = Field(default=None, max_length=80)


class RoomOut(BaseModel):
    code: str
    name: str | None
    join_path: str  # what the QR code points to, after the origin


class JoinIn(BaseModel):
    nickname: str = Field(min_length=1, max_length=40)

    @field_validator("nickname")
    @classmethod
    def strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("o apelido não pode ficar em branco")
        return value


class GuestOut(BaseModel):
    id: str
    nickname: str
    room_code: str


class QueueEntryIn(BaseModel):
    video_id: str = Field(max_length=200)  # an id or a YouTube URL
    singer_name: str | None = Field(default=None, max_length=40)
    semitones: int = Field(default=0, ge=-6, le=6)  # the key it starts in, relative to the original

    @field_validator("video_id")
    @classmethod
    def video(cls, value: str) -> str:
        return parse_video_id(value)


class QueueEntryOut(BaseModel):
    id: int
    video_id: str
    position: float
    status: str
    singer_name: str | None
    semitones: int
    added_by: str  # the owner's nickname, or "host"
    mine: bool  # the caller owns it
    song: SongOut

    @classmethod
    def of(cls, entry: QueueEntry, song: Song, nickname: str | None, actor: Actor) -> QueueEntryOut:
        return cls(
            id=entry.id,
            video_id=entry.video_id,
            position=entry.position,
            status=entry.status,
            singer_name=entry.singer_name,
            semitones=entry.semitones,
            added_by=nickname or "host",
            mine=entry.guest_id == actor.owner_id,
            song=SongOut.of(song),
        )


class QueueEntryPatch(BaseModel):
    semitones: int | None = Field(default=None, ge=-6, le=6)  # the owner or the host
    position: int | None = Field(default=None, ge=0)  # only the host: the new index in the queue, 0 = first


class TranscriptionIn(BaseModel):
    accept: bool


class ActiveRoomOut(RoomOut):
    public_base_url: str  # the QR's origin when the TV runs on localhost; empty when not set


class EventIn(BaseModel):
    """A worker report: song.progress, song.ready, song.failed or song.lyrics_missing, with its fields."""

    model_config = {"extra": "allow"}

    type: str
    video_id: str
