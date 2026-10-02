"""Shared by the tests: things the pipeline would have left on disk."""
from fastapi.testclient import TestClient

from karaoke.core.config import Settings
from karaoke.core.storage import Manifest, SongFolder

PIN = "4321"  # the host's PIN in the tests


def write_manifest(settings: Settings, video_id: str, status: str, stages: dict) -> Manifest:
    """A song folder as the pipeline would leave it."""
    manifest = Manifest.load(SongFolder(settings.media_dir, video_id))
    manifest.data.update(status=status, stages=stages)
    manifest.save()
    return manifest


class Caller:
    """One person (the host or a phone), with their own cookie, on the shared client.

    Everything goes through one TestClient so the API runs on one event loop, as under uvicorn; separate clients
    would each run their own, and the hub would send across loops."""

    def __init__(self, client: TestClient, cookie: str):
        self.client, self.headers = client, {"cookie": cookie}

    def get(self, path, **kw):
        return self.client.get(path, headers=self.headers, **kw)

    def post(self, path, **kw):
        return self.client.post(path, headers=self.headers, **kw)

    def patch(self, path, **kw):
        return self.client.patch(path, headers=self.headers, **kw)

    def put(self, path, **kw):
        return self.client.put(path, headers=self.headers, **kw)

    def delete(self, path, **kw):
        return self.client.delete(path, headers=self.headers, **kw)

    def websocket_connect(self, path):
        return self.client.websocket_connect(path, headers=self.headers)


def cookie_of(response) -> str:
    return "; ".join(f"{name}={value}" for name, value in response.cookies.items())
