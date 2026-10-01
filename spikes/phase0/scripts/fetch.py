"""Step 1: find each song on YouTube, fetch synced lyrics from LRCLIB and download the audio.

Times the stages the app will run before any GPU work: metadata, lyrics lookup, download.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import time
from pathlib import Path

import requests
from yt_dlp import YoutubeDL

from common import RESULTS, encode_opus, load_songs, probe_duration, read_json, song_dir, write_json

LRCLIB = "https://lrclib.net/api"
HEADERS = {"User-Agent": "karaoke-app-spike/0.1 (https://github.com/raphmello/karaoke-app)"}
EXCLUDE = re.compile(
    r"\b(live|ao vivo|cover|karaok[eê]|instrumental|remix|slowed|sped up|8d|acoustic|ac[uú]stico|reaction)\b", re.I
)
TIMESTAMP = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")


def parse_lrc(synced: str) -> list[dict]:
    lines = []
    for raw in synced.splitlines():
        stamps = list(TIMESTAMP.finditer(raw))
        if not stamps:
            continue
        text = raw[stamps[-1].end():].strip()
        for stamp in stamps:
            lines.append({"t": int(stamp[1]) * 60 + float(stamp[2]), "text": text})
    return sorted(lines, key=lambda line: line["t"])


def lrclib_search(artist: str, title: str) -> list[dict]:
    resp = requests.get(
        f"{LRCLIB}/search", params={"artist_name": artist, "track_name": title}, headers=HEADERS, timeout=30
    )
    resp.raise_for_status()
    return [r for r in resp.json() if r.get("syncedLyrics") and not r.get("instrumental")]


def lrclib_get(artist: str, title: str, duration: float) -> tuple[dict | None, float, int]:
    """The lookup the app will make: artist, track and the video's duration."""
    start = time.perf_counter()
    resp = requests.get(
        f"{LRCLIB}/get",
        params={"artist_name": artist, "track_name": title, "duration": round(duration)},
        headers=HEADERS,
        timeout=30,
    )
    elapsed = time.perf_counter() - start
    return (resp.json() if resp.status_code == 200 else None), elapsed, resp.status_code


def yt_search(query: str, n: int = 10) -> tuple[list[dict], float]:
    start = time.perf_counter()
    with YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True, "extract_flat": True}) as ydl:
        info = ydl.extract_info(f"ytsearch{n}:{query}", download=False)
    elapsed = time.perf_counter() - start
    videos = [
        {
            "id": e["id"],
            "title": e.get("title") or "",
            "channel": e.get("channel") or e.get("uploader") or "",
            "duration": e.get("duration"),
        }
        for e in info.get("entries") or []
        if e and e.get("duration")
    ]
    return videos, elapsed


def pick(videos: list[dict], lyrics: list[dict]) -> tuple[dict | None, dict | None]:
    """Prefer a video within 3 s of some synced lyrics, then the higher search rank, then the closest duration."""
    best = None
    for rank, video in enumerate(videos):
        if EXCLUDE.search(video["title"]):
            continue
        for lrc in lyrics:
            diff = abs(video["duration"] - lrc["duration"])
            key = (diff > 3, rank, diff)
            if best is None or key < best[0]:
                best = (key, video, lrc)
    return (best[1], best[2]) if best else (None, None)


def download(video_id: str, out: Path) -> dict:
    url = f"https://www.youtube.com/watch?v={video_id}"
    start = time.perf_counter()
    with YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
        meta = ydl.extract_info(url, download=False)
    metadata_s = time.perf_counter() - start

    start = time.perf_counter()
    opts = {"quiet": True, "no_warnings": True, "format": "bestaudio/best", "outtmpl": str(out / "download.%(ext)s")}
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(ydl.prepare_filename(info))
    download_s = time.perf_counter() - start

    start = time.perf_counter()
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-ac", "2", "-ar", "44100", str(out / "source.wav")],
        check=True,
    )
    convert_s = time.perf_counter() - start
    encode_opus(out / "source.wav", out / "play" / "source.opus")

    return {
        "metadata_s": round(metadata_s, 2),
        "download_s": round(download_s, 2),
        "convert_s": round(convert_s, 2),
        "file": path.name,
        "bytes": path.stat().st_size,
        "acodec": info.get("acodec"),
        "abr_kbps": info.get("abr"),
        "yt_track": meta.get("track"),
        "yt_artist": meta.get("artist"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="slug of a single song")
    parser.add_argument("--force", action="store_true", help="download again even if source.wav exists")
    args = parser.parse_args()

    report = read_json(RESULTS / "fetch.json", {})
    for song in load_songs(args.only):
        out = song_dir(song["slug"])
        print(f"== {song['artist']} - {song['title']}")

        lyrics = lrclib_search(song["artist"], song["title"])
        videos, search_s = yt_search(f"{song['artist']} {song['title']} audio")
        if song.get("video_id"):
            videos = [v for v in videos if v["id"] == song["video_id"]] or videos
        video, lrc = pick(videos, lyrics)
        if video is None:
            print("   no usable video/lyrics pair found")
            report[song["slug"]] = {"error": "no video/lyrics pair", "lrclib_results": len(lyrics)}
            write_json(RESULTS / "fetch.json", report)
            continue

        got, get_s, get_status = lrclib_get(song["artist"], song["title"], video["duration"])
        lines = parse_lrc(lrc["syncedLyrics"])
        write_json(
            out / "lyrics.json",
            {
                "lrclib_id": lrc["id"],
                "artist": lrc.get("artistName"),
                "track": lrc.get("trackName"),
                "album": lrc.get("albumName"),
                "duration": lrc["duration"],
                "plain": lrc.get("plainLyrics"),
                "lines": lines,
            },
        )

        entry = report.get(song["slug"], {})
        if args.force or not (out / "source.wav").exists():
            entry["download"] = download(video["id"], out)
        entry.update(
            {
                "artist": song["artist"],
                "title": song["title"],
                "language": song["language"],
                "video": video,
                "search_s": round(search_s, 2),
                "audio_s": round(probe_duration(out / "source.wav"), 2),
                "lrclib": {
                    "search_results_with_sync": len(lyrics),
                    "id": lrc["id"],
                    "duration": lrc["duration"],
                    "duration_diff_s": round(abs(video["duration"] - lrc["duration"]), 2),
                    "lines": len(lines),
                    "sung_lines": sum(1 for line in lines if line["text"]),
                },
                "lrclib_get": {
                    "status": get_status,
                    "elapsed_s": round(get_s, 2),
                    "has_synced": bool(got and got.get("syncedLyrics")),
                    "same_id_as_search": bool(got and got.get("id") == lrc["id"]),
                },
            }
        )
        report[song["slug"]] = entry
        write_json(RESULTS / "fetch.json", report)
        print(f"   video {video['id']} ({video['duration']} s), lyrics {lrc['id']} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
