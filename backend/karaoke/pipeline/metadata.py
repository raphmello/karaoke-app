"""Stage 1: video metadata from yt-dlp, without downloading the video, plus the thumbnail."""
from __future__ import annotations

import logging

import requests

from karaoke.core.storage import atomic_path

log = logging.getLogger("karaoke.pipeline")


def video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def run(ctx) -> dict:
    from yt_dlp import YoutubeDL

    with YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
        info = ydl.extract_info(video_url(ctx.folder.video_id), download=False)

    thumbnail_url = f"https://i.ytimg.com/vi/{ctx.folder.video_id}/hqdefault.jpg"
    try:
        resp = requests.get(thumbnail_url, timeout=30)
        resp.raise_for_status()
        with atomic_path(ctx.folder.thumb) as tmp:
            tmp.write_bytes(resp.content)
    except requests.RequestException as exc:  # a missing thumbnail does not stop a song from being sung
        log.warning("thumbnail não baixada: %s", exc)

    return {
        "title": info.get("title"),
        "channel": info.get("channel") or info.get("uploader"),
        "duration_s": info.get("duration"),
        "thumbnail_url": thumbnail_url,
        "track": info.get("track"),
        "artist": info.get("artist") or info.get("creator"),
        "album": info.get("album"),
    }
