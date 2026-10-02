"""Settings. Defaults are the choices of the phase 0 spike (docs/ARCHITECTURE.md, stack table)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    host_pin: str = ""
    api_url: str = "http://api:8000"  # where the worker reports progress (/internal/events), inside Compose
    separation_model: str = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"
    separation_overlap: int = 2
    separation_autocast: bool = True
    whisper_model: str = "turbo"
    opus_bitrate: str = "160k"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'karaoke.db'}"


def load_settings() -> Settings:
    return Settings(
        data_dir=Path(os.environ.get("KARAOKE_DATA", "/data")),
        host_pin=os.environ.get("HOST_PIN", ""),
    )
