"""Step 0: record the environment the measurements ran in."""
from __future__ import annotations

import platform
import subprocess
from importlib import metadata

from common import RESULTS, gpu_info, write_json

PACKAGES = [
    "torch", "torchaudio", "audio-separator", "onnxruntime-gpu", "yt-dlp", "yt-dlp-ejs",
    "stable-ts", "openai-whisper", "faster-whisper", "ctranslate2", "musdb", "numpy",
]


def tool_version(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        text = (out.stdout or out.stderr).strip().splitlines()
        return text[0] if text else "?"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"error: {exc}"


def main() -> None:
    import torch

    versions = {}
    for name in PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None

    env = {
        "python": platform.python_version(),
        "gpu": gpu_info(),
        "torch_cuda": torch.version.cuda,
        "torch_cuda_available": torch.cuda.is_available(),
        "cudnn": torch.backends.cudnn.version(),
        "packages": versions,
        "tools": {
            "ffmpeg": tool_version(["ffmpeg", "-version"]),
            "rubberband": tool_version(["rubberband", "--version"]),
            "deno": tool_version(["deno", "--version"]),
        },
    }
    write_json(RESULTS / "env.json", env)
    for key, value in env.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
