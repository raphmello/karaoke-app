"""Who is calling: the host's PIN and cookie, and the guests' anonymous tokens (docs/ARCHITECTURE.md, "Salas")."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

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
