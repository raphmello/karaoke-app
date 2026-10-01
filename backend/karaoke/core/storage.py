"""A song's folder, media/<video_id>/, its manifest.json and atomic writes.

Every file is written under a temporary name and renamed when complete, so a crash never leaves a half-written
file under its final name. The manifest records each finished stage; it is the only record of progress.
"""
from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

PIPELINE_VERSION = 1
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
VIDEO_ID_IN_URL = re.compile(r"(?:[?&]v=|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])")


def parse_video_id(value: str) -> str:
    """Accept a YouTube video id or a YouTube URL; the id becomes a folder name, so nothing else passes."""
    value = value.strip()
    if VIDEO_ID.match(value):
        return value
    match = VIDEO_ID_IN_URL.search(value)
    if match:
        return match[1]
    raise ValueError(f"não é um ID nem uma URL de vídeo do YouTube: {value!r}")


@contextmanager
def atomic_path(path: Path) -> Iterator[Path]:
    """Yield a temporary path next to `path` that replaces it only if the block finishes.

    The temporary name keeps the extension, so tools that pick the format from it (ffmpeg) still work.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.stem}.tmp{path.suffix}")
    tmp.unlink(missing_ok=True)
    try:
        yield tmp
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def write_json(path: Path, data) -> None:
    with atomic_path(path) as tmp:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


class SongFolder:
    """Paths inside media/<video_id>/, as laid out in the architecture's storage section."""

    def __init__(self, media_dir: Path, video_id: str):
        self.video_id = parse_video_id(video_id)
        self.root = media_dir / self.video_id

    @property
    def manifest(self) -> Path:
        return self.root / "manifest.json"

    @property
    def thumb(self) -> Path:
        return self.root / "thumb.jpg"

    @property
    def instrumental(self) -> Path:
        return self.root / "stems" / "instrumental.flac"

    @property
    def vocals(self) -> Path:
        return self.root / "stems" / "vocals.flac"

    @property
    def play_instrumental(self) -> Path:
        return self.root / "play" / "instrumental.opus"

    @property
    def play_vocals(self) -> Path:
        return self.root / "play" / "vocals.opus"

    @property
    def lyrics_source(self) -> Path:
        return self.root / "lyrics" / "source.json"

    @property
    def aligned(self) -> Path:
        return self.root / "lyrics" / "aligned.json"

    def source_audio(self) -> Path | None:
        found = sorted(p for p in self.root.glob("source.*") if ".tmp" not in p.name)
        return found[0] if found else None

    def scratch(self, name: str) -> Path:
        """A working folder for a stage, emptied by the caller; never part of the finished layout."""
        return self.root / f".{name}"


class Manifest:
    def __init__(self, path: Path, data: dict):
        self.path = path
        self.data = data

    @classmethod
    def load(cls, folder: SongFolder) -> Manifest:
        data = read_json(folder.manifest) or {
            "video_id": folder.video_id,
            "pipeline_version": PIPELINE_VERSION,
            "status": "pending",
            "stages": {},
        }
        return cls(folder.manifest, data)

    @property
    def status(self) -> str:
        return self.data["status"]

    def done(self, stage: str) -> bool:
        return stage in self.data["stages"]

    def info(self, stage: str) -> dict:
        return self.data["stages"].get(stage, {})

    def complete(self, stage: str, info: dict) -> None:
        self.data["stages"][stage] = {"at": _now(), **info}
        self.save()

    def set(self, **fields) -> None:
        self.data.update(fields)
        self.save()

    def save(self) -> None:
        write_json(self.path, self.data)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
