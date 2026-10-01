"""Stage 4: split the voice from the instrumental with BS-RoFormer (overlap 2, autocast), as chosen in the spike."""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

import requests

from karaoke.pipeline.gpu import free_gpu

STEM = re.compile(r"_\(([^)]+)\)")

# GitHub answers HTTP 500 for this release asset (checked 2026-10-01). UVR's own data repo has the same file
# (2273 bytes, like the asset); placed in the model folder first, audio-separator skips its download.
CONFIG_MIRRORS = {
    "model_bs_roformer_ep_317_sdr_12.9755.yaml":
        "https://raw.githubusercontent.com/TRvlvr/application_data/main/mdx_model_data/mdx_c_configs/"
        "model_bs_roformer_ep_317_sdr_12.9755.yaml",
}


def place_mirrored_configs(model_dir: Path) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)
    for name, url in CONFIG_MIRRORS.items():
        if not (model_dir / name).exists():
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            (model_dir / name).write_bytes(resp.content)


def run(ctx) -> dict:
    from audio_separator.separator import Separator

    settings = ctx.settings
    source = ctx.folder.source_audio()
    if source is None:
        raise FileNotFoundError("áudio original não encontrado; a etapa download não terminou")
    model_dir = settings.models_dir / "audio-separator"
    place_mirrored_configs(model_dir)
    scratch = ctx.folder.scratch("separation")
    shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir(parents=True)
    # audio-separator reads through libsndfile, which does not open YouTube's webm/m4a: hand it a WAV.
    wav = scratch / "input.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(source), "-ac", "2", "-ar", "44100", str(wav)], check=True
    )

    separator = Separator(
        log_level=logging.WARNING,
        model_file_dir=str(model_dir),
        output_dir=str(scratch),
        output_format="FLAC",
        use_autocast=settings.separation_autocast,
        mdxc_params={
            "segment_size": 256,
            "override_model_segment_size": False,
            "batch_size": None,
            "overlap": settings.separation_overlap,
            "pitch_shift": 0,
        },
    )
    try:
        separator.load_model(model_filename=settings.separation_model)
        separator.separate(str(wav))
    finally:
        del separator
        free_gpu()

    stems = {match[1].lower(): path for path in scratch.glob("*.flac") if (match := STEM.search(path.name))}
    missing = {"vocals", "instrumental"} - stems.keys()
    if missing:
        raise RuntimeError(f"a separação não gerou {sorted(missing)}; gerou {sorted(stems)}")
    ctx.folder.vocals.parent.mkdir(parents=True, exist_ok=True)
    os.replace(stems["vocals"], ctx.folder.vocals)
    os.replace(stems["instrumental"], ctx.folder.instrumental)
    shutil.rmtree(scratch, ignore_errors=True)
    return {
        "model": settings.separation_model,
        "overlap": settings.separation_overlap,
        "precision": "autocast" if settings.separation_autocast else "fp32",
    }
