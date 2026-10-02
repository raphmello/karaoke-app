"""YouTube search through yt-dlp, with the architecture's 10-minute cache per term."""
from __future__ import annotations

import threading
import time
from collections.abc import Callable

from karaoke.core.storage import VIDEO_ID

SearchFn = Callable[[str], list[dict]]
RESULTS = 10


def youtube_search(query: str) -> list[dict]:
    """Search results without opening each video: id, title, channel, duration and thumbnail."""
    from yt_dlp import YoutubeDL

    options = {"quiet": True, "no_warnings": True, "skip_download": True, "extract_flat": "in_playlist"}
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(f"ytsearch{RESULTS}:{query}", download=False)
    results = []
    for entry in info.get("entries") or []:
        video_id = entry.get("id") or ""
        if not VIDEO_ID.match(video_id):  # channels and playlists also show up in searches
            continue
        results.append({
            "video_id": video_id,
            "title": entry.get("title"),
            "channel": entry.get("channel") or entry.get("uploader"),
            "duration_s": entry.get("duration"),
            "thumbnail_url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        })
    return results


class CachedSearch:
    def __init__(self, search: SearchFn, ttl_s: float = 600):
        self._search = search
        self._ttl_s = ttl_s
        self._cache: dict[str, tuple[float, list[dict]]] = {}
        self._lock = threading.Lock()

    def __call__(self, query: str) -> list[dict]:
        key = " ".join(query.lower().split())
        now = time.monotonic()
        with self._lock:
            self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
            hit = self._cache.get(key)
        if hit:
            return hit[1]
        results = self._search(key)
        with self._lock:
            self._cache[key] = (now + self._ttl_s, results)
        return results
