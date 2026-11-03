"""Offline gateway-to-bank settlement reconciliation, not financial settlement.

The gateway validation API proves a payment record under the provider contract;
`store_amount` is gateway-reported net, NOT proof that a bank account received
funds. This engine deliberately requires independent bank statement evidence,
uses exact references and BDT minor units, and never auto-fills discrepancies.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import io
from typing import Iterable, Mapping, Sequence

from .primitives import (
    ConflictError, EvidenceError, Finding, PolicyError, bdt_from_minor,
    ensure_unique_references, evidence_hash, minor_from_bdt, nonnegative_minor,
    positive_minor, reference, safe_key, timestamp, utc_iso,
)


class GatewayState(str, Enum):
    VALID = "valid"
    VALIDATED = "validated"
    REVIEW = "risk_review"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    DISPUTED = "disputed"


class SettlementState(str, Enum):
    SETTLED = "settled"
    MISSING_BANK_EVIDENCE = "missing_bank_evidence"
    UNMATCHED_BANK_CREDIT = "unmatched_bank_credit"
    AMOUNT_MISMATCH = "amount_mismatch"
    CURRENCY_MISMATCH = "currency_mismatch"
    RISK_HELD = "risk_held"
    NOT_PAYABLE = "not_payable"
    DUPLICATE_REFERENCE = "duplicate_reference"
    UNBATCHED = "unbatched"
    PENDING_WITHIN_WINDOW = "pending_within_window"
    INVALID_GATEWAY_EVIDENCE = "invalid_gateway_evidence"


@dataclass(frozen=True, slots=True)
class GatewayRecord:
    merchant_id: str
    tran_id: str
    val_id: str
    bank_tran_id: str
    batch_ref: str | None
    gross_poisha: int
    provider_net_poisha: int
    provider_fee_poisha: int
    currency: str
    state: GatewayState
    verified: bool
    paid_at: datetime
    risk_level: int = 0

    def __post_init__(self) -> None:
        for attr in ("merchant_id", "tran_id", "val_id", "bank_tran_id"):
            reference(getattr(self, attr), field_name=attr)
        if self.batch_ref is not None:
            reference(self.batch_ref, field_name="batch_ref")
        positive_minor(self.gross_poisha)
        positive_minor(self.provider_net_poisha)
        nonnegative_minor(self.provider_fee_poisha)
        if self.provider_net_poisha + self.provider_fee_poisha != self.gross_poisha:
            raise EvidenceError("Gateway gross, net and fee do not reconcile")
        if self.currency != "BDT" or not isinstance(self.state, GatewayState):
            raise EvidenceError("Unrecognized gateway currency or state")
        if not isinstance(self.verified, bool):
            raise EvidenceError("Gateway verified flag must be boolean")
        if isinstance(self.risk_level, bool) or not isinstance(self.risk_level, int):
            raise EvidenceError("Risk level must be an integer")
        if not 0 <= self.risk_level <= 10:
            raise EvidenceError("Risk level exceeds allowed range")
        timestamp(self.paid_at)

    def public_dict(self) -> dict:
        return {"tran_id": self.tran_id, "batch_ref": self.batch_ref,
                "gross_bdt": bdt_from_minor(self.gross_poisha),
                "provider_net_bdt": bdt_from_minor(self.provider_net_poisha),
                "provider_fee_bdt": bdt_from_minor(self.provider_fee_poisha),
                "currency": self.currency, "state": self.state.value,
                "provider_validation_verified": self.verified,
                "risk_level": self.risk_level, "paid_at": utc_iso(self.paid_at)}


@dataclass(frozen=True, slots=True)
class BankCredit:
    merchant_id: str
    statement_ref: str
    batch_ref: str
    amount_poisha: int
    currency: str
    posted_at: datetime
    bank_statement_verified: bool = False

    def __post_init__(self) -> None:
        reference(self.merchant_id, field_name="merchant_id")
        reference(self.statement_ref, field_name="statement_ref")
        reference(self.batch_ref, field_name="batch_ref")
        positive_minor(self.amount_poisha)
        if self.currency != "BDT":
            raise EvidenceError("Bank credit must be BDT")
        timestamp(self.posted_at)
        if not isinstance(self.bank_statement_verified, bool):
            raise EvidenceError("Bank evidence verified flag must be boolean")

    def public_dict(self) -> dict:
        return {"statement_ref": self.statement_ref, "batch_ref": self.batch_ref,
                "amount_bdt": bdt_from_minor(self.amount_poisha),
                "currency": self.currency, "posted_at": utc_iso(self.posted_at),
                "bank_statement_verified": self.bank_statement_verified}


@dataclass(frozen=True, slots=True)
class BatchFinding:
    batch_ref: str
    merchant_id: str
    state: SettlementState
    provider_net_poisha: int
    bank_credit_poisha: int
    transaction_count: int
    explanation: str
    bank_statement_verified: bool = False
    provider_verification_complete: bool = False

    def __post_init__(self) -> None:
        reference(self.batch_ref, field_name="batch_ref")
        reference(self.merchant_id, field_name="merchant_id")
        nonnegative_minor(self.provider_net_poisha)
        nonnegative_minor(self.bank_credit_poisha)
        if not isinstance(self.state, SettlementState):
            raise EvidenceError("Unrecognized reconciliation result state")
        if self.transaction_count < 0:
            raise EvidenceError("Invalid transaction count")
        safe_key(self.explanation, field_name="explanation")

    @property
    def difference_poisha(self) -> int:
        return self.bank_credit_poisha - self.provider_net_poisha

    def as_dict(self) -> dict:
        return {"merchant_id": self.merchant_id, "batch_ref": self.batch_ref,
                "state": self.state.value, "transaction_count": self.transaction_count,
                "provider_reported_net_bdt": bdt_from_minor(self.provider_net_poisha),
                "bank_credit_bdt": bdt_from_minor(self.bank_credit_poisha),
                "difference_bdt": bdt_from_minor(self.difference_poisha),
                "explanation": self.explanation,
                "bank_statement_verified": self.bank_statement_verified,
                "provider_verification_complete": self.provider_verification_complete}


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    merchant_id: str
    as_of: datetime
    gateway_count: int
    bank_count: int
    findings: tuple[BatchFinding, ...]
    provider_gross_poisha: int
    provider_fee_poisha: int
    provider_net_poisha: int
    bank_credit_poisha: int
    evidence_digest: str

    @property
    def reconciled(self) -> bool:
        return bool(self.findings) and all(x.state == SettlementState.SETTLED for x in self.findings)

    @property
    def missing_batches(self) -> int:
        return sum(x.state == SettlementState.MISSING_BANK_EVIDENCE for x in self.findings)

    @property
    def mismatch_batches(self) -> int:
        return sum(x.state == SettlementState.AMOUNT_MISMATCH for x in self.findings)

    def as_dict(self) -> dict:
        return {"merchant_id": self.merchant_id, "as_of": utc_iso(self.as_of),
                "gateway_count": self.gateway_count, "bank_count": self.bank_count,
                "reconciled": self.reconciled,
                "provider_gross_bdt": bdt_from_minor(self.provider_gross_poisha),
                "provider_fee_bdt": bdt_from_minor(self.provider_fee_poisha),
                "provider_reported_net_bdt": bdt_from_minor(self.provider_net_poisha),
                "bank_credit_bdt": bdt_from_minor(self.bank_credit_poisha),
                "findings": [f.as_dict() for f in self.findings],
                "evidence_digest": self.evidence_digest,
                "bank_settlement_executed_by_software": False}


class Reconciler:
    """Exact batch/reference matching with conservative fail-closed decisions."""

    def __init__(self, *, settlement_window_days: int = 2,
                 require_bank_verification: bool = True) -> None:
        if isinstance(settlement_window_days, bool) or not 0 <= settlement_window_days <= 30:
            raise EvidenceError("Settlement window must be between 0 and 30 days")
        self.window_days = settlement_window_days
        if require_bank_verification is not True:
            raise PolicyError("Bank statement verification cannot be bypassed")
        self.require_bank_verification = True

    @staticmethod
    def _duplicate_identity(records: Sequence[GatewayRecord]) -> set[str]:
        seen_ids, seen_val, seen_bank = set(), set(), set()
        duplicates = set()
        for row in records:
            if row.tran_id in seen_ids or row.val_id in seen_val or row.bank_tran_id in seen_bank:
                duplicates.add(row.batch_ref or row.tran_id)
            seen_ids.add(row.tran_id)
            seen_val.add(row.val_id)
            seen_bank.add(row.bank_tran_id)
        return duplicates

    def reconcile(self, *, merchant_id: str, gateway: Sequence[GatewayRecord],
                  bank: Sequence[BankCredit], as_of: datetime) -> ReconciliationReport:
        reference(merchant_id, field_name="merchant_id")
        as_of = timestamp(as_of)
        if len(gateway) > 10_000 or len(bank) > 10_000:
            raise EvidenceError("Reconciliation input exceeds batch limit")
        if any(not isinstance(x, GatewayRecord) for x in gateway):
            raise EvidenceError("Gateway evidence type mismatch")
        if any(not isinstance(x, BankCredit) for x in bank):
            raise EvidenceError("Bank evidence type mismatch")
        if any(r.merchant_id != merchant_id for r in gateway) or any(b.merchant_id != merchant_id for b in bank):
            raise PolicyError("Reconciliation cannot cross merchant boundaries")
        if any(timestamp(row.paid_at) > as_of for row in gateway):
            raise EvidenceError("Gateway timestamp is in the future")
        if any(timestamp(row.posted_at) > as_of for row in bank):
            raise EvidenceError("Bank timestamp is in the future")
        duplicate_batches = self._duplicate_identity(gateway)
        bank_seen: set[str] = set()
        for row in bank:
            if row.statement_ref in bank_seen:
                duplicate_batches.add(row.batch_ref)
            bank_seen.add(row.statement_ref)
        gateway_groups: dict[str, list[GatewayRecord]] = {}
        bank_groups: dict[str, list[BankCredit]] = {}
        findings: list[BatchFinding] = []
        for row in gateway:
            if row.batch_ref is None:
                findings.append(BatchFinding(row.tran_id, merchant_id, SettlementState.UNBATCHED,
                                             row.provider_net_poisha, 0, 1, "batch_reference_missing"))
            else:
                gateway_groups.setdefault(row.batch_ref, []).append(row)
        for row in bank:
            bank_groups.setdefault(row.batch_ref, []).append(row)
        for batch_ref in sorted(gateway_groups.keys() | bank_groups.keys()):
            payments = gateway_groups.get(batch_ref, [])
            credits = bank_groups.get(batch_ref, [])
            net = sum(x.provider_net_poisha for x in payments)
            credited = sum(x.amount_poisha for x in credits)
            gateway_valid = bool(payments) and all(x.verified for x in payments)
            bank_valid = bool(credits) and all(x.bank_statement_verified for x in credits)
            context = (batch_ref, merchant_id)
            def record(state: SettlementState, explanation: str) -> None:
                findings.append(BatchFinding(*context, state, net, credited,
                                             len(payments), explanation, bank_valid, gateway_valid))
            if batch_ref in duplicate_batches or len(credits) > 1:
                record(SettlementState.DUPLICATE_REFERENCE, "duplicate_bank_or_gateway_reference")
                continue
            if not payments:
                record(SettlementState.UNMATCHED_BANK_CREDIT, "bank_credit_without_gateway_batch")
                continue
            if not gateway_valid:
                record(SettlementState.INVALID_GATEWAY_EVIDENCE, "provider_verification_missing")
                continue
            if any(x.state in (GatewayState.REVIEW, GatewayState.DISPUTED) or x.risk_level != 0
                   for x in payments):
                record(SettlementState.RISK_HELD, "gateway_risk_or_dispute_hold")
                continue
            if any(x.state not in (GatewayState.VALID, GatewayState.VALIDATED) for x in payments):
                record(SettlementState.NOT_PAYABLE, "gateway_state_not_authorized_for_settlement")
                continue
            if not credits:
                age = max((as_of - timestamp(x.paid_at)).days for x in payments)
                if age <= self.window_days:
                    record(SettlementState.PENDING_WITHIN_WINDOW, "bank_settlement_pending_window")
                else:
                    record(SettlementState.MISSING_BANK_EVIDENCE, "bank_statement_missing_after_window")
                continue
            if self.require_bank_verification and not bank_valid:
                record(SettlementState.MISSING_BANK_EVIDENCE, "bank_document_unverified")
                continue
            if net != credited:
                record(SettlementState.AMOUNT_MISMATCH, "gateway_net_does_not_equal_bank_credit")
                continue
            if timestamp(credits[0].posted_at) < min(timestamp(p.paid_at) for p in payments):
                record(SettlementState.INVALID_GATEWAY_EVIDENCE, "bank_posted_before_gateway_payment")
                continue
            record(SettlementState.SETTLED, "matching_independent_bank_credit")
        findings.sort(key=lambda x: (x.batch_ref, x.state.value))
        digest = evidence_hash({
            "merchant_id": merchant_id, "as_of": utc_iso(as_of),
            "gateway": [x.public_dict() for x in sorted(gateway, key=lambda x: x.tran_id)],
            "bank": [x.public_dict() for x in sorted(bank, key=lambda x: x.statement_ref)],
            "states": [x.as_dict() for x in findings],
        })
        return ReconciliationReport(merchant_id, as_of, len(gateway), len(bank),
                                    tuple(findings), sum(x.gross_poisha for x in gateway),
                                    sum(x.provider_fee_poisha for x in gateway),
                                    sum(x.provider_net_poisha for x in gateway),
                                    sum(x.amount_poisha for x in bank), digest)


class StatementImporter:
    """Strict CSV import of intentionally minimal settlement metadata.

    Avoid storing card numbers, customer names, email addresses, national IDs,
    or any raw full gateway response in bank reconciliation artifacts.
    """

    GATEWAY_COLUMNS = frozenset({
        "merchant_id", "tran_id", "val_id", "bank_tran_id", "batch_ref",
        "gross_bdt", "net_bdt", "fee_bdt", "currency", "state", "verified",
        "paid_at", "risk_level",
    })
    BANK_COLUMNS = frozenset({
        "merchant_id", "statement_ref", "batch_ref", "amount_bdt", "currency",
        "posted_at", "statement_verified",
    })

    def __init__(self, *, max_rows: int = 10_000, max_bytes: int = 2_000_000) -> None:
        if not 1 <= max_rows <= 50_000 or not 256 <= max_bytes <= 10_000_000:
            raise EvidenceError("Invalid import limits")
        self.max_rows, self.max_bytes = max_rows, max_bytes

    def _parse_csv(self, raw: str, columns: frozenset[str]) -> list[dict[str, str]]:
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > self.max_bytes:
            raise EvidenceError("Statement file exceeds size limit")
        if "\x00" in raw:
            raise EvidenceError("Malformed statement")
        reader = csv.DictReader(io.StringIO(raw, newline=""))
        headers = reader.fieldnames
        if not headers or len(headers) != len(set(headers)) or set(headers) != columns:
            raise EvidenceError("Statement headers must match approved exact schema")
        rows = []
        for item in reader:
            if len(rows) >= self.max_rows:
                raise EvidenceError("Statement row count exceeds limit")
            if None in item or any(v is None for v in item.values()):
                raise EvidenceError("Statement row has missing or extra fields")
            rows.append(item)
        return rows

    @staticmethod
    def _bool(value: str) -> bool:
        if value not in ("true", "false"):
            raise EvidenceError("Expected true or false")
        return value == "true"

    def gateway_rows(self, raw: str) -> tuple[GatewayRecord, ...]:
        from .primitives import parse_utc
        items = []
        for row in self._parse_csv(raw, self.GATEWAY_COLUMNS):
            try:
                state = GatewayState(row["state"])
                risk = int(row["risk_level"])
            except (ValueError, TypeError) as exc:
                raise EvidenceError("Unsupported gateway state or risk") from exc
            items.append(GatewayRecord(
                merchant_id=row["merchant_id"], tran_id=row["tran_id"],
                val_id=row["val_id"], bank_tran_id=row["bank_tran_id"],
                batch_ref=row["batch_ref"] or None,
                gross_poisha=minor_from_bdt(row["gross_bdt"]),
                provider_net_poisha=minor_from_bdt(row["net_bdt"]),
                provider_fee_poisha=minor_from_bdt(row["fee_bdt"], allow_zero=True),
                currency=row["currency"], state=state, verified=self._bool(row["verified"]),
                paid_at=parse_utc(row["paid_at"]), risk_level=risk))
        return tuple(items)

    def bank_rows(self, raw: str) -> tuple[BankCredit, ...]:
        from .primitives import parse_utc
        return tuple(BankCredit(
            merchant_id=row["merchant_id"], statement_ref=row["statement_ref"],
            batch_ref=row["batch_ref"], amount_poisha=minor_from_bdt(row["amount_bdt"]),
            currency=row["currency"], posted_at=parse_utc(row["posted_at"]),
            bank_statement_verified=self._bool(row["statement_verified"]))
            for row in self._parse_csv(raw, self.BANK_COLUMNS))

    def render_gateway_csv(self, records: Sequence[GatewayRecord]) -> str:
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=sorted(self.GATEWAY_COLUMNS))
        writer.writeheader()
        for entry in records:
            data = {"merchant_id": entry.merchant_id, "tran_id": entry.tran_id,
                    "val_id": entry.val_id, "bank_tran_id": entry.bank_tran_id,
                    "batch_ref": entry.batch_ref or "", "gross_bdt": bdt_from_minor(entry.gross_poisha),
                    "net_bdt": bdt_from_minor(entry.provider_net_poisha),
                    "fee_bdt": bdt_from_minor(entry.provider_fee_poisha),
                    "currency": entry.currency, "state": entry.state.value,
                    "verified": str(entry.verified).lower(), "paid_at": utc_iso(entry.paid_at),
                    "risk_level": str(entry.risk_level)}
            writer.writerow(data)
        return buffer.getvalue()

    def render_bank_csv(self, records: Sequence[BankCredit]) -> str:
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=sorted(self.BANK_COLUMNS))
        writer.writeheader()
        for item in records:
            writer.writerow({"merchant_id": item.merchant_id,
                             "statement_ref": item.statement_ref, "batch_ref": item.batch_ref,
                             "amount_bdt": bdt_from_minor(item.amount_poisha),
                             "currency": item.currency, "posted_at": utc_iso(item.posted_at),
                             "statement_verified": str(item.bank_statement_verified).lower()})
        return buffer.getvalue()
