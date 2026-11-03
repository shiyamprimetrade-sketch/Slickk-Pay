"""Merchant notification outbox (offline staging model, no automatic delivery).

Enqueue and lease are deterministic; a separate reviewed worker would be
required for real network delivery. An outbox event must not be interpreted as
funds transfer, a gateway-authoritative webhook or proof of bank settlement.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from threading import RLock
from typing import Mapping, Sequence

from .primitives import (
    ConflictError, EvidenceError, PolicyError, NotFoundError, canonical_json,
    evidence_hash, reference, safe_key, timestamp, utc_iso,
)
from .security import HttpsEndpointPolicy, KeyRing, SignedEnvelope


class DeliveryState(str, Enum):
    QUEUED = "queued"
    LEASED = "leased"
    ACKNOWLEDGED = "acknowledged"
    RETRY_SCHEDULED = "retry_scheduled"
    EXHAUSTED = "exhausted"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    event_ref: str
    merchant_id: str
    event_type: str
    endpoint: str
    payload: Mapping[str, object]
    created_at: datetime
    payload_digest: str

    def __post_init__(self) -> None:
        reference(self.event_ref, field_name="event_ref")
        reference(self.merchant_id, field_name="merchant_id")
        safe_key(self.event_type, field_name="event_type")
        timestamp(self.created_at)
        if self.payload_digest != evidence_hash(dict(self.payload)):
            raise EvidenceError("Outbox payload does not match digest")
        if len(canonical_json(dict(self.payload))) > 16_384:
            raise EvidenceError("Outbox payload exceeds limit")

    def public_dict(self) -> dict:
        return {"event_ref": self.event_ref, "merchant_id": self.merchant_id,
                "event_type": self.event_type, "created_at": utc_iso(self.created_at),
                "payload_digest": self.payload_digest}


@dataclass(frozen=True, slots=True)
class DeliveryAttempt:
    event_ref: str
    attempt_number: int
    began_at: datetime
    lease_until: datetime
    status_code: int | None = None
    outcome: str = "leased"

    def __post_init__(self) -> None:
        reference(self.event_ref, field_name="event_ref")
        if not 1 <= self.attempt_number <= 100:
            raise EvidenceError("Invalid delivery attempt number")
        timestamp(self.began_at)
        timestamp(self.lease_until)
        if self.lease_until <= self.began_at:
            raise EvidenceError("Delivery lease must be positive")
        if self.status_code is not None and not 100 <= self.status_code <= 599:
            raise EvidenceError("Invalid HTTP status")
        safe_key(self.outcome, field_name="outcome")


@dataclass(frozen=True, slots=True)
class OutboxRecord:
    event: OutboxEvent
    state: DeliveryState
    attempts: tuple[DeliveryAttempt, ...]
    next_attempt_at: datetime
    lease_token_digest: str | None = None

    def __post_init__(self) -> None:
        timestamp(self.next_attempt_at)
        if not isinstance(self.state, DeliveryState):
            raise EvidenceError("Invalid outbox state")

    def public_dict(self) -> dict:
        return {**self.event.public_dict(), "state": self.state.value,
                "attempt_count": len(self.attempts),
                "next_attempt_at": utc_iso(self.next_attempt_at)}


class RetryPolicy:
    """Bounded exponential retry with deterministic event-scoped jitter."""

    def __init__(self, *, max_attempts: int = 6, initial_seconds: int = 10,
                 maximum_seconds: int = 3600) -> None:
        if not 1 <= max_attempts <= 20:
            raise EvidenceError("Invalid retry count")
        if not 1 <= initial_seconds <= maximum_seconds <= 86_400:
            raise EvidenceError("Invalid retry intervals")
        self.max_attempts = max_attempts
        self.initial_seconds = initial_seconds
        self.maximum_seconds = maximum_seconds

    def next_delay(self, *, event_ref: str, attempt: int) -> int:
        reference(event_ref, field_name="event_ref")
        if not 1 <= attempt <= self.max_attempts:
            raise EvidenceError("Retry attempt is out of range")
        exponential = min(self.maximum_seconds, self.initial_seconds * 2 ** (attempt - 1))
        jitter_bound = max(1, exponential // 5)
        jitter = int(evidence_hash({"event": event_ref, "attempt": attempt})[:6], 16) % jitter_bound
        return min(self.maximum_seconds, exponential + jitter)


class Outbox:
    """Non-networking simulation of persistent-at-least-once delivery semantics."""

    def __init__(self, endpoint_policy: HttpsEndpointPolicy,
                 *, retry_policy: RetryPolicy | None = None, enabled: bool = False) -> None:
        if not isinstance(endpoint_policy, HttpsEndpointPolicy):
            raise EvidenceError("Expected HttpsEndpointPolicy")
        self.endpoint_policy = endpoint_policy
        self.retry_policy = retry_policy or RetryPolicy()
        self.enabled = enabled
        self._lock = RLock()
        self._records: dict[str, OutboxRecord] = {}

    def enqueue(self, *, merchant_id: str, event_ref: str, event_type: str,
                endpoint: str, payload: Mapping[str, object],
                created_at: datetime) -> OutboxRecord:
        reference(merchant_id, field_name="merchant_id")
        reference(event_ref, field_name="event_ref")
        safe_key(event_type, field_name="event_type")
        self.endpoint_policy.validate(endpoint)
        created_at = timestamp(created_at)
        if not isinstance(payload, Mapping):
            raise EvidenceError("Outbox payload must be a mapping")
        digest = evidence_hash(dict(payload))
        event = OutboxEvent(event_ref, merchant_id, event_type, endpoint,
                            dict(payload), created_at, digest)
        with self._lock:
            if event_ref in self._records:
                previous = self._records[event_ref]
                if previous.event != event:
                    raise ConflictError("Outbox event reused with different payload")
                return previous
            state = DeliveryState.QUEUED if self.enabled else DeliveryState.DISABLED
            record = OutboxRecord(event, state, (), created_at)
            self._records[event_ref] = record
            return record

    def get(self, event_ref: str, *, merchant_id: str) -> OutboxRecord:
        reference(event_ref, field_name="event_ref")
        reference(merchant_id, field_name="merchant_id")
        with self._lock:
            record = self._records.get(event_ref)
            if record is None or record.event.merchant_id != merchant_id:
                raise NotFoundError("Outbox event not found for merchant")
            return record

    def lease(self, *, event_ref: str, merchant_id: str, at: datetime,
              lease_token: str, lease_seconds: int = 30) -> OutboxRecord:
        reference(lease_token, field_name="lease_token")
        at = timestamp(at)
        if not 1 <= lease_seconds <= 300:
            raise EvidenceError("Invalid lease duration")
        with self._lock:
            record = self.get(event_ref, merchant_id=merchant_id)
            if record.state not in (DeliveryState.QUEUED, DeliveryState.RETRY_SCHEDULED, DeliveryState.LEASED):
                raise PolicyError("Event cannot be leased in current state")
            if record.state == DeliveryState.LEASED and record.attempts[-1].lease_until > at:
                raise ConflictError("Another worker owns the active lease")
            if timestamp(record.next_attempt_at) > at:
                raise PolicyError("Delivery retry is not yet due")
            count = len(record.attempts) + 1
            if count > self.retry_policy.max_attempts:
                raise PolicyError("Event has exhausted retry policy")
            attempt = DeliveryAttempt(event_ref, count, at,
                                      at + timedelta(seconds=lease_seconds))
            new = OutboxRecord(record.event, DeliveryState.LEASED,
                               record.attempts + (attempt,), record.next_attempt_at,
                               evidence_hash({"lease_token": lease_token}))
            self._records[event_ref] = new
            return new

    def finish(self, *, merchant_id: str, event_ref: str, lease_token: str,
               at: datetime, status_code: int | None) -> OutboxRecord:
        reference(lease_token, field_name="lease_token")
        at = timestamp(at)
        with self._lock:
            record = self.get(event_ref, merchant_id=merchant_id)
            if record.state != DeliveryState.LEASED or not record.attempts:
                raise PolicyError("Event has no outstanding delivery lease")
            if record.lease_token_digest != evidence_hash({"lease_token": lease_token}):
                raise PolicyError("Lease token mismatch")
            lease = record.attempts[-1]
            if at > lease.lease_until:
                raise PolicyError("Lease expired")
            if status_code is not None and (isinstance(status_code, bool)
                                            or not isinstance(status_code, int)
                                            or not 100 <= status_code <= 599):
                raise EvidenceError("Invalid HTTP status")
            successful = status_code is not None and 200 <= status_code < 300
            exhausted = not successful and lease.attempt_number >= self.retry_policy.max_attempts
            state = (DeliveryState.ACKNOWLEDGED if successful else
                     DeliveryState.EXHAUSTED if exhausted else DeliveryState.RETRY_SCHEDULED)
            outcome = "acknowledged" if successful else "exhausted" if exhausted else "retry"
            completed = DeliveryAttempt(event_ref, lease.attempt_number, lease.began_at,
                                        lease.lease_until, status_code, outcome)
            next_at = (at + timedelta(seconds=self.retry_policy.next_delay(
                event_ref=event_ref, attempt=lease.attempt_number))
                if state == DeliveryState.RETRY_SCHEDULED else at)
            new = OutboxRecord(record.event, state, record.attempts[:-1] + (completed,),
                               next_at, None)
            self._records[event_ref] = new
            return new

    def list_due(self, *, merchant_id: str, at: datetime,
                 limit: int = 100) -> tuple[OutboxRecord, ...]:
        reference(merchant_id, field_name="merchant_id")
        at = timestamp(at)
        if not 1 <= limit <= 1000:
            raise EvidenceError("Invalid due-list limit")
        with self._lock:
            due = [r for r in self._records.values()
                   if r.event.merchant_id == merchant_id
                   and r.state in (DeliveryState.QUEUED, DeliveryState.RETRY_SCHEDULED)
                   and r.next_attempt_at <= at]
            return tuple(sorted(due, key=lambda x: (x.next_attempt_at, x.event.event_ref))[:limit])

    def stats(self, *, merchant_id: str) -> dict:
        reference(merchant_id, field_name="merchant_id")
        with self._lock:
            records = [x for x in self._records.values() if x.event.merchant_id == merchant_id]
            return {"merchant_id": merchant_id, "event_count": len(records),
                    "queued": sum(x.state == DeliveryState.QUEUED for x in records),
                    "acknowledged": sum(x.state == DeliveryState.ACKNOWLEDGED for x in records),
                    "retry_pending": sum(x.state == DeliveryState.RETRY_SCHEDULED for x in records),
                    "exhausted": sum(x.state == DeliveryState.EXHAUSTED for x in records),
                    "network_delivery_implemented": False}
