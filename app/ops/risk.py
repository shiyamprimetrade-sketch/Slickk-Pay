"""Conservative offline merchant transaction risk triage.

The outcome is advisory only. A risk score never authenticates the payment,
authorizes customer funds movement, or overrides bank/SSLCOMMERZ risk rules.
Inputs intentionally exclude customer identity, device tracking and card data.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from threading import RLock
from typing import Iterable, Sequence

from .primitives import (
    ConflictError, EvidenceError, PolicyError, bdt_from_minor, evidence_hash,
    positive_minor, reference, timestamp, utc_iso,
)


class Decision(str, Enum):
    REVIEW = "review"
    ALLOW_TO_VALIDATE = "allow_to_validate"
    REJECT_DUPLICATE = "reject_duplicate"
    HOLD_PROVIDER_RISK = "hold_provider_risk"
    HOLD_MISSING_EVIDENCE = "hold_missing_evidence"


@dataclass(frozen=True, slots=True)
class RiskInput:
    merchant_id: str
    order_ref: str
    transaction_id: str
    amount_poisha: int
    created_at: datetime
    currency: str = "BDT"
    gateway_verified: bool = False
    gateway_risk_level: int | None = None
    merchant_policy_version: int = 1
    invoice_authorized: bool = False
    prior_chargebacks: int = 0
    change_count: int = 0

    def __post_init__(self) -> None:
        for name in ("merchant_id", "order_ref", "transaction_id"):
            reference(getattr(self, name), field_name=name)
        positive_minor(self.amount_poisha)
        timestamp(self.created_at)
        if self.currency != "BDT":
            raise EvidenceError("Risk engine only accepts BDT")
        if not isinstance(self.gateway_verified, bool) or not isinstance(self.invoice_authorized, bool):
            raise EvidenceError("Risk flags must be booleans")
        if self.gateway_risk_level is not None:
            if isinstance(self.gateway_risk_level, bool) or not isinstance(self.gateway_risk_level, int):
                raise EvidenceError("Invalid provider risk level")
            if not 0 <= self.gateway_risk_level <= 10:
                raise EvidenceError("Provider risk level out of range")
        for name in ("prior_chargebacks", "change_count", "merchant_policy_version"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 10_000:
                raise EvidenceError("Invalid integer risk metadata")


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    merchant_id: str
    version: int
    maximum_per_order_poisha: int = 5_000_000
    velocity_window_seconds: int = 300
    maximum_events_per_window: int = 10
    maximum_window_amount_poisha: int = 20_000_000
    threshold_review_score: int = 40
    chargeback_points: int = 20
    changed_order_points: int = 15
    missing_invoice_points: int = 45
    amount_points: int = 25
    velocity_points: int = 40

    def __post_init__(self) -> None:
        reference(self.merchant_id, field_name="merchant_id")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise EvidenceError("Policy version must be positive")
        for name in ("maximum_per_order_poisha", "maximum_window_amount_poisha"):
            positive_minor(getattr(self, name))
        if not 30 <= self.velocity_window_seconds <= 86_400:
            raise EvidenceError("Risk window out of bounds")
        if not 1 <= self.maximum_events_per_window <= 1000:
            raise EvidenceError("Risk event threshold out of bounds")
        for name in ("threshold_review_score", "chargeback_points", "changed_order_points",
                     "missing_invoice_points", "amount_points", "velocity_points"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
                raise EvidenceError("Risk score settings must be integer 0..100")


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    merchant_id: str
    transaction_id: str
    policy_version: int
    assessed_at: datetime
    decision: Decision
    score: int
    reasons: tuple[str, ...]
    velocity_events: int
    velocity_amount_poisha: int
    evidence_digest: str

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100:
            raise EvidenceError("Risk score out of bounds")
        if not isinstance(self.decision, Decision):
            raise EvidenceError("Invalid risk decision")

    def as_dict(self) -> dict:
        return {"merchant_id": self.merchant_id, "transaction_id": self.transaction_id,
                "policy_version": self.policy_version, "assessed_at": utc_iso(self.assessed_at),
                "decision": self.decision.value, "score": self.score,
                "reasons": list(self.reasons), "velocity_events": self.velocity_events,
                "velocity_amount_bdt": bdt_from_minor(self.velocity_amount_poisha),
                "evidence_digest": self.evidence_digest,
                "authorizes_payment_or_settlement": False}


class RiskEvaluator:
    """Thread-safe advisory risk recorder with deterministic merchant-isolated windows."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._events: dict[str, list[RiskInput]] = defaultdict(list)
        self._assessments: dict[tuple[str, str], RiskAssessment] = {}
        self._fingerprints: dict[tuple[str, str], str] = {}

    @staticmethod
    def _fingerprint(item: RiskInput) -> str:
        return evidence_hash({
            "merchant_id": item.merchant_id, "transaction_id": item.transaction_id,
            "order_ref": item.order_ref, "amount": item.amount_poisha,
            "created_at": utc_iso(item.created_at), "currency": item.currency,
            "verified": item.gateway_verified, "risk": item.gateway_risk_level,
            "policy_version": item.merchant_policy_version,
            "invoice": item.invoice_authorized, "chargebacks": item.prior_chargebacks,
            "changes": item.change_count,
        })

    def evaluate(self, item: RiskInput, policy: RiskPolicy, *, now: datetime,
                 record: bool = False) -> RiskAssessment:
        if not isinstance(item, RiskInput) or not isinstance(policy, RiskPolicy):
            raise EvidenceError("Expected typed risk input and policy")
        now = timestamp(now)
        if item.merchant_id != policy.merchant_id:
            raise PolicyError("Risk policy belongs to another merchant")
        if item.merchant_policy_version != policy.version:
            raise PolicyError("Risk policy version mismatch")
        if timestamp(item.created_at) > now:
            raise EvidenceError("Cannot assess future transaction")
        key = item.merchant_id, item.transaction_id
        fingerprint = self._fingerprint(item)
        with self._lock:
            if key in self._assessments:
                if self._fingerprints[key] != fingerprint:
                    raise ConflictError("Transaction risk evidence changed after assessment")
                return self._assessments[key]
            floor = now - timedelta(seconds=policy.velocity_window_seconds)
            history = [e for e in self._events[item.merchant_id]
                       if floor <= timestamp(e.created_at) <= now]
            events = len(history) + 1
            amount = sum(e.amount_poisha for e in history) + item.amount_poisha
            duplicate_order = any(e.order_ref == item.order_ref
                                  and e.transaction_id != item.transaction_id for e in history)
            reasons = []
            score = 0
            if item.amount_poisha > policy.maximum_per_order_poisha:
                reasons.append("large_amount")
                score += policy.amount_points
            if events > policy.maximum_events_per_window:
                reasons.append("high_event_velocity")
                score += policy.velocity_points
            if amount > policy.maximum_window_amount_poisha:
                reasons.append("high_amount_velocity")
                score += policy.velocity_points
            if item.prior_chargebacks:
                reasons.append("previous_disputes")
                score += min(100, item.prior_chargebacks * policy.chargeback_points)
            if item.change_count:
                reasons.append("order_details_changed")
                score += min(100, item.change_count * policy.changed_order_points)
            if not item.invoice_authorized:
                reasons.append("merchant_invoice_unverified")
                score += policy.missing_invoice_points
            if duplicate_order:
                reasons.append("reused_order_reference")
            if not item.gateway_verified or item.gateway_risk_level is None:
                reasons.append("provider_verification_missing")
            if item.gateway_risk_level is not None and item.gateway_risk_level > 0:
                reasons.append("provider_risk_hold")
            score = min(100, score)
            if duplicate_order:
                decision = Decision.REJECT_DUPLICATE
            elif item.gateway_risk_level is not None and item.gateway_risk_level > 0:
                decision = Decision.HOLD_PROVIDER_RISK
            elif not item.gateway_verified or item.gateway_risk_level is None:
                decision = Decision.HOLD_MISSING_EVIDENCE
            elif score >= policy.threshold_review_score:
                decision = Decision.REVIEW
            else:
                decision = Decision.ALLOW_TO_VALIDATE
            result = RiskAssessment(item.merchant_id, item.transaction_id, policy.version,
                                    now, decision, score, tuple(sorted(set(reasons))),
                                    events, amount, fingerprint)
            if record:
                self._events[item.merchant_id].append(item)
                self._assessments[key] = result
                self._fingerprints[key] = fingerprint
            return result

    def count(self, merchant_id: str) -> int:
        reference(merchant_id, field_name="merchant_id")
        with self._lock:
            return len(self._events[merchant_id])

    def history(self, merchant_id: str) -> tuple[RiskAssessment, ...]:
        reference(merchant_id, field_name="merchant_id")
        with self._lock:
            return tuple(value for (mid, _), value in self._assessments.items()
                         if mid == merchant_id)

    def merchant_summary(self, merchant_id: str) -> dict:
        records = self.history(merchant_id)
        return {"merchant_id": merchant_id, "recorded": len(records),
                "hold_count": sum(r.decision != Decision.ALLOW_TO_VALIDATE for r in records),
                "max_score": max((r.score for r in records), default=0),
                "payment_authorization_possible": False}
