"""Stage 8: the playback versions of both stems, Opus at 160 kbps."""
from __future__ import annotations

import subprocess
from pathlib import Path

from karaoke.core.storage import atomic_path


def to_opus(src: Path, dst: Path, bitrate: str) -> None:
    with atomic_path(dst) as tmp:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-c:a", "libopus", "-b:a", bitrate, str(tmp)],
            check=True,
        )


def run(ctx) -> dict:
    folder, bitrate = ctx.folder, ctx.settings.opus_bitrate
    to_opus(folder.instrumental, folder.play_instrumental, bitrate)
    to_opus(folder.vocals, folder.play_vocals, bitrate)
    return {
        "bitrate": bitrate,
        "bytes": folder.play_instrumental.stat().st_size + folder.play_vocals.stat().st_size,
    }
