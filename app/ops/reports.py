"""Evidence summary and readiness reports for merchant-operations dry runs.

A report is a reproducible digest of offline inputs. It is not a Bangladesh
Bank filing, an attestation of regulatory permission, or proof of actual bank
settlement. Exported summaries omit full customer and payment identifiers.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable, Mapping, Sequence

from .primitives import (
    EvidenceError, bdt_from_minor, evidence_hash, reference, timestamp, utc_iso,
)
from .settlement import ReconciliationReport, SettlementState
from .risk import RiskAssessment, Decision
from .journal import ShadowJournal
from .disputes import DisputeDesk
from .outbox import Outbox


class GateStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    PENDING = "pending"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class VerificationGate:
    gate_id: str
    status: GateStatus
    evidence_ref_digest: str | None
    reviewer_ref: str | None

    def __post_init__(self) -> None:
        reference(self.gate_id, field_name="gate_id")
        if not isinstance(self.status, GateStatus):
            raise EvidenceError("Invalid evidence gate status")
        if self.status == GateStatus.PASSED and not self.evidence_ref_digest:
            raise EvidenceError("Passed gate requires evidence digest")
        if self.evidence_ref_digest is not None:
            if len(self.evidence_ref_digest) != 64:
                raise EvidenceError("Gate evidence must use SHA-256")
            if any(c not in "0123456789abcdef" for c in self.evidence_ref_digest):
                raise EvidenceError("Invalid evidence digest")
        if self.reviewer_ref is not None:
            reference(self.reviewer_ref, field_name="reviewer_ref")

    def summary(self) -> dict:
        return {"gate_id": self.gate_id, "status": self.status.value,
                "evidence_digest": self.evidence_ref_digest,
                "reviewer_ref": self.reviewer_ref}


@dataclass(frozen=True, slots=True)
class ReadinessAssessment:
    merchant_id: str
    created_at: datetime
    gates: tuple[VerificationGate, ...]
    evidence_digest: str
    all_claimed_gates_passed: bool

    def as_dict(self) -> dict:
        return {"merchant_id": self.merchant_id, "created_at": utc_iso(self.created_at),
                "gates": [gate.summary() for gate in self.gates],
                "production_ready": False,
                "all_claimed_gates_passed": self.all_claimed_gates_passed,
                "evidence_digest": self.evidence_digest,
                "financial_activity_authorized_by_this_report": False}


class ReadinessChecklist:
    """High-level evidence gating; cannot self-certify legal authorisation."""

    REQUIRED = frozenset({
        "credential_rotation", "licensed_entity_review", "gateway_merchant_onboarding",
        "staging_deployment", "isolated_db_migration", "sandbox_e2e_payment",
        "ipn_replay_tests", "settlement_statement_review", "security_review",
        "dispute_refund_runbook", "incident_response_runbook", "data_privacy_review",
    })

    def assess(self, *, merchant_id: str, now: datetime,
               gates: Sequence[VerificationGate]) -> ReadinessAssessment:
        reference(merchant_id, field_name="merchant_id")
        now = timestamp(now)
        if len(gates) > 50 or any(not isinstance(g, VerificationGate) for g in gates):
            raise EvidenceError("Invalid readiness gate collection")
        by_id = {g.gate_id: g for g in gates}
        if len(by_id) != len(gates):
            raise EvidenceError("Duplicate readiness gate")
        supplied = tuple(sorted(gates, key=lambda x: x.gate_id))
        complete = all(by_id.get(k) is not None and by_id[k].status == GateStatus.PASSED
                       for k in self.REQUIRED)
        digest = evidence_hash({"merchant": merchant_id, "at": utc_iso(now),
                                "gates": [g.summary() for g in supplied]})
        return ReadinessAssessment(merchant_id, now, supplied, digest, complete)

    def missing(self, gates: Sequence[VerificationGate]) -> tuple[str, ...]:
        by_id = {g.gate_id: g for g in gates}
        return tuple(sorted(k for k in self.REQUIRED
                            if k not in by_id or by_id[k].status != GateStatus.PASSED))


@dataclass(frozen=True, slots=True)
class MerchantSnapshot:
    merchant_id: str
    created_at: datetime
    settlement_state_counts: Mapping[str, int]
    provider_gross_poisha: int
    provider_reported_net_poisha: int
    bank_evidence_poisha: int
    held_risk_count: int
    dispute_open_count: int
    audit_root: str
    evidence_digest: str

    def public_dict(self) -> dict:
        return {"merchant_id": self.merchant_id, "created_at": utc_iso(self.created_at),
                "settlement_state_counts": dict(self.settlement_state_counts),
                "provider_gross_bdt": bdt_from_minor(self.provider_gross_poisha),
                "provider_reported_net_bdt": bdt_from_minor(self.provider_reported_net_poisha),
                "bank_evidence_bdt": bdt_from_minor(self.bank_evidence_poisha),
                "held_risk_count": self.held_risk_count,
                "dispute_open_count": self.dispute_open_count,
                "audit_root": self.audit_root, "evidence_digest": self.evidence_digest,
                "regulatory_report_submitted": False,
                "bank_settlement_authorized": False}


class ReportingEngine:
    """Combine audited metadata without creating a second settlement authority."""

    def create_snapshot(self, *, merchant_id: str, at: datetime,
                        reconciliation: ReconciliationReport,
                        risk: Sequence[RiskAssessment],
                        journal: ShadowJournal,
                        disputes: DisputeDesk) -> MerchantSnapshot:
        reference(merchant_id, field_name="merchant_id")
        at = timestamp(at)
        if not isinstance(reconciliation, ReconciliationReport):
            raise EvidenceError("Expected ReconciliationReport")
        if reconciliation.merchant_id != merchant_id:
            raise EvidenceError("Reconciliation belongs to another merchant")
        if any(x.merchant_id != merchant_id for x in risk):
            raise EvidenceError("Risk evidence belongs to another merchant")
        if not isinstance(journal, ShadowJournal) or not journal.verify_chain():
            raise EvidenceError("Journal chain is not verified")
        if not isinstance(disputes, DisputeDesk):
            raise EvidenceError("Invalid dispute registry")
        states = {x.value: 0 for x in SettlementState}
        for finding in reconciliation.findings:
            states[finding.state.value] += 1
        open_cases = disputes.dashboard(merchant_id=merchant_id, now=at)["open_count"]
        risk_holds = sum(x.decision != Decision.ALLOW_TO_VALIDATE for x in risk)
        root = journal.chain_root()
        digest = evidence_hash({
            "merchant": merchant_id, "at": utc_iso(at), "states": states,
            "gateway_digest": reconciliation.evidence_digest,
            "risk_digests": sorted(x.evidence_digest for x in risk),
            "journal_root": root, "dispute_open_count": open_cases,
        })
        return MerchantSnapshot(merchant_id, at, states,
                                reconciliation.provider_gross_poisha,
                                reconciliation.provider_net_poisha,
                                reconciliation.bank_credit_poisha,
                                risk_holds, open_cases, root, digest)

    @staticmethod
    def compare_snapshots(earlier: MerchantSnapshot, later: MerchantSnapshot) -> dict:
        if earlier.merchant_id != later.merchant_id:
            raise EvidenceError("Cannot compare different merchants")
        if timestamp(later.created_at) < timestamp(earlier.created_at):
            raise EvidenceError("Snapshot time order invalid")
        return {"merchant_id": earlier.merchant_id,
                "change_provider_gross_bdt": bdt_from_minor(later.provider_gross_poisha - earlier.provider_gross_poisha),
                "change_gateway_net_bdt": bdt_from_minor(later.provider_reported_net_poisha - earlier.provider_reported_net_poisha),
                "change_bank_evidence_bdt": bdt_from_minor(later.bank_evidence_poisha - earlier.bank_evidence_poisha),
                "change_open_disputes": later.dispute_open_count - earlier.dispute_open_count,
                "earlier_digest": earlier.evidence_digest, "later_digest": later.evidence_digest}
