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
TV_COOKIE = "karaoke_tv"  # a room's TV, opened by its owner: plays the queue, nothing of /host

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
    """The login check against HOST_PIN. An unset PIN never matches, so nobody logs in by accident."""
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


class CreationLimiter:
    """At most `limit` rooms per address in `window_s`: with the app on the internet, anyone may create rooms, and
    each one can bring downloads and GPU work (docs/ARCHITECTURE.md, "Salas"). In memory, like the login limiter."""

    def __init__(self, limit: int = 10, window_s: float = 3600, clock=time.monotonic):
        self.limit, self.window_s, self.clock = limit, window_s, clock
        self._made: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def take(self, address: str) -> int:
        """Counts one creation and returns 0, or, over the limit, the seconds until the next one is allowed."""
        now = self.clock()
        with self._lock:
            recent = [t for t in self._made.get(address, []) if t > now - self.window_s]
            if len(recent) >= self.limit:
                self._made[address] = recent
                return max(1, math.ceil(recent[0] + self.window_s - now))
            self._made[address] = recent + [now]
            return 0


class HostSigner:
    """Signs the host's and the TV's cookies with a secret that lives only in this process. The role is part of the
    signature, so a TV cookie never passes for a host one.

    Nothing about these sessions is stored, so restarting the API logs the host and the TV out; the PIN logs them
    back in.
    """

    def __init__(self, secret: bytes | None = None):
        self._secret = secret or secrets.token_bytes(32)

    def issue(self, role: str = "host") -> str:
        nonce = secrets.token_urlsafe(16)
        return f"{nonce}.{self._sign(role, nonce)}"

    def verify(self, value: str | None, role: str = "host") -> bool:
        if not value or "." not in value:
            return False
        nonce, signature = value.rsplit(".", 1)
        return hmac.compare_digest(signature, self._sign(role, nonce))

    def issue_tv(self, scope: str) -> str:
        """The TV's cookie, for one room (its id), given to the room's owner by "Abrir como TV". The scope is in the
        clear, and signed with the role, so a room's TV cookie never opens another room."""
        return f"{scope}~{self.issue(f'tv:{scope}')}"

    def tv_scope(self, value: str | None) -> str | None:
        """The room id a TV cookie is good for; None when it is not a valid TV cookie."""
        if not value or "~" not in value:
            return None
        scope, signed = value.split("~", 1)
        return scope if self.verify(signed, f"tv:{scope}") else None

    def _sign(self, role: str, nonce: str) -> str:
        return hmac.new(self._secret, f"{role}:{nonce}".encode(), hashlib.sha256).hexdigest()

