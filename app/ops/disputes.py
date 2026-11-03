"""Offline merchant dispute desk with human review and evidence provenance.

This is a workflow tracker, not a refund or chargeback submission API.
Actions are advisory: no financial status or bank/gateway transaction changes.
No raw personal information, document files or cardholder data are persisted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from threading import RLock
from typing import Mapping, Sequence

from .primitives import (
    ConflictError, EvidenceError, NotFoundError, PolicyError, evidence_hash,
    reference, safe_key, timestamp, utc_iso,
)


class CaseType(str, Enum):
    DUPLICATE_CHARGE = "duplicate_charge"
    SERVICE_NOT_RECEIVED = "service_not_received"
    REFUND_REQUEST = "refund_request"
    UNAUTHORIZED_PAYMENT = "unauthorized_payment"
    CHARGEBACK_NOTICE = "chargeback_notice"
    PROVIDER_DISCREPANCY = "provider_discrepancy"
    SETTLEMENT_MISMATCH = "settlement_mismatch"
    OTHER = "other"


class CaseState(str, Enum):
    OPEN = "open"
    TRIAGE = "triage"
    WAITING_MERCHANT = "waiting_merchant"
    WAITING_PROVIDER = "waiting_provider"
    EVIDENCE_COMPLETE = "evidence_complete"
    RESOLVED = "resolved"
    REJECTED = "rejected"
    CLOSED = "closed"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


ALLOWED_TRANSITIONS: dict[CaseState, frozenset[CaseState]] = {
    CaseState.OPEN: frozenset({CaseState.TRIAGE, CaseState.REJECTED}),
    CaseState.TRIAGE: frozenset({CaseState.WAITING_MERCHANT, CaseState.WAITING_PROVIDER,
                                CaseState.EVIDENCE_COMPLETE, CaseState.REJECTED}),
    CaseState.WAITING_MERCHANT: frozenset({CaseState.TRIAGE, CaseState.EVIDENCE_COMPLETE}),
    CaseState.WAITING_PROVIDER: frozenset({CaseState.TRIAGE, CaseState.EVIDENCE_COMPLETE}),
    CaseState.EVIDENCE_COMPLETE: frozenset({CaseState.WAITING_MERCHANT, CaseState.WAITING_PROVIDER,
                                           CaseState.RESOLVED, CaseState.REJECTED}),
    CaseState.RESOLVED: frozenset({CaseState.CLOSED}),
    CaseState.REJECTED: frozenset({CaseState.CLOSED}),
    CaseState.CLOSED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    evidence_id: str
    kind: str
    sha256_digest: str
    verified_by: str | None
    received_at: datetime

    def __post_init__(self) -> None:
        reference(self.evidence_id, field_name="evidence_id")
        safe_key(self.kind, field_name="kind")
        if not isinstance(self.sha256_digest, str) or len(self.sha256_digest) != 64:
            raise EvidenceError("Evidence requires SHA-256 digest")
        if any(c not in "0123456789abcdef" for c in self.sha256_digest):
            raise EvidenceError("Invalid SHA-256 digest")
        if self.verified_by is not None:
            reference(self.verified_by, field_name="reviewer")
        timestamp(self.received_at)

    def summary(self) -> dict[str, str | None]:
        return {"evidence_id": self.evidence_id, "kind": self.kind,
                "sha256_digest": self.sha256_digest,
                "verified_by": self.verified_by,
                "received_at": utc_iso(self.received_at)}


@dataclass(frozen=True, slots=True)
class CaseEvent:
    event_ref: str
    event_kind: str
    from_state: CaseState | None
    to_state: CaseState
    actor: str
    occurred_at: datetime
    evidence_digest: str
    prior_hash: str
    event_hash: str

    def __post_init__(self) -> None:
        reference(self.event_ref, field_name="event_ref")
        safe_key(self.event_kind, field_name="event_kind")
        reference(self.actor, field_name="actor")
        timestamp(self.occurred_at)

    def verify(self) -> bool:
        return self.event_hash == evidence_hash({
            "event_ref": self.event_ref, "event_kind": self.event_kind,
            "from_state": self.from_state.value if self.from_state else None,
            "to_state": self.to_state.value, "actor": self.actor,
            "occurred_at": utc_iso(self.occurred_at),
            "evidence_digest": self.evidence_digest, "prior_hash": self.prior_hash,
        })


@dataclass(frozen=True, slots=True)
class DisputeCase:
    case_id: str
    merchant_id: str
    payment_ref: str
    case_type: CaseType
    severity: Severity
    state: CaseState
    opened_at: datetime
    deadline_at: datetime
    updated_at: datetime
    assigned_to: str | None
    evidence: tuple[EvidenceItem, ...]
    events: tuple[CaseEvent, ...]

    def __post_init__(self) -> None:
        for name in ("case_id", "merchant_id", "payment_ref"):
            reference(getattr(self, name), field_name=name)
        if timestamp(self.deadline_at) <= timestamp(self.opened_at):
            raise EvidenceError("Dispute deadline must follow opening")
        if timestamp(self.updated_at) < timestamp(self.opened_at):
            raise EvidenceError("Dispute updated timestamp is invalid")

    def overdue(self, at: datetime) -> bool:
        return self.state not in (CaseState.CLOSED, CaseState.RESOLVED, CaseState.REJECTED) and timestamp(at) > timestamp(self.deadline_at)

    def summary(self, *, now: datetime) -> dict:
        return {"case_id": self.case_id, "merchant_id": self.merchant_id,
                "payment_ref": self.payment_ref, "type": self.case_type.value,
                "severity": self.severity.value, "state": self.state.value,
                "opened_at": utc_iso(self.opened_at), "deadline_at": utc_iso(self.deadline_at),
                "overdue": self.overdue(now), "assigned_to": self.assigned_to,
                "evidence_count": len(self.evidence), "event_count": len(self.events),
                "audit_root": self.events[-1].event_hash if self.events else "0" * 64,
                "refund_or_dispute_executed": False}


class DisputeDesk:
    """In-memory case registry with per-merchant access controls and hash-linked events."""

    GENESIS = "0" * 64

    def __init__(self) -> None:
        self._lock = RLock()
        self._cases: dict[str, DisputeCase] = {}
        self._events_seen: dict[str, str] = {}

    @staticmethod
    def _event(*, event_ref: str, event_kind: str, before: CaseState | None,
               after: CaseState, actor: str, occurred_at: datetime,
               evidence_digest: str, prior_hash: str) -> CaseEvent:
        data = {"event_ref": event_ref, "event_kind": event_kind,
                "from_state": before.value if before else None,
                "to_state": after.value, "actor": actor,
                "occurred_at": utc_iso(occurred_at),
                "evidence_digest": evidence_digest, "prior_hash": prior_hash}
        return CaseEvent(event_ref, event_kind, before, after, actor, occurred_at,
                         evidence_digest, prior_hash, evidence_hash(data))

    def open(self, *, case_id: str, merchant_id: str, payment_ref: str,
             case_type: CaseType, severity: Severity, actor: str,
             opened_at: datetime, deadline_hours: int = 48) -> DisputeCase:
        for name, value in (("case_id", case_id), ("merchant_id", merchant_id),
                            ("payment_ref", payment_ref), ("actor", actor)):
            reference(value, field_name=name)
        if not isinstance(case_type, CaseType) or not isinstance(severity, Severity):
            raise EvidenceError("Invalid case category")
        if isinstance(deadline_hours, bool) or not isinstance(deadline_hours, int):
            raise EvidenceError("Invalid deadline hours")
        if not 1 <= deadline_hours <= 720:
            raise EvidenceError("Deadline must be 1–720 hours")
        opened_at = timestamp(opened_at)
        with self._lock:
            if case_id in self._cases:
                raise ConflictError("Dispute case already exists")
            event = self._event(event_ref=case_id + ".open", event_kind="opened",
                                before=None, after=CaseState.OPEN, actor=actor,
                                occurred_at=opened_at, evidence_digest=self.GENESIS,
                                prior_hash=self.GENESIS)
            case = DisputeCase(case_id, merchant_id, payment_ref, case_type, severity,
                               CaseState.OPEN, opened_at,
                               opened_at + timedelta(hours=deadline_hours), opened_at,
                               None, (), (event,))
            self._cases[case_id] = case
            self._events_seen[event.event_ref] = case_id
            return case

    def get(self, case_id: str, *, merchant_id: str) -> DisputeCase:
        reference(case_id, field_name="case_id")
        reference(merchant_id, field_name="merchant_id")
        with self._lock:
            case = self._cases.get(case_id)
            if case is None or case.merchant_id != merchant_id:
                raise NotFoundError("Dispute case not found for merchant")
            return case

    def _save(self, before: DisputeCase, *, event_ref: str, event_kind: str,
              new_state: CaseState, actor: str, occurred_at: datetime,
              evidence: tuple[EvidenceItem, ...] | None = None,
              assigned_to: str | None = None, assignment_change: bool = False) -> DisputeCase:
        reference(event_ref, field_name="event_ref")
        reference(actor, field_name="actor")
        occurred_at = timestamp(occurred_at)
        if occurred_at < timestamp(before.updated_at):
            raise EvidenceError("Case events cannot move backward in time")
        if event_ref in self._events_seen:
            raise ConflictError("Case event reference already used")
        existing = before.evidence if evidence is None else evidence
        digest = evidence_hash([x.summary() for x in existing])
        event = self._event(event_ref=event_ref, event_kind=event_kind,
                            before=before.state, after=new_state, actor=actor,
                            occurred_at=occurred_at, evidence_digest=digest,
                            prior_hash=before.events[-1].event_hash)
        updated = DisputeCase(before.case_id, before.merchant_id, before.payment_ref,
                              before.case_type, before.severity, new_state,
                              before.opened_at, before.deadline_at, occurred_at,
                              assigned_to if assignment_change else before.assigned_to,
                              existing, before.events + (event,))
        self._cases[before.case_id] = updated
        self._events_seen[event_ref] = before.case_id
        return updated

    def transition(self, *, merchant_id: str, case_id: str, to_state: CaseState,
                   event_ref: str, actor: str, occurred_at: datetime) -> DisputeCase:
        if not isinstance(to_state, CaseState):
            raise EvidenceError("Unknown dispute state")
        with self._lock:
            case = self.get(case_id, merchant_id=merchant_id)
            if to_state not in ALLOWED_TRANSITIONS[case.state]:
                raise PolicyError("Dispute transition is not permitted")
            if to_state in (CaseState.RESOLVED, CaseState.REJECTED) and not case.evidence:
                raise PolicyError("Resolution requires an evidence digest")
            return self._save(case, event_ref=event_ref, event_kind="transition",
                              new_state=to_state, actor=actor, occurred_at=occurred_at)

    def assign(self, *, merchant_id: str, case_id: str, assignee: str,
               event_ref: str, actor: str, occurred_at: datetime) -> DisputeCase:
        reference(assignee, field_name="assignee")
        with self._lock:
            case = self.get(case_id, merchant_id=merchant_id)
            if case.state == CaseState.CLOSED:
                raise PolicyError("Closed dispute cannot be reassigned")
            return self._save(case, event_ref=event_ref, event_kind="assignment",
                              new_state=case.state, actor=actor, occurred_at=occurred_at,
                              assigned_to=assignee, assignment_change=True)

    def attach(self, *, merchant_id: str, case_id: str, item: EvidenceItem,
               event_ref: str, actor: str, occurred_at: datetime) -> DisputeCase:
        if not isinstance(item, EvidenceItem):
            raise EvidenceError("Expected EvidenceItem")
        with self._lock:
            case = self.get(case_id, merchant_id=merchant_id)
            if case.state in (CaseState.CLOSED, CaseState.RESOLVED, CaseState.REJECTED):
                raise PolicyError("Cannot attach evidence to completed case")
            if any(existing.evidence_id == item.evidence_id for existing in case.evidence):
                raise ConflictError("Duplicate evidence reference")
            if len(case.evidence) >= 50:
                raise PolicyError("Dispute evidence count exceeds limit")
            return self._save(case, event_ref=event_ref, event_kind="evidence_added",
                              new_state=case.state, actor=actor, occurred_at=occurred_at,
                              evidence=case.evidence + (item,))

    def list_cases(self, *, merchant_id: str, now: datetime,
                   state: CaseState | None = None) -> tuple[dict, ...]:
        reference(merchant_id, field_name="merchant_id")
        timestamp(now)
        with self._lock:
            cases = [c for c in self._cases.values()
                     if c.merchant_id == merchant_id and (state is None or c.state == state)]
            return tuple(c.summary(now=now) for c in sorted(cases, key=lambda x: x.case_id))

    def verify_audit(self, *, merchant_id: str, case_id: str) -> bool:
        case = self.get(case_id, merchant_id=merchant_id)
        prior = self.GENESIS
        for event in case.events:
            if event.prior_hash != prior or not event.verify():
                return False
            prior = event.event_hash
        return bool(case.events)

    def dashboard(self, *, merchant_id: str, now: datetime) -> dict:
        cases = self.list_cases(merchant_id=merchant_id, now=now)
        return {"merchant_id": merchant_id, "case_count": len(cases),
                "open_count": sum(c["state"] not in {"closed", "resolved", "rejected"} for c in cases),
                "overdue_count": sum(c["overdue"] for c in cases),
                "critical_count": sum(c["severity"] == "critical" for c in cases),
                "refund_automation_enabled": False}
