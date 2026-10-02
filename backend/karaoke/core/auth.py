"""Who is calling: the host's PIN and cookie, and the guests' anonymous tokens (docs/ARCHITECTURE.md, "Salas")."""
from __future__ import annotations

import base64
import hashlib
import hmac
import math
import secrets
import threading
import time

GUEST_COOKIE = "karaoke_guest"
HOST_COOKIE = "karaoke_host"

_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def hash_pin(pin: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(pin.encode(), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_pin(pin: str, stored: str) -> bool:
    try:
        scheme, salt, digest = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    actual = hashlib.scrypt(pin.encode(), salt=base64.b64decode(salt), **_SCRYPT)
    return hmac.compare_digest(actual, base64.b64decode(digest))


def pin_matches(pin: str, expected: str) -> bool:
    """The login check against HOST_PIN. An unset PIN never matches, so the host can't log in by accident."""
    return bool(expected) and hmac.compare_digest(pin.encode(), expected.encode())


def new_guest_token() -> tuple[str, str]:
    """A random token for the phone's cookie, and the hash that is the only thing the database keeps."""
    token = secrets.token_urlsafe(32)
    return token, token_hash(token)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class LoginLimiter:
    """Too many wrong PINs from one address lock that address out for a while: once the app is on the internet,
    a short PIN would otherwise fall to guessing. In memory, like the host's sessions."""

    def __init__(self, attempts: int = 5, window_s: float = 600, lockout_s: float = 600, clock=time.monotonic):
        self.attempts, self.window_s, self.lockout_s, self.clock = attempts, window_s, lockout_s, clock
        self._failures: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def retry_after(self, address: str) -> int:
        """Seconds until this address may try again; 0 when it may try now."""
        with self._lock:
            left = self._locked_until.get(address, 0) - self.clock()
            return max(0, math.ceil(left))

    def failed(self, address: str) -> None:
        now = self.clock()
        with self._lock:
            recent = [t for t in self._failures.get(address, []) if t > now - self.window_s] + [now]
            if len(recent) >= self.attempts:
                self._locked_until[address] = now + self.lockout_s
                recent = []
            self._failures[address] = recent

    def succeeded(self, address: str) -> None:
        with self._lock:
            self._failures.pop(address, None)


class HostSigner:
    """Signs the host cookie with a secret that lives only in this process.

    Nothing about the host session is stored, so restarting the API logs the host out; the PIN logs them back in.
    """

    def __init__(self, secret: bytes | None = None):
        self._secret = secret or secrets.token_bytes(32)

    def issue(self) -> str:
        nonce = secrets.token_urlsafe(16)
        return f"{nonce}.{self._sign(nonce)}"

    def verify(self, value: str | None) -> bool:
        if not value or "." not in value:
            return False
        nonce, signature = value.rsplit(".", 1)
        return hmac.compare_digest(signature, self._sign(nonce))

    def _sign(self, nonce: str) -> str:
        return hmac.new(self._secret, f"host:{nonce}".encode(), hashlib.sha256).hexdigest()
