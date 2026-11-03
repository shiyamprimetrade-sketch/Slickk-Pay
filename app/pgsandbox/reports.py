"""Bounded synthetic financial and agent reporting; no real customer statistics."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from sqlalchemy import select, func, and_
from .schema import (accounts, journals, postings, requests, cash_inventory,
                     money_events, outbox, security_events, cases)
from .store import SandboxStore
from .guard import sim_id
from .money import minor_to_bdt
from .errors import InvalidValue, MissingRecord


@dataclass(frozen=True)
class LedgerMetrics:
    account_count: int
    journal_count: int
    journal_line_count: int
    gross_debit_poisha: int
    gross_credit_poisha: int
    frozen_account_count: int
    simulation: bool = True

    def public(self) -> dict[str, str | int | bool]:
        return {"accounts": self.account_count, "journal_events": self.journal_count,
                "postings": self.journal_line_count,
                "gross_debits_bdt": minor_to_bdt(self.gross_debit_poisha),
                "gross_credits_bdt": minor_to_bdt(self.gross_credit_poisha),
                "frozen_accounts": self.frozen_account_count,
                "balanced": self.gross_debit_poisha == self.gross_credit_poisha,
                "simulation": True}


@dataclass(frozen=True)
class AgentMetrics:
    agent_float_account: str
    electronic_float_poisha: int
    physical_cash_assertion_poisha: int
    commission_poisha: int
    pending_requests: int
    completed_cashins: int
    completed_cashouts: int
    simulation: bool = True


class SandboxReports:
    """Reporting can never update money or imply a real financial institution."""

    def __init__(self, store: SandboxStore):
        self.store = store

    def ledger_metrics(self) -> LedgerMetrics:
        with self.store.engine.connect() as db:
            ac = db.execute(select(func.count()).select_from(accounts)).scalar_one()
            ev = db.execute(select(func.count()).select_from(journals)).scalar_one()
            pl = db.execute(select(func.count()).select_from(postings)).scalar_one()
            debit = db.execute(select(func.coalesce(func.sum(postings.c.amount),0))
                               .where(postings.c.direction == "debit")).scalar_one()
            credit = db.execute(select(func.coalesce(func.sum(postings.c.amount),0))
                                .where(postings.c.direction == "credit")).scalar_one()
            frozen = db.execute(select(func.count()).select_from(accounts)
                                .where(accounts.c.frozen.is_(True))).scalar_one()
        return LedgerMetrics(ac, ev, pl, debit, credit, frozen)

    def agent_metrics(self, agent_account: str, *, commission_account: str) -> AgentMetrics:
        sim_id(agent_account, "agent float")
        sim_id(commission_account, "agent commission")
        with self.store.engine.connect() as db:
            float_row = db.execute(select(accounts).where(accounts.c.account_id == agent_account)).mappings().first()
            comm_row = db.execute(select(accounts).where(accounts.c.account_id == commission_account)).mappings().first()
            if not float_row or not comm_row or float_row["owner_id"] != comm_row["owner_id"]:
                raise MissingRecord("Agent synthetic accounts do not share the same owner")
            if float_row["kind"] != "agent_float" or comm_row["kind"] != "agent_commission":
                raise InvalidValue("Agent account categories must match")
            physical = db.execute(select(cash_inventory.c.cash).where(
                cash_inventory.c.agent_account == agent_account)).scalar_one_or_none()
            reqs = db.execute(select(requests.c.kind, requests.c.state)
                              .where(requests.c.agent_account == agent_account)).all()
        pending = sum(state in ("reserved", "awaiting", "customer_confirmed") for _,state in reqs)
        cin = sum(k == "cash_in" and s == "completed" for k,s in reqs)
        cout = sum(k == "cash_out" and s == "completed" for k,s in reqs)
        return AgentMetrics(agent_account, float_row["balance"], physical or 0,
                            comm_row["balance"], pending, cin, cout)

    def liability_by_kind(self) -> dict[str, int]:
        with self.store.engine.connect() as db:
            rows = db.execute(select(accounts.c.kind,func.sum(accounts.c.balance))
                              .group_by(accounts.c.kind)).all()
        return {k:int(v) for k,v in rows}

    def dashboard(self, *, max_events: int = 100000) -> dict[str, object]:
        if not 1 <= max_events <= 1_000_000:
            raise InvalidValue("Invalid bounded dashboard limit")
        metrics = self.ledger_metrics()
        if metrics.journal_count > max_events:
            raise InvalidValue("Sandbox dashboard event cap exceeded")
        with self.store.engine.connect() as db:
            states = db.execute(select(requests.c.state,func.count())
                                .group_by(requests.c.state)).all()
            alerts = db.execute(select(func.count()).select_from(security_events)).scalar_one()
            dead_outbox = db.execute(select(func.count()).select_from(outbox)
                                    .where(outbox.c.state == "dead")).scalar_one()
        return {"ledger": metrics.public(), "cash_states": dict(states),
                "redacted_security_events": alerts, "failed_notification_records": dead_outbox,
                "account_liabilities_by_kind_poisha": self.liability_by_kind(),
                "truth_in_advertising": "ALL BALANCES AND STATISTICS ARE FICTIONAL",
                "simulation": True, "bank_settlement_confirmed": False}

    def account_statement(self, account_id: str, *, limit: int = 100) -> tuple[dict[str, object], ...]:
        sim_id(account_id, "account")
        if not 1 <= limit <= 500:
            raise InvalidValue("Statement limit outside policy")
        with self.store.engine.connect() as db:
            rows = db.execute(select(postings.c.event_id,postings.c.direction,
                                     postings.c.amount, journals.c.created_at)
                              .join(journals, postings.c.event_id == journals.c.event_id)
                              .where(postings.c.account_id == account_id)
                              .order_by(journals.c.sequence.desc()).limit(limit)).mappings().all()
        return tuple({"event_id": row["event_id"], "side": row["direction"],
                      "amount_poisha": row["amount"], "created_at": row["created_at"],
                      "simulation": True} for row in rows)

    def activity_buckets(self, *, event_limit: int = 50000) -> tuple[dict[str, object], ...]:
        if not 1 <= event_limit <= 1_000_000:
            raise InvalidValue("Invalid activity scan")
        with self.store.engine.connect() as db:
            rows = db.execute(select(journals.c.operation,journals.c.created_at)
                              .limit(event_limit)).all()
        counts: dict[tuple[str,str],int] = {}
        for name,when in rows:
            date = datetime.fromisoformat(when).astimezone(timezone.utc).date().isoformat()
            key=(date,name)
            counts[key]=counts.get(key,0)+1
        return tuple({"date": day,"operation":op,"count":count,"simulation":True}
                     for (day,op),count in sorted(counts.items()))
