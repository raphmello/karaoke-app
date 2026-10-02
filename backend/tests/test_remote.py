"""What protects the app once it is on the internet: the PIN attempt limit and /media only for people in a room."""
from fastapi.testclient import TestClient
from helpers import PIN

from karaoke.core.auth import LoginLimiter


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_five_wrong_pins_lock_the_address_for_a_while():
    clock = Clock()
    limiter = LoginLimiter(attempts=5, window_s=600, lockout_s=600, clock=clock)
    for _ in range(4):
        limiter.failed("1.2.3.4")
    assert limiter.retry_after("1.2.3.4") == 0
    limiter.failed("1.2.3.4")
    assert limiter.retry_after("1.2.3.4") == 600
    assert limiter.retry_after("5.6.7.8") == 0  # other addresses are not affected
    clock.now += 601
    assert limiter.retry_after("1.2.3.4") == 0


def test_old_failures_and_a_success_are_forgotten():
    clock = Clock()
    limiter = LoginLimiter(attempts=3, window_s=60, lockout_s=600, clock=clock)
    limiter.failed("a")
    limiter.failed("a")
    clock.now += 61  # outside the window
    limiter.failed("a")
    assert limiter.retry_after("a") == 0
    limiter.failed("a")
    limiter.succeeded("a")
    limiter.failed("a")
    limiter.failed("a")
    assert limiter.retry_after("a") == 0


def login(client: TestClient, pin: str, address: str):
    return client.post("/api/host/login", json={"pin": pin}, headers={"cf-connecting-ip": address})


def test_the_login_refuses_even_the_right_pin_while_locked(app, client):
    for _ in range(5):
        assert login(client, "0000", "203.0.113.7").status_code == 401
    locked = login(client, PIN, "203.0.113.7")
    assert locked.status_code == 429
    assert "Muitas tentativas" in locked.json()["detail"] and int(locked.headers["retry-after"]) > 0
    assert login(client, PIN, "198.51.100.1").status_code == 204  # someone else, elsewhere


def test_media_needs_the_host_or_a_guest_of_an_open_room(client, host, code, phone):
    assert client.get("/internal/media-auth").status_code == 401
    assert host.get("/internal/media-auth").status_code == 204
    ana = phone(code, "Ana")
    assert ana.get("/internal/media-auth").status_code == 204
    host.post("/api/rooms", json={})  # Ana's room closes
    assert ana.get("/internal/media-auth").status_code == 401
