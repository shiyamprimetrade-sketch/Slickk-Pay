"""Standard-library primitives for synthetic fixtures and opaque sessions.

These are deliberately not advertised as production customer authentication.
No custom cipher or cryptographic primitive is implemented here.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from .errors import LabError, require
from .identifiers import canonical, digest


def b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def unb64u(value: str) -> bytes:
    require(isinstance(value, str) and value and len(value) <= 4096, "INVALID_INPUT")
    if not all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for c in value):
        raise LabError("INVALID_INPUT")
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception as exc:
        raise LabError("INVALID_INPUT") from exc


def new_opaque_token() -> str:
    return "simsess_" + secrets.token_urlsafe(32)


def new_reference(prefix: str) -> str:
    require(prefix in ("request", "quote", "audit", "session", "support", "receipt", "qr", "delivery", "device"), "INVALID_INPUT")
    return "sim_" + prefix + "_" + secrets.token_hex(15)


def token_digest(token: str) -> str:
    require(isinstance(token, str) and token.startswith("simsess_") and 32 <= len(token) <= 128, "UNAUTHORIZED")
    return digest(token)


def derive_pin(pin: str, salt: bytes | None = None) -> tuple[str, str]:
    """Scrypt PIN derivation for synthetic accounts; keep online rate limits."""
    require(isinstance(pin, str) and len(pin) >= 8 and len(pin) <= 128, "INVALID_INPUT")
    require(not pin.isdigit() or len(set(pin)) >= 5, "INVALID_INPUT")
    random_salt = salt or secrets.token_bytes(24)
    require(isinstance(random_salt, bytes) and len(random_salt) == 24, "INVALID_INPUT")
    stretched = hashlib.scrypt(pin.encode(), salt=random_salt, n=2**14, r=8, p=1, dklen=32)
    return b64u(random_salt), b64u(stretched)


def check_pin(pin: str, salt_b64: str, expected_b64: str) -> bool:
    if not isinstance(pin, str) or len(pin) > 128:
        return False
    try:
        salt = unb64u(salt_b64)
        expected = unb64u(expected_b64)
        if len(salt) != 24 or len(expected) != 32:
            return False
        actual = hashlib.scrypt(pin.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(actual, expected)
    except (ValueError, LabError):
        return False


@dataclass(frozen=True)
class SigningKey:
    key_id: str
    secret: bytes
    activated_at: int
    retired_at: int | None = None

    def __post_init__(self) -> None:
        require(self.key_id.startswith("sim_key_") and 10 <= len(self.key_id) <= 60, "INVALID_INPUT")
        require(isinstance(self.secret, bytes) and len(self.secret) >= 32, "INVALID_INPUT")
        require(type(self.activated_at) is int and self.activated_at > 0, "INVALID_INPUT")
        if self.retired_at is not None:
            require(self.retired_at > self.activated_at, "INVALID_INPUT")

    def active_at(self, moment: int) -> bool:
        return moment >= self.activated_at and (self.retired_at is None or moment < self.retired_at)

    def sign(self, payload: bytes) -> str:
        return b64u(hmac.digest(self.secret, payload, "sha256"))

    def verify(self, payload: bytes, signature: str) -> bool:
        return hmac.compare_digest(self.sign(payload), signature)


class KeyRing:
    def __init__(self, keys: tuple[SigningKey, ...], current_key_id: str):
        require(bool(keys), "INVALID_INPUT")
        self._keys = {key.key_id: key for key in keys}
        require(len(self._keys) == len(keys), "INVALID_INPUT")
        require(current_key_id in self._keys, "INVALID_INPUT")
        self.current = current_key_id

    def sign_message(self, data: dict[str, object], now: int) -> dict[str, str]:
        key = self._keys[self.current]
        require(key.active_at(now), "UNAUTHORIZED")
        payload = canonical(data)
        return {"kid": key.key_id, "payload": b64u(payload), "sig": key.sign(payload)}

    def verify_message(self, envelope: dict[str, str], now: int) -> dict[str, object]:
        require(isinstance(envelope, dict) and set(envelope) == {"kid", "payload", "sig"}, "INVALID_INPUT")
        key = self._keys.get(envelope["kid"])
        require(key is not None and key.active_at(now), "UNAUTHORIZED")
        raw = unb64u(envelope["payload"])
        if not key.verify(raw, envelope["sig"]):
            raise LabError("UNAUTHORIZED")
        import json
        try:
            data = json.loads(raw)
        except Exception as exc:
            raise LabError("INVALID_INPUT") from exc
        require(isinstance(data, dict) and canonical(data) == raw, "INVALID_INPUT")
        return data

    def rotate(self, key: SigningKey) -> "KeyRing":
        require(key.key_id not in self._keys, "CONFLICT")
        return KeyRing(tuple(self._keys.values()) + (key,), key.key_id)
