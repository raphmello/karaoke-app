"""Stage 2: find the lyrics, before anything is downloaded.

Order (architecture, stage 2): LRCLIB by artist, track and duration; then LRCLIB free search with the cleaned
title; then syncedlyrics. Synced lyrics win over plain ones, then the duration closest to the video's.
A network failure raises: "the service is down" must never be recorded as "these lyrics do not exist".
"""
from __future__ import annotations

import logging
import re
import time

import requests

from karaoke.core.storage import write_json

log = logging.getLogger("karaoke.pipeline")

LRCLIB = "https://lrclib.net/api"
HEADERS = {"User-Agent": "karaoke-app/0.1 (https://github.com/raphmello/karaoke-app)"}
RETRY_WAITS_S = (1.0, 2.0, 4.0)  # LRCLIB is tried 4 times in all
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
    channel = channel_name(meta)
    if len(parts) > 1:
        first, rest = parts[0].strip(), " - ".join(parts[1:]).strip()
        # "Track - Artist" titles exist too ("In The End [Official HD Music Video] - Linkin Park"): the part that
        # is the channel's name is the artist.
        if same_name(rest, channel) and not same_name(first, channel):
            return rest, first
        return first, rest
    return channel, parts[0].strip()


def channel_name(meta: dict) -> str:
    return CHANNEL_NOISE.sub("", meta.get("channel") or "").strip()


def same_name(a: str | None, b: str | None) -> bool:
    """Names equal once case, spaces and punctuation are ignored (accents still count): "[LINKIN PARK]" is
    "Linkin Park"."""
    def key(name: str | None) -> str:
        return "".join(ch for ch in (name or "").casefold() if ch.isalnum())

    return bool(key(a)) and key(a) == key(b)


def artist_and_track(meta: dict, lyrics: dict | None) -> tuple[str, str]:
    """The guess from the title; when the channel doesn't vouch for the artist, the lyrics found may correct it."""
    artist, track = guess_artist_track(meta)
    if same_name(artist, channel_name(meta)) or (meta.get("track") and meta.get("artist")):
        return artist, track
    return match_lyrics(artist, track, lyrics)


def match_lyrics(artist: str, track: str, lyrics: dict | None) -> tuple[str, str]:
    """The lyrics found tell who sings: when their artist and track are ours swapped, the guess had them reversed.
    Only a second opinion: LRCLIB has entries filed the wrong way round too (In the End is one)."""
    if lyrics and same_name(lyrics.get("artist"), track) and same_name(lyrics.get("track"), artist):
        return track, artist
    return artist, track


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


def lrclib_request(endpoint: str, params: dict) -> requests.Response:
    """LRCLIB sometimes answers 503 for a moment: a busy server, a timeout or a dropped connection is tried again
    with growing waits. If it is still down after that, the error rises: "the service is down" is never recorded
    as "these lyrics do not exist"."""
    for attempt, wait in enumerate((*RETRY_WAITS_S, None)):
        try:
            resp = requests.get(f"{LRCLIB}/{endpoint}", params=params, headers=HEADERS, timeout=30)
            if resp.status_code < 500:
                return resp
            problem: Exception = requests.HTTPError(f"{resp.status_code} do LRCLIB", response=resp)
        except (requests.ConnectionError, requests.Timeout) as exc:
            problem = exc
        if wait is None:
            if isinstance(problem, requests.HTTPError):
                problem.response.raise_for_status()
            raise problem
        log.info("LRCLIB falhou (%s), tentativa %d; de novo em %.0f s", problem, attempt + 1, wait)
        time.sleep(wait)
    raise AssertionError("unreachable")


def lrclib_get(artist: str, track: str, duration: float | None) -> dict | None:
    params = {"artist_name": artist, "track_name": track}
    if duration:
        params["duration"] = round(duration)
    resp = lrclib_request("get", params)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return _candidate(resp.json(), "lrclib")


def lrclib_search(query: str) -> list[dict]:
    resp = lrclib_request("search", {"q": query})
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
    artist, track = artist_and_track(meta, lyrics)
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
