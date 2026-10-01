"""Stage 3: download the best available audio as source.<ext>."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from karaoke.pipeline.metadata import video_url


def run(ctx) -> dict:
    from yt_dlp import YoutubeDL

    scratch = ctx.folder.scratch("download")
    shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir(parents=True)
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "format": "bestaudio/best",
        "outtmpl": str(scratch / "source.%(ext)s"),
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(video_url(ctx.folder.video_id), download=True)
        downloaded = Path(ydl.prepare_filename(info))

    for old in ctx.folder.root.glob("source.*"):
        old.unlink()
    dest = ctx.folder.root / downloaded.name
    os.replace(downloaded, dest)
    shutil.rmtree(scratch, ignore_errors=True)
    return {"file": dest.name, "bytes": dest.stat().st_size, "acodec": info.get("acodec"), "abr_kbps": info.get("abr")}
