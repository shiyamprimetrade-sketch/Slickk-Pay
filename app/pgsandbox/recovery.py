"""Crash and timeout recovery of synthetic cash requests, without bank calls.

Reconciliation is bounded, repeatable, and intentionally conservative. Unknown
external outcomes never authorize a new synthetic credit. Expired cash holds
may be released only through the same reversible journal transaction.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from .schema import requests, accounts, cash_inventory, outbox, journals
from .cash import SandboxCashDesk
from .posting import LedgerService
from .store import SandboxStore, utc_now
from .errors import StateError, InvalidValue, ReportMismatch


@dataclass(frozen=True)
class RecoveryFinding:
    reference: str
    kind: str
    action: str
    status: str
    detail: str
    simulation: bool = True


@dataclass(frozen=True)
class RecoverySummary:
    scanned: int
    expired_released: int
    needs_review: int
    skipped: int
    failures: tuple[RecoveryFinding, ...]
    simulation: bool = True


class CashRecovery:
    def __init__(self, cash: SandboxCashDesk):
        self.cash = cash
        self.store = cash.ledger.store

    def expired(self, *, limit: int = 100, now: datetime | None = None) -> tuple[str, ...]:
        if not 1 <= limit <= 1000:
            raise InvalidValue("Invalid recovery batch")
        at = now or datetime.now(timezone.utc)
        if at.tzinfo is None:
            raise InvalidValue("Naive recovery date")
        cutoff = at.astimezone(timezone.utc).isoformat(timespec="microseconds")
        with self.store.engine.connect() as db:
            rows = db.execute(select(requests.c.request_id)
                              .where(requests.c.state.in_(["awaiting", "reserved", "customer_confirmed"]))
                              .where(requests.c.expires_at <= cutoff)
                              .order_by(requests.c.expires_at).limit(limit)).scalars().all()
        return tuple(rows)

    def sweep(self, *, limit: int = 100) -> RecoverySummary:
        identifiers = self.expired(limit=limit)
        failures: list[RecoveryFinding] = []
        complete = 0
        skipped = 0
        for request_id in identifiers:
            try:
                row = self.cash.expire(request_id=request_id)
                if row.state == "expired":
                    complete += 1
                else:
                    skipped += 1
            except (StateError, ReportMismatch) as exc:
                failures.append(RecoveryFinding(request_id, "cash_timeout", "manual_review",
                                                "blocked", type(exc).__name__))
            except Exception as exc:
                # Unexpected DB/storage errors are not erased: the operator must
                # inspect the durable record before any compensating posting.
                failures.append(RecoveryFinding(request_id, "cash_timeout", "manual_review",
                                                "failed", type(exc).__name__))
        return RecoverySummary(len(identifiers), complete, len(failures), skipped, tuple(failures))

    def stalled_cashouts(self, *, older_than_minutes: int = 30, limit: int = 100) -> tuple[RecoveryFinding, ...]:
        if not 1 <= older_than_minutes <= 7*24*60:
            raise InvalidValue("Invalid stalled threshold")
        if not 1 <= limit <= 1000:
            raise InvalidValue("Invalid bounded query")
        cutoff = (datetime.now(timezone.utc)-timedelta(minutes=older_than_minutes)).isoformat(timespec="microseconds")
        with self.store.engine.connect() as db:
            rows = db.execute(select(requests).where(requests.c.kind == "cash_out")
                              .where(requests.c.state.in_(["reserved", "customer_confirmed"]))
                              .where(requests.c.created_at < cutoff).limit(limit)).mappings().all()
        return tuple(RecoveryFinding(r["request_id"], "cash_out", "check_handover",
                                     r["state"], "Operator must verify physical cash claim")
                     for r in rows)


class DiagnosticScans:
    """Read-only database checks for reconciliation after interrupted test runs."""

    def __init__(self, store: SandboxStore):
        self.store = store

    def unfinished_outbox(self, *, limit: int = 100) -> list[RecoveryFinding]:
        if not 1 <= limit <= 1000:
            raise InvalidValue("Invalid output limit")
        with self.store.engine.connect() as db:
            rows = db.execute(select(outbox.c.message_id, outbox.c.state)
                              .where(outbox.c.state.in_(["ready", "leased", "dead"]))
                              .limit(limit)).all()
        return [RecoveryFinding(m, "outbox", "review_delivery", state,
                                "At-least-once retry; receiver must deduplicate") for m,state in rows]

    def abandoned_escrow(self, *, limit: int = 100) -> list[RecoveryFinding]:
        if not 1 <= limit <= 1000:
            raise InvalidValue("Invalid output limit")
        with self.store.engine.connect() as db:
            rows = db.execute(select(requests.c.request_id, requests.c.state,
                                     accounts.c.balance)
                              .join(accounts, requests.c.escrow_account == accounts.c.account_id)
                              .where(requests.c.kind == "cash_out")
                              .where(requests.c.state.in_(["completed", "cancelled", "expired"]))
                              .where(accounts.c.balance != 0).limit(limit)).all()
        return [RecoveryFinding(req_id, "escrow_balance", "manual_reconciliation", state,
                                f"Fictional escrow remains nonzero ({balance} poisha)")
                for req_id,state,balance in rows]

    def journal_count(self) -> int:
        with self.store.engine.connect() as db:
            return int(db.execute(select(func.count()).select_from(journals)).scalar_one())
