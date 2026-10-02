"""A preview of a video not yet downloaded: yt-dlp finds its audio and the API passes it on, Range included, so the
screens keep talking only to Caddy (docs/ARCHITECTURE.md, GET /api/preview/{video_id}).

YouTube's audio URLs last a few hours; each one found is kept for a while, and found again if YouTube refuses it.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass

import requests

from karaoke.pipeline.metadata import video_url

URL_TTL_S = 30 * 60
CHUNK = 64 * 1024
PASSED_ON = ("content-type", "content-length", "content-range", "accept-ranges")
TYPES = {"m4a": "audio/mp4", "webm": "audio/webm", "mp4": "audio/mp4"}


@dataclass
class Upstream:
    status: int
    headers: dict[str, str]
    body: Iterator[bytes]


class PreviewSource:
    def __init__(self):
        self._found: dict[str, tuple[float, str, dict, str]] = {}
        self._lock = threading.Lock()

    def _find(self, video_id: str, fresh: bool = False) -> tuple[str, dict, str]:
        now = time.monotonic()
        with self._lock:
            hit = self._found.get(video_id)
        if hit and hit[0] > now and not fresh:
            return hit[1], hit[2], hit[3]
        from yt_dlp import YoutubeDL

        # m4a first: every browser plays it, Safari included
        options = {"quiet": True, "no_warnings": True, "skip_download": True, "format": "bestaudio[ext=m4a]/bestaudio"}
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(video_url(video_id), download=False)
        found = (info["url"], dict(info.get("http_headers") or {}), TYPES.get(info.get("ext"), "audio/mp4"))
        with self._lock:
            self._found[video_id] = (now + URL_TTL_S, *found)
        return found

    def open(self, video_id: str, range_header: str | None) -> Upstream:
        for fresh in (False, True):  # an expired URL is found again, once
            url, headers, content_type = self._find(video_id, fresh)
            if range_header:
                headers = {**headers, "Range": range_header}
            response = requests.get(url, headers=headers, stream=True, timeout=30)
            if response.status_code in (403, 410) and not fresh:
                response.close()
                continue
            response.raise_for_status()
            passed = {k: v for k, v in response.headers.items() if k.lower() in PASSED_ON}
            passed["Content-Type"] = content_type
            passed.setdefault("Accept-Ranges", "bytes")
            return Upstream(response.status_code, passed, _stream(response))
        raise RuntimeError("unreachable")


def _stream(response: requests.Response) -> Iterator[bytes]:
    try:
        yield from response.iter_content(CHUNK)
    finally:
        response.close()
