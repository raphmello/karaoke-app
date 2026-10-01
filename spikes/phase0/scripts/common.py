"""Shared helpers for the phase 0 spike: paths, JSON files, audio tools and GPU memory sampling."""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path

ROOT = Path(os.environ.get("SPIKE_ROOT", Path(__file__).resolve().parents[1]))
WORK = Path(os.environ.get("SPIKE_WORK", ROOT / "work"))
MODELS = Path(os.environ.get("SPIKE_MODELS", WORK / "models"))
SONGS = WORK / "songs"
RESULTS = WORK / "results"


def load_songs(only: str | None = None) -> list[dict]:
    songs = json.loads((ROOT / "songs.json").read_text(encoding="utf-8"))
    return [s for s in songs if not only or s["slug"] == only]


def song_dir(slug: str) -> Path:
    path = SONGS / slug
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def encode_opus(src: Path, dst: Path, bitrate: str = "160k") -> float:
    """Encode the playback version (architecture stage 8) and return the elapsed seconds."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-c:a", "libopus", "-b:a", bitrate, str(dst)],
        check=True,
    )
    return time.perf_counter() - start


def free_gpu() -> None:
    import gc

    gc.collect()
    try:
        import torch

        torch.cuda.empty_cache()
    except ImportError:
        pass


def gpu_info() -> dict:
    import pynvml

    pynvml.nvmlInit()
    handle = pynvml.nvmlDeviceGetHandleByIndex(0)
    name = pynvml.nvmlDeviceGetName(handle)
    driver = pynvml.nvmlSystemGetDriverVersion()
    return {
        "name": name.decode() if isinstance(name, bytes) else name,
        "driver": driver.decode() if isinstance(driver, bytes) else driver,
        "total_mib": round(pynvml.nvmlDeviceGetMemoryInfo(handle).total / 2**20),
    }


class GpuMonitor:
    """Samples device memory through NVML while used as a context manager.

    NVML sees every allocation (PyTorch, ONNX Runtime, CTranslate2), unlike torch.cuda.max_memory_allocated.
    Create it before the process touches CUDA: `idle_mib` is then the memory used by everything else on the
    GPU (the Windows desktop included), and `above_idle_mib` is what this process needed at its peak,
    CUDA context included. `delta_mib` is the peak above the level seen on entry.
    """

    def __init__(self, interval: float = 0.05):
        import pynvml

        pynvml.nvmlInit()
        self._nvml = pynvml
        self._handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.idle_mib = self.used_mib()
        self.baseline_mib = self.idle_mib
        self.peak_mib = self.baseline_mib

    def used_mib(self) -> float:
        return self._nvml.nvmlDeviceGetMemoryInfo(self._handle).used / 2**20

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.peak_mib = max(self.peak_mib, self.used_mib())
            time.sleep(self._interval)

    def __enter__(self) -> "GpuMonitor":
        self.baseline_mib = self.used_mib()
        self.peak_mib = self.baseline_mib
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join()
        self.peak_mib = max(self.peak_mib, self.used_mib())

    @property
    def delta_mib(self) -> int:
        return round(self.peak_mib - self.baseline_mib)

    @property
    def above_idle_mib(self) -> int:
        return round(self.peak_mib - self.idle_mib)
