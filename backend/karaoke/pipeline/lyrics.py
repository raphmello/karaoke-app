"""Stage 2: find the lyrics, before anything is downloaded.

Order (architecture, stage 2): LRCLIB by artist, track and duration; then LRCLIB free search with the cleaned
title; then syncedlyrics. Synced lyrics win over plain ones, then the duration closest to the video's.
A network failure raises: "the service is down" must never be recorded as "these lyrics do not exist".
"""
from __future__ import annotations

import logging
import re

import requests

from karaoke.core.storage import write_json

log = logging.getLogger("karaoke.pipeline")

LRCLIB = "https://lrclib.net/api"
HEADERS = {"User-Agent": "karaoke-app/0.1 (https://github.com/raphmello/karaoke-app)"}
MAX_DURATION_DIFF = 10.0  # seconds; further away it is probably another version of the song
TIMESTAMP = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
NOISE = re.compile(
    r"\s*[\(\[][^)\]]*?(official|oficial|video|vídeo|clipe|clip|audio|áudio|lyric|letra|remaster|hd|4k|"
    r"visualizer|ao vivo|live)[^)\]]*[\)\]]",
    re.IGNORECASE,
)
CHANNEL_NOISE = re.compile(r"\s*(-\s*topic|vevo|oficial|official)\s*$", re.IGNORECASE)
NOISE_WORDS = re.compile(
    r"\b(official|oficial|video|vídeo|clipe|clip|audio|áudio|lyrics?|letra|remaster(ed)?|visualizer|ao vivo|live)\b",
    re.IGNORECASE,
)
SEPARATOR = re.compile(r"\s+[-–—|]\s+")  # noqa: RUF001 - YouTube titles use en and em dashes as separators


def parse_lrc(text: str) -> list[dict]:
    """LRC lines as {"t": seconds, "text": words}, sorted; empty lines are kept, they mark pauses."""
    lines = []
    for raw in text.splitlines():
        stamps = list(TIMESTAMP.finditer(raw))
        if not stamps:
            continue
        words = raw[stamps[-1].end():].strip()
        for stamp in stamps:
            lines.append({"t": int(stamp[1]) * 60 + float(stamp[2]), "text": words})
    return sorted(lines, key=lambda line: line["t"])


def guess_artist_track(meta: dict) -> tuple[str, str]:
    """Artist and track from the YouTube metadata, falling back to "Artist - Track (Official Video)" titles."""
    if meta.get("track") and meta.get("artist"):
        return meta["artist"].split(",")[0].strip(), meta["track"].strip()
    title = NOISE.sub("", meta.get("title") or "").strip()
    parts = SEPARATOR.split(title)
    # "Artist - Track - Video Oficial": the parts after the track that only say what kind of video it is go
    while len(parts) > 2 and NOISE_WORDS.search(parts[-1]):
        parts.pop()
    if len(parts) > 1:
        return parts[0].strip(), " - ".join(parts[1:]).strip()
    return CHANNEL_NOISE.sub("", meta.get("channel") or "").strip(), parts[0].strip()


def _candidate(record: dict, origin: str) -> dict | None:
    if record.get("instrumental"):
        return None
    synced = parse_lrc(record.get("syncedLyrics") or "")
    plain = record.get("plainLyrics") or ""
    if not synced and not plain.strip():
        return None
    return {
        "source": origin,
        "id": record.get("id"),
        "artist": record.get("artistName"),
        "track": record.get("trackName"),
        "album": record.get("albumName"),
        "duration": record.get("duration"),
        "synced": bool(synced),
        "lines": synced or [{"t": None, "text": line.strip()} for line in plain.splitlines() if line.strip()],
    }


def lrclib_get(artist: str, track: str, duration: float | None) -> dict | None:
    params = {"artist_name": artist, "track_name": track}
    if duration:
        params["duration"] = round(duration)
    resp = requests.get(f"{LRCLIB}/get", params=params, headers=HEADERS, timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return _candidate(resp.json(), "lrclib")


def lrclib_search(query: str) -> list[dict]:
    resp = requests.get(f"{LRCLIB}/search", params={"q": query}, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return [c for c in (_candidate(r, "lrclib") for r in resp.json()) if c]


def syncedlyrics_search(artist: str, track: str) -> dict | None:
    import syncedlyrics

    text = syncedlyrics.search(f"{track} {artist}")
    if not text:
        return None
    synced = parse_lrc(text)
    lines = synced or [{"t": None, "text": line.strip()} for line in text.splitlines() if line.strip()]
    return {"source": "syncedlyrics", "id": None, "artist": artist, "track": track, "album": None,
            "duration": None, "synced": bool(synced), "lines": lines}


def choose(candidates: list[dict], duration: float | None) -> dict | None:
    """Synced first, then the closest duration; lyrics far from the video's duration are another version."""
    def diff(c: dict) -> float:
        return abs(c["duration"] - duration) if c.get("duration") and duration else 0.0

    usable = [c for c in candidates if diff(c) <= MAX_DURATION_DIFF]
    if not usable:
        return None
    return min(usable, key=lambda c: (not c["synced"], diff(c)))


def fits_video(lyrics: dict, duration: float | None) -> bool:
    """Synced lyrics without a known duration must at least end inside the video and cover half of it."""
    if not lyrics["synced"] or not duration:
        return True
    last = max(line["t"] for line in lyrics["lines"])
    return duration * 0.5 <= last <= duration + 5


def find(meta: dict) -> dict | None:
    artist, track = guess_artist_track(meta)
    duration = meta.get("duration_s")
    found = lrclib_get(artist, track, duration)
    if found and found["synced"]:
        return found
    candidates = [found] if found else []
    candidates += lrclib_search(f"{artist} {track}".strip())
    best = choose(candidates, duration)
    if best and best["synced"]:
        return best
    try:
        extra = syncedlyrics_search(artist, track)
    except Exception as exc:  # a scraper fallback; its failure must not hide what LRCLIB already found
        log.warning("syncedlyrics falhou: %s", exc)
        extra = None
    if extra and not fits_video(extra, duration):
        log.info("syncedlyrics devolveu uma letra que não cabe no vídeo; descartada")
        extra = None
    if extra and (not best or extra["synced"]):
        return extra
    return best


def run(ctx) -> dict:
    meta = ctx.manifest.info("metadata")
    lyrics = find(meta)
    artist, track = guess_artist_track(meta)
    if not lyrics:
        return {"found": False, "artist": artist, "track": track}
    write_json(ctx.folder.lyrics_source, lyrics)
    diff = abs(lyrics["duration"] - meta["duration_s"]) if lyrics.get("duration") and meta.get("duration_s") else None
    return {
        "found": True,
        "source": lyrics["source"],
        "synced": lyrics["synced"],
        "lines": sum(1 for line in lyrics["lines"] if line["text"]),
        "duration_diff_s": round(diff, 2) if diff is not None else None,
        "artist": artist,
        "track": track,
    }
