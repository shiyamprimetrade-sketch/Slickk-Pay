"""Independent HMAC signing, key rotation, replay checks and URL boundaries.

Designed for outbound merchant notification preparation and manual evidence
verification. These helpers do not authenticate SSLCOMMERZ IPNs; gateway IPNs
must still use the independent validation API in `app.live`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import hmac
from threading import RLock
from typing import Mapping
from urllib.parse import urlsplit
import re

from .primitives import (
    ConflictError, EvidenceError, PolicyError, canonical_json, reference,
    safe_key, timestamp, utc_iso,
)


@dataclass(frozen=True, slots=True)
class SigningKey:
    key_id: str
    secret: bytes
    valid_from: datetime
    valid_until: datetime
    active_for_signing: bool = True

    def __post_init__(self) -> None:
        reference(self.key_id, field_name="key_id", max_length=40)
        if not isinstance(self.secret, bytes) or not 32 <= len(self.secret) <= 4096:
            raise EvidenceError("HMAC key must contain 32–4096 random bytes")
        if timestamp(self.valid_until) <= timestamp(self.valid_from):
            raise EvidenceError("Invalid key validity interval")
        if not isinstance(self.active_for_signing, bool):
            raise EvidenceError("Invalid signing key mode")


@dataclass(frozen=True, slots=True)
class SignedEnvelope:
    key_id: str
    nonce: str
    issued_at: datetime
    expires_at: datetime
    signature: str
    version: str = "v1"

    def __post_init__(self) -> None:
        reference(self.key_id, field_name="key_id")
        reference(self.nonce, field_name="nonce")
        timestamp(self.issued_at)
        timestamp(self.expires_at)
        if timestamp(self.expires_at) <= timestamp(self.issued_at):
            raise EvidenceError("Invalid signature expiry")
        if self.version != "v1" or not re.fullmatch(r"[0-9a-f]{64}", self.signature):
            raise EvidenceError("Unsupported signed envelope")

    def as_headers(self) -> dict[str, str]:
        return {"X-Slickk-Signature": self.version + "=" + self.signature,
                "X-Slickk-Key-Id": self.key_id,
                "X-Slickk-Nonce": self.nonce,
                "X-Slickk-Issued-At": utc_iso(self.issued_at),
                "X-Slickk-Expires-At": utc_iso(self.expires_at)}


class KeyRing:
    """Multiple HMAC keys with explicit signing/verification time windows."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._keys: dict[str, SigningKey] = {}
        self._current: str | None = None

    def register(self, key: SigningKey, *, make_current: bool = False) -> None:
        if not isinstance(key, SigningKey):
            raise EvidenceError("Expected SigningKey")
        with self._lock:
            if key.key_id in self._keys:
                raise ConflictError("Signing key ID cannot be reused")
            if make_current and not key.active_for_signing:
                raise PolicyError("Verification-only key cannot become current")
            self._keys[key.key_id] = key
            if make_current:
                self._current = key.key_id

    def select_current(self, key_id: str, *, at: datetime) -> None:
        reference(key_id, field_name="key_id")
        with self._lock:
            key = self._keys.get(key_id)
            if key is None or not key.active_for_signing:
                raise PolicyError("Unknown or non-signing key")
            if not timestamp(key.valid_from) <= timestamp(at) < timestamp(key.valid_until):
                raise PolicyError("Key not currently valid")
            self._current = key_id

    @staticmethod
    def _message(payload: Mapping, *, purpose: str, nonce: str,
                 issued_at: datetime, expires_at: datetime) -> bytes:
        safe_key(purpose, field_name="purpose")
        reference(nonce, field_name="nonce")
        return canonical_json({"version": "slickk-notification-v1", "purpose": purpose,
                               "nonce": nonce, "issued": utc_iso(issued_at),
                               "expires": utc_iso(expires_at), "payload": dict(payload)})

    def sign(self, payload: Mapping, *, purpose: str, nonce: str,
             at: datetime, ttl_seconds: int = 300) -> SignedEnvelope:
        timestamp(at)
        if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or not 1 <= ttl_seconds <= 3600:
            raise EvidenceError("Signature TTL out of bounds")
        with self._lock:
            if self._current is None:
                raise PolicyError("No signing key configured")
            key = self._keys[self._current]
            expires = timestamp(at) + timedelta(seconds=ttl_seconds)
            if not key.active_for_signing or timestamp(at) < timestamp(key.valid_from) or expires > timestamp(key.valid_until):
                raise PolicyError("Current key does not cover signature validity")
            message = self._message(payload, purpose=purpose, nonce=nonce,
                                    issued_at=at, expires_at=expires)
            signature = hmac.new(key.secret, message, sha256).hexdigest()
            return SignedEnvelope(key.key_id, nonce, at, expires, signature)

    def verify(self, payload: Mapping, *, purpose: str,
               envelope: SignedEnvelope, at: datetime,
               max_skew_seconds: int = 60) -> bool:
        if not isinstance(envelope, SignedEnvelope):
            return False
        at = timestamp(at)
        if not 0 <= max_skew_seconds <= 300:
            raise EvidenceError("Invalid signature clock skew")
        with self._lock:
            key = self._keys.get(envelope.key_id)
            if key is None:
                return False
            if timestamp(envelope.issued_at) - timedelta(seconds=max_skew_seconds) > at:
                return False
            if at >= timestamp(envelope.expires_at):
                return False
            if timestamp(key.valid_from) > timestamp(envelope.issued_at):
                return False
            if timestamp(envelope.expires_at) > timestamp(key.valid_until):
                return False
            try:
                message = self._message(payload, purpose=purpose, nonce=envelope.nonce,
                                        issued_at=envelope.issued_at, expires_at=envelope.expires_at)
            except EvidenceError:
                return False
            expected = hmac.new(key.secret, message, sha256).hexdigest()
            return hmac.compare_digest(expected, envelope.signature)

    def retire(self, key_id: str, *, at: datetime) -> None:
        """Remove signing capability; old evidence remains verifiable until expiry."""
        reference(key_id, field_name="key_id")
        timestamp(at)
        with self._lock:
            original = self._keys.get(key_id)
            if original is None:
                raise EvidenceError("Unknown key")
            self._keys[key_id] = SigningKey(original.key_id, original.secret,
                                            original.valid_from, original.valid_until, False)
            if self._current == key_id:
                self._current = None

    def public_manifest(self, *, at: datetime) -> dict:
        at = timestamp(at)
        with self._lock:
            return {"key_ids": sorted(self._keys), "current_key_id": self._current,
                    "active_count": sum(k.active_for_signing and k.valid_from <= at < k.valid_until
                                        for k in self._keys.values()),
                    "secrets_exposed": False}


