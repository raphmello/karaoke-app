"""GPU housekeeping. With 8 GB of VRAM only one model is loaded at a time, so each stage frees what it used."""
from __future__ import annotations

import gc


def free_gpu() -> None:
    gc.collect()
    import torch

    if torch.cuda.is_available():
        torch.cuda.empty_cache()
