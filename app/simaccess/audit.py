"""Redacted append-only access and request journal with independent verification."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import sqlite3
from .errors import LabError, require
from .identifiers import canonical, digest, event_ref, synthetic_id
from .clock import Clock
from .store import LabStore


@dataclass(frozen=True)
class AuditProof:
    checked: int
    valid: bool
    first_broken_sequence: int | None
    head: str
    simulation: bool = True


class AccessAudit:
    def __init__(self, store: LabStore):
        self.store = store

    @staticmethod
    def entry_hash(sequence: int, event_id: str, actor_digest: str, kind: str,
                   event_digest: str, prior: str, created_at: int) -> str:
        data = [sequence, event_id, actor_digest, kind, event_digest, prior, created_at]
        return hashlib.sha256(canonical(data)).hexdigest()

    def append_in_transaction(self, db: sqlite3.Connection, *, actor: str,
                              kind: str, data: dict[str, object], event_id: str) -> int:
        synthetic_id(actor)
        event_ref(event_id)
        require(kind in {
            "fixture_enrolled", "actor_state", "device_registered", "device_revoked",
            "login_succeeded", "login_failed", "logout", "session_rejected",
            "quote_created", "quote_reviewed", "quote_cancelled", "quote_expired",
            "request_cancelled", "cash_checklist", "support_draft", "support_closed",
            "qr_issued", "qr_consumed", "recovery_expired", "outbox_enqueued",
            "cash_acknowledged", "cash_ack_cancelled",
        }, "INVALID_INPUT")
        # Only a sanitized, cryptographic digest of the event body is persisted.
        body_digest = hashlib.sha256(canonical(data)).hexdigest()
        head = db.execute("SELECT sequence,hash FROM lab_audit_head WHERE id=1").fetchone()
        if head is None:
            raise LabError("AUDIT_INTEGRITY")
        sequence = int(head["sequence"]) + 1
        prior = head["hash"]
        now = self.store.clock.now()
        actor_hash = digest(actor)
        entry = self.entry_hash(sequence, event_id, actor_hash, kind, body_digest, prior, now)
        db.execute("INSERT INTO lab_audit(sequence,event_id,actor_digest,event_type,event_digest,previous_hash,entry_hash,created_at) VALUES(?,?,?,?,?,?,?,?)",
                   (sequence, event_id, actor_hash, kind, body_digest, prior, entry, now))
        db.execute("UPDATE lab_audit_head SET sequence=?,hash=? WHERE id=1 AND sequence=? AND hash=?",
                   (sequence, entry, sequence - 1, prior))
        return sequence

    def append(self, **kwargs: object) -> int:
        with self.store.transaction() as db:
            return self.append_in_transaction(db, **kwargs)

    def verify(self) -> AuditProof:
        with self.store.read() as db:
            head = db.execute("SELECT sequence,hash FROM lab_audit_head WHERE id=1").fetchone()
            rows = db.execute("SELECT * FROM lab_audit ORDER BY sequence ASC").fetchall()
        prior = "0" * 64
        expected_sequence = 1
        for row in rows:
            if row["sequence"] != expected_sequence or row["previous_hash"] != prior:
                return AuditProof(len(rows), False, expected_sequence, prior)
            recalculated = self.entry_hash(row["sequence"], row["event_id"], row["actor_digest"],
                                           row["event_type"], row["event_digest"], row["previous_hash"],row["created_at"])
            if row["entry_hash"] != recalculated:
                return AuditProof(len(rows), False, expected_sequence, prior)
            prior = recalculated
            expected_sequence += 1
        if head is None or head["sequence"] != len(rows) or head["hash"] != prior:
            return AuditProof(len(rows), False, expected_sequence, prior)
        return AuditProof(len(rows), True, None, prior)

    def public_summary(self) -> dict[str, object]:
        proof = self.verify()
        return {"simulation": True, "events": proof.checked, "valid": proof.valid,
                "head": proof.head, "last_sequence": proof.checked}

    def assert_intact(self) -> AuditProof:
        proof = self.verify()
        if not proof.valid:
            raise LabError("AUDIT_INTEGRITY")
        return proof