class NonceRegistry:
    """Replay guard for merchant notification consumers; memory-only test primitive."""

    def __init__(self, *, capacity: int = 100_000) -> None:
        if isinstance(capacity, bool) or not isinstance(capacity, int) or not 1 <= capacity <= 1_000_000:
            raise EvidenceError("Invalid nonce capacity")
        self.capacity = capacity
        self._lock = RLock()
        self._seen: dict[tuple[str, str], datetime] = {}

    def consume(self, *, key_id: str, nonce: str, expires_at: datetime, now: datetime) -> bool:
        reference(key_id, field_name="key_id")
        reference(nonce, field_name="nonce")
        now = timestamp(now)
        expires_at = timestamp(expires_at)
        if expires_at <= now:
            return False
        with self._lock:
            self._seen = {k: v for k, v in self._seen.items() if v > now}
            key = key_id, nonce
            if key in self._seen:
                return False
            if len(self._seen) >= self.capacity:
                raise PolicyError("Nonce registry full; reject rather than evict live tokens")
            self._seen[key] = expires_at
            return True

    def count(self, *, at: datetime) -> int:
        at = timestamp(at)
        with self._lock:
            return sum(expiry > at for expiry in self._seen.values())


class HttpsEndpointPolicy:
    """Strict merchant webhook allowlist; does not perform DNS or HTTP requests."""

    def __init__(self, hosts: set[str]) -> None:
        if not isinstance(hosts, set) or not hosts:
            raise EvidenceError("Webhook host allowlist must be nonempty")
        self.hosts = frozenset(self._hostname(h) for h in hosts)

    @staticmethod
    def _hostname(host: str) -> str:
        if not isinstance(host, str) or not re.fullmatch(r"[a-z0-9.-]{4,253}", host):
            raise EvidenceError("Invalid endpoint host")
        if host.startswith(".") or host.endswith(".") or ".." in host:
            raise EvidenceError("Invalid endpoint hostname")
        if host in {"localhost", "127.0.0.1", "0.0.0.0"} or host.endswith(".local"):
            raise PolicyError("Internal hosts cannot be used for outbound webhooks")
        return host

    def validate(self, url: str) -> str:
        if not isinstance(url, str) or len(url) > 2048:
            raise EvidenceError("Invalid callback URL")
        try:
            parts = urlsplit(url)
            hostname = (parts.hostname or "").lower()
            port = parts.port
        except ValueError as exc:
            raise EvidenceError("Invalid callback authority") from exc
        if (parts.scheme != "https" or parts.username or parts.password or parts.fragment
                or port not in (None, 443) or hostname not in self.hosts):
            raise PolicyError("Webhook endpoint is not on the HTTPS allowlist")
        if not parts.path.startswith("/") or "\\" in parts.path or "//" in parts.path:
            raise PolicyError("Invalid callback path")
        if parts.query and any(token in parts.query.lower() for token in ("token=", "key=", "password=")):
            raise PolicyError("Do not place credentials in URL parameters")
        return url
