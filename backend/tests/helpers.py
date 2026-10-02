"""Shared by the tests: things the pipeline would have left on disk."""
from karaoke.core.config import Settings
from karaoke.core.storage import Manifest, SongFolder

PIN = "4321"  # the host's PIN in the tests


def write_manifest(settings: Settings, video_id: str, status: str, stages: dict) -> Manifest:
    """A song folder as the pipeline would leave it."""
    manifest = Manifest.load(SongFolder(settings.media_dir, video_id))
    manifest.data.update(status=status, stages=stages)
    manifest.save()
    return manifest
