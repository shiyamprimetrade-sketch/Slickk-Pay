"""Transactional outbox for synthetic financial notifications.

The outbox does not send network requests. An authorized test worker can lease
and acknowledge messages; the transport is deliberately external. Delivery is
at-least-once, so consumers must use message_id for deduplication.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
import json
import secrets
from sqlalchemy import select, insert, update, and_
from sqlalchemy.engine import Connection
from .schema import outbox, chain, journals
from .store import SandboxStore, utc_now
from .posting import canonical, digest
from .guard import sim_id, event_key
from .errors import Conflict, InvalidValue, MissingRecord, StateError, AuthorizationError


_ALLOWED_DESTINATIONS = frozenset({"sim_customer_notice", "sim_agent_notice",
                                  "sim_merchant_notice", "sim_operator_audit"})
_ALLOWED_KEYS = frozenset({"event_id", "type", "amount_poisha", "currency",
                          "status", "timestamp", "merchant_reference", "risk_code"})


@dataclass(frozen=True)
class OutboxMessage:
    message_id: str
    event_id: str
    destination: str
    state: str
    attempts: int
    next_attempt_at: str
    lease_until: str | None
    payload_digest: str
    simulation: bool = True


@dataclass(frozen=True)
class LeasedMessage:
    message: OutboxMessage
    payload: dict[str, object]
    lease_token: str
    simulation: bool = True


class DurableOutbox:
    """Database-first event publication with bounded retries and replay control."""

    def __init__(self, store: SandboxStore, *, max_attempts: int = 6):
        self.store = store
        if not 1 <= max_attempts <= 30:
            raise InvalidValue("Invalid maximum attempts")
        self.max_attempts = max_attempts

    def _validate_payload(self, payload: dict[str, object]) -> str:
        if not isinstance(payload, dict) or not payload or not payload.keys() <= _ALLOWED_KEYS:
            raise InvalidValue("Outbox contains disallowed fields")
        if "currency" in payload and payload["currency"] != "BDT":
            raise InvalidValue("Non-BDT sandbox notifications forbidden")
        if "amount_poisha" in payload:
            v = payload["amount_poisha"]
            if type(v) is not int or not 0 <= v <= 10**14:
                raise InvalidValue("Unbounded or noninteger notification amount")
        if "type" not in payload or not isinstance(payload["type"], str):
            raise InvalidValue("Notification needs a bounded event type")
        if len(canonical(payload).encode()) > 4096:
            raise InvalidValue("Notification payload too large")
        return canonical(payload)

    def enqueue_in_transaction(self, db: Connection, *, event_id: str,
                               destination: str, payload: dict[str, object]) -> OutboxMessage:
        sim_id(event_id, "journal event")
        if destination not in _ALLOWED_DESTINATIONS:
            raise InvalidValue("Unauthorized destination")
        serialized = self._validate_payload(payload)
        source = db.execute(select(journals.c.event_id).where(journals.c.event_id == event_id)).scalar_one_or_none()
        if source is None:
            raise MissingRecord("Notifications must reference committed journal event")
        payload_digest = sha256(serialized.encode()).hexdigest()
        message_id = "sim_msg_" + sha256((event_id+"|"+destination).encode()).hexdigest()[:40]
        old = db.execute(select(outbox).where(outbox.c.message_id == message_id).with_for_update()).mappings().first()
        if old:
            if old["payload_digest"] != payload_digest:
                raise Conflict("Event/destination reused with altered payload")
            return self._view(old)
        now = utc_now()
        db.execute(insert(outbox).values(message_id=message_id, event_id=event_id,
                   destination=destination, payload_digest=payload_digest,
                   payload=serialized, state="ready", attempts=0,
                   next_attempt_at=now, created_at=now))
        return self._view(db.execute(select(outbox).where(outbox.c.message_id == message_id)).mappings().one())

    def enqueue(self, *, event_id: str, destination: str, payload: dict[str, object]) -> OutboxMessage:
        with self.store.transaction() as db:
            return self.enqueue_in_transaction(db, event_id=event_id, destination=destination, payload=payload)

    @staticmethod
    def _view(row) -> OutboxMessage:
        return OutboxMessage(row["message_id"], row["event_id"], row["destination"],
                             row["state"], row["attempts"], row["next_attempt_at"],
                             row["lease_until"], row["payload_digest"])

    def lease(self, *, limit: int = 10, ttl_seconds: int = 60) -> tuple[LeasedMessage, ...]:
        if not 1 <= limit <= 100 or not 15 <= ttl_seconds <= 300:
            raise InvalidValue("Invalid outbox lease parameters")
        now = datetime.now(timezone.utc)
        now_text = now.isoformat(timespec="microseconds")
        until = (now+timedelta(seconds=ttl_seconds)).isoformat(timespec="microseconds")
        output: list[LeasedMessage] = []
        with self.store.transaction() as db:
            # Postgres skip_locked allows multiple independent workers. SQLite
            # BEGIN IMMEDIATE gives local test writers single-worker semantics.
            query = select(outbox).where(
                ((outbox.c.state == "ready") & (outbox.c.next_attempt_at <= now_text)) |
                ((outbox.c.state == "leased") & (outbox.c.lease_until < now_text))
            ).order_by(outbox.c.next_attempt_at).limit(limit)
            if self.store.dialect == "postgresql":
                query = query.with_for_update(skip_locked=True)
            rows = db.execute(query).mappings().all()
            for row in rows:
                token = secrets.token_hex(24)
                attempts = row["attempts"]+1
                if attempts > self.max_attempts:
                    db.execute(update(outbox).where(outbox.c.message_id == row["message_id"])
                               .values(state="dead", lease_until=None, lease_token=None))
                    continue
                db.execute(update(outbox).where(outbox.c.message_id == row["message_id"])
                           .values(state="leased", attempts=attempts,
                                   lease_until=until, lease_token=token))
                current = db.execute(select(outbox).where(outbox.c.message_id == row["message_id"])).mappings().one()
                output.append(LeasedMessage(self._view(current), json.loads(current["payload"]), token))
        return tuple(output)

    def ack(self, *, message_id: str, token: str) -> OutboxMessage:
        sim_id(message_id, "message")
        self._check_token(token)
        with self.store.transaction() as db:
            row = self._lookup(db, message_id, lock=True)
            if row["state"] == "delivered":
                # A duplicate ACK is safe if it is the same last lease; token
                # is cleared after delivery and no replay is accepted.
                raise StateError("Message was already acknowledged")
            self._require_current_lease(row, token)
            db.execute(update(outbox).where(outbox.c.message_id == message_id)
                       .values(state="delivered", lease_until=None, lease_token=None))
            return self._view(self._lookup(db, message_id))

    def fail(self, *, message_id: str, token: str, reason_code: str) -> OutboxMessage:
        sim_id(message_id, "message")
        self._check_token(token)
        if reason_code not in ("TIMEOUT", "TRANSPORT_FAILURE", "RECIPIENT_UNAVAILABLE", "TRANSIENT_5XX"):
            raise InvalidValue("Only redacted transport reason codes allowed")
        with self.store.transaction() as db:
            row = self._lookup(db, message_id, lock=True)
            self._require_current_lease(row, token)
            attempts = row["attempts"]
            delay = min(3600, 2**min(attempts, 12))
            due = (datetime.now(timezone.utc)+timedelta(seconds=delay)).isoformat(timespec="microseconds")
            state = "dead" if attempts >= self.max_attempts else "ready"
            db.execute(update(outbox).where(outbox.c.message_id == message_id)
                       .values(state=state, lease_until=None, lease_token=None,
                               next_attempt_at=due))
            return self._view(self._lookup(db, message_id))

    def _check_token(self, value: str) -> None:
        if not isinstance(value, str) or not 48 <= len(value) <= 96:
            raise AuthorizationError("Invalid lease token")

    def _require_current_lease(self, row, token: str) -> None:
        if row["state"] != "leased" or not row["lease_token"] or not hmac.compare_digest(row["lease_token"],token):
            raise AuthorizationError("Notification lease is not owned")
        if row["lease_until"] < utc_now():
            raise StateError("Notification lease expired")

    def _lookup(self, db: Connection, message_id: str, *, lock: bool = False):
        query = select(outbox).where(outbox.c.message_id == message_id)
        if lock:
            query = query.with_for_update()
        row = db.execute(query).mappings().first()
        if row is None:
            raise MissingRecord("Outbox message missing")
        return row

    def status(self, message_id: str) -> OutboxMessage:
        sim_id(message_id, "message")
        with self.store.engine.connect() as db:
            return self._view(self._lookup(db, message_id))

    def statistics(self) -> dict[str, int | bool]:
        from sqlalchemy import func
        with self.store.engine.connect() as db:
            rows = db.execute(select(outbox.c.state,func.count()).group_by(outbox.c.state)).all()
        summary = {k: 0 for k in ("ready", "leased", "delivered", "dead")}
        summary.update(dict(rows))
        summary["simulation"] = True
        return summary
