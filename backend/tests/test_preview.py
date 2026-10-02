"""The preview of a video not yet downloaded: the route, and how the source talks to YouTube."""
import pytest

from karaoke.api import preview as preview_module
from karaoke.api.preview import PreviewSource, Upstream

VIDEO = "dQw4w9WgXcQ"


class FakeSource:
    def __init__(self, fail=False):
        self.fail, self.ranges = fail, []

    def open(self, video_id, range_header):
        if self.fail:
            raise RuntimeError("YouTube said no")
        self.ranges.append(range_header)
        return Upstream(206, {"Content-Type": "audio/mp4", "Content-Range": "bytes 0-3/4", "Accept-Ranges": "bytes"},
                        iter([b"ab", b"cd"]))


@pytest.fixture
def source():
    return FakeSource()


@pytest.fixture
def app(settings, source):
    from karaoke.api.app import create_app

    return create_app(settings, search=lambda q: [], preview=source)


def test_a_guest_hears_the_preview_with_range(phone, host, code, source):
    response = phone(code, "Ana").get(f"/api/preview/{VIDEO}", headers={"range": "bytes=0-"})
    assert response.status_code == 206
    assert response.content == b"abcd"
    assert response.headers["content-type"] == "audio/mp4"
    assert response.headers["content-range"] == "bytes 0-3/4"
    assert source.ranges == ["bytes=0-"]


def test_the_preview_needs_a_room(client):
    assert client.get(f"/api/preview/{VIDEO}").status_code == 401


def test_only_video_ids_are_previewed(host, code):
    assert host.get("/api/preview/..%2F..%2Fetc").status_code == 404


def test_a_preview_youtube_refuses_says_so(settings, client, phone, host, code):
    client.app.state.preview = FakeSource(fail=True)
    response = phone(code, "Ana").get(f"/api/preview/{VIDEO}")
    assert response.status_code == 502
    assert "prévia" in response.json()["detail"]


class FakeResponse:
    def __init__(self, status):
        self.status_code, self.headers, self.closed = status, {"Content-Length": "4", "X-Other": "no"}, False

    def iter_content(self, size):
        yield b"data"

    def close(self):
        self.closed = True

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def test_an_expired_audio_url_is_found_again_once(monkeypatch):
    finds, answers = [], [FakeResponse(403), FakeResponse(200)]
    source = PreviewSource()
    monkeypatch.setattr(source, "_find", lambda video_id, fresh=False: finds.append(fresh) or ("u", {}, "audio/mp4"))
    monkeypatch.setattr(preview_module.requests, "get", lambda url, headers, stream, timeout: answers.pop(0))

    upstream = source.open(VIDEO, None)
    assert finds == [False, True]
    assert upstream.status == 200
    assert upstream.headers == {"Content-Length": "4", "Content-Type": "audio/mp4", "Accept-Ranges": "bytes"}
    assert b"".join(upstream.body) == b"data"
