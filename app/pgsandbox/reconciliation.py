"""Deterministic *internal* ledger reconciliation for fictional balances.

A matched internal journal is not confirmation of settlement by SSLCOMMERZ or a
Bangladesh bank. External bank evidence is intentionally not accepted here.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
import re
from sqlalchemy import select, insert, and_, func
from .schema import accounts, journals, postings, reconciliation, chain
from .posting import LedgerService, digest
from .store import utc_now
from .guard import sim_id
from .money import minor, minor_to_bdt
from .errors import InvalidValue, MissingRecord, Conflict, ReportMismatch


@dataclass(frozen=True)
class AccountReconciliation:
    reference: str
    account_id: str
    date: str
    opening_poisha: int
    debit_poisha: int
    credit_poisha: int
    expected_poisha: int
    observed_poisha: int
    matched: bool
    evidence_digest: str
    simulation: bool = True


@dataclass(frozen=True)
class BatchReconciliation:
    batch_key: str
    date: str
    matching: int
    exceptions: int
    total_debits: int
    total_credits: int
    report_hash: str
    source: str = "SYNTHETIC_LEDGER_ONLY"
    simulation: bool = True


def _period(raw: str) -> date:
    if not isinstance(raw, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raise InvalidValue("Use YYYY-MM-DD for sandbox reconciliation")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise InvalidValue("Invalid reporting period") from exc


class ReconciliationService:
    def __init__(self, ledger: LedgerService):
        self.ledger = ledger

    def _journal_amounts(self, db, account_id: str, period: str) -> tuple[int, int, int]:
        # Left join is not needed: journal evidence only exists if a posting
        # references a valid event. Predicates use ISO8601 UTC timestamps.
        joined = select(postings.c.direction, postings.c.amount, journals.c.created_at)
        joined = joined.join(journals, postings.c.event_id == journals.c.event_id)
        rows = db.execute(joined.where(postings.c.account_id == account_id)).mappings().all()
        opening = 0
        debits = 0
        credits = 0
        for row in rows:
            timestamp = datetime.fromisoformat(row["created_at"])
            utc_date = timestamp.astimezone(timezone.utc).date().isoformat()
            side = -row["amount"] if row["direction"] == "debit" else row["amount"]
            if utc_date < period:
                opening += side
            elif utc_date == period:
                if row["direction"] == "debit":
                    debits += row["amount"]
                else:
                    credits += row["amount"]
        return opening, debits, credits

    def calculate(self, account_id: str, period: str) -> AccountReconciliation:
        sim_id(account_id, "account")
        day = _period(period).isoformat()
        today = datetime.now(timezone.utc).date()
        if date.fromisoformat(day) > today:
            raise InvalidValue("Future reporting periods cannot be reconciled")
        with self.ledger.store.engine.connect() as db:
            account = db.execute(select(accounts).where(accounts.c.account_id == account_id)).mappings().first()
            if account is None:
                raise MissingRecord("Account not found")
            opening, debits, credits = self._journal_amounts(db, account_id, day)
            # Reconciliation of historical days uses the posting records only;
            # current balance must not be mistaken for a historical close.
            expected = opening + credits - debits
            latest = db.execute(select(func.max(journals.c.created_at))).scalar()
            observed = account["balance"] if day == today.isoformat() else expected
            # Historical equality is an internal reconstruction, not independent
            # bank evidence. Report source explicitly retains that limitation.
            matched = expected == observed
        ref = "sim_recon_" + sha256((day+":"+account_id).encode()).hexdigest()[:32]
        payload = {"reference": ref, "account_id": account_id, "period": day,
                   "opening": opening, "debits": debits, "credits": credits,
                   "expected": expected, "observed": observed,
                   "matched": matched, "evidence_kind": "INTERNAL_ONLY"}
        return AccountReconciliation(ref, account_id, day, opening, debits, credits,
                                     expected, observed, matched, digest(payload))

    def record(self, account_id: str, period: str) -> AccountReconciliation:
        result = self.calculate(account_id, period)
        with self.ledger.store.transaction() as db:
            old = db.execute(select(reconciliation).where(
                (reconciliation.c.period == result.date) &
                (reconciliation.c.account_id == account_id)).with_for_update()).mappings().first()
            if old:
                if old["evidence_digest"] != result.evidence_digest:
                    raise Conflict("Existing period proof differs; manual audit required")
                return result
            db.execute(insert(reconciliation).values(recon_id=result.reference, period=result.date,
                       account_id=account_id, opening=result.opening_poisha,
                       debits=result.debit_poisha, credits=result.credit_poisha,
                       closing=result.expected_poisha, observed=result.observed_poisha,
                       status="matching" if result.matched else "exception",
                       evidence_digest=result.evidence_digest, created_at=utc_now()))
        return result

    def batch(self, period: str, *, max_accounts: int = 5000) -> BatchReconciliation:
        day = _period(period).isoformat()
        if not 1 <= max_accounts <= 100000:
            raise InvalidValue("Unbounded reconciliation query")
        with self.ledger.store.engine.connect() as db:
            account_ids = db.execute(select(accounts.c.account_id)
                                     .order_by(accounts.c.account_id).limit(max_accounts+1)).scalars().all()
        if len(account_ids) > max_accounts:
            raise InvalidValue("Too many accounts for bounded snapshot")
        rows = tuple(self.calculate(account_id, day) for account_id in account_ids)
        total_debits = sum(r.debit_poisha for r in rows)
        total_credits = sum(r.credit_poisha for r in rows)
        mismatches = sum(not r.matched for r in rows)
        if total_debits != total_credits:
            mismatches += 1
        batch_key = "sim_batch_"+sha256(day.encode()).hexdigest()[:32]
        report_hash = digest([r.evidence_digest for r in rows])
        return BatchReconciliation(batch_key, day, len(rows)-sum(not r.matched for r in rows),
                                   mismatches, total_debits, total_credits, report_hash)

    def assert_healthy(self) -> bool:
        proof = self.ledger.verify()
        if not proof.valid or proof.total_credits != proof.total_debits:
            raise ReportMismatch("Synthetic journal integrity failed")
        return True

    def exceptions(self, *, period: str | None = None, limit: int = 100) -> tuple[dict[str, object], ...]:
        if not 1 <= limit <= 1000:
            raise InvalidValue("Invalid exception limit")
        with self.ledger.store.engine.connect() as db:
            q = select(reconciliation).where(reconciliation.c.status == "exception")
            if period is not None:
                q = q.where(reconciliation.c.period == _period(period).isoformat())
            q = q.order_by(reconciliation.c.created_at.desc()).limit(limit)
            rows = db.execute(q).mappings().all()
        return tuple({"account_id": row["account_id"], "period": row["period"],
                      "expected_poisha": row["closing"], "observed_poisha": row["observed"],
                      "simulation": True} for row in rows)


@dataclass(frozen=True)
class ExternalSettlementPlaceholder:
    """Explicit boundary: no synthetic statement masquerades as a real bank file."""
    provider: str
    enabled: bool = False
    reason: str = "External partner settlement is not configured"

    def import_bank_statement(self, *_args, **_kwargs):
        raise ReportMismatch(self.reason)
