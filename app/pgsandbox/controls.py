"""Synthetic transaction policies with database-transactional velocity assertions.

Not KYC, sanctions screening, or a production AML decision. This module only
compares deterministic sandbox events against explicit synthetic limits.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import re
from sqlalchemy import select, insert, func
from sqlalchemy.engine import Connection
from .schema import money_events, accounts
from .posting import LedgerService, canonical
from .store import utc_now
from .guard import sim_id, event_key
from .money import minor
from .errors import InvalidValue, AuthorizationError, RateLimit, MissingRecord


@dataclass(frozen=True)
class LimitProfile:
    profile_id: str
    max_single_poisha: int
    max_daily_poisha: int
    max_daily_count: int
    min_principal_poisha: int = 100

    def __post_init__(self):
        if not re.fullmatch(r"pilot_[a-z0-9_]{4,40}", self.profile_id):
            raise InvalidValue("Invalid limit profile")
        if any(isinstance(v, bool) or not isinstance(v, int) for v in (
            self.max_single_poisha, self.max_daily_poisha, self.max_daily_count,
            self.min_principal_poisha)):
            raise InvalidValue("Limits must be integers")
        if not (0 < self.min_principal_poisha <= self.max_single_poisha <= self.max_daily_poisha <= 10**14):
            raise InvalidValue("Invalid monetary ceilings")
        if not 1 <= self.max_daily_count <= 100000:
            raise InvalidValue("Invalid transaction count ceiling")


@dataclass(frozen=True)
class RiskDecision:
    accepted: bool
    reason: str
    daily_count: int
    daily_poisha: int
    principal_poisha: int
    policy: str
    simulation: bool = True


DEFAULT_LIMITS = LimitProfile("pilot_basic_2026", 5_000_000, 15_000_000, 30)
HIGH_REVIEW = LimitProfile("pilot_review_2026", 1_000_000, 3_000_000, 5)


class VelocityController:
    """Must evaluate and record inside the SAME transaction as ledger posting."""

    def __init__(self, ledger: LedgerService, profile: LimitProfile = DEFAULT_LIMITS):
        self.ledger = ledger
        self.profile = profile

    def _cutoff(self, now: datetime) -> str:
        if now.tzinfo is None:
            raise InvalidValue("Naive timestamps are forbidden")
        midnight = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight.isoformat(timespec="microseconds")

    def evaluate(self, db: Connection, account_id: str, operation: str, principal_poisha: int,
                 *, at: datetime | None = None) -> RiskDecision:
        sim_id(account_id, "payer")
        minor(principal_poisha, positive=True)
        if not re.fullmatch(r"[a-z][a-z_]{3,39}", operation):
            raise InvalidValue("Invalid operation")
        now = at or datetime.now(timezone.utc)
        # Chain lock serializes all ledger writers including velocity checks in
        # this lab. The caller MUST already have the same head-row lock.
        cutoff = self._cutoff(now)
        count, total = db.execute(select(func.count(), func.coalesce(func.sum(money_events.c.amount), 0))
                                  .where(money_events.c.account_id == account_id)
                                  .where(money_events.c.occurred_at >= cutoff)).one()
        count = int(count)
        total = int(total)
        if principal_poisha < self.profile.min_principal_poisha:
            return RiskDecision(False, "BELOW_MINIMUM", count, total, principal_poisha, self.profile.profile_id)
        if principal_poisha > self.profile.max_single_poisha:
            return RiskDecision(False, "SINGLE_LIMIT", count, total, principal_poisha, self.profile.profile_id)
        if total + principal_poisha > self.profile.max_daily_poisha:
            return RiskDecision(False, "DAILY_VALUE_LIMIT", count, total, principal_poisha, self.profile.profile_id)
        if count + 1 > self.profile.max_daily_count:
            return RiskDecision(False, "DAILY_COUNT_LIMIT", count, total, principal_poisha, self.profile.profile_id)
        return RiskDecision(True, "APPROVED_SYNTHETIC", count, total, principal_poisha, self.profile.profile_id)

    def record(self, db: Connection, account_id: str, operation: str, amount: int,
               event_id: str) -> None:
        sim_id(account_id, "actor account")
        sim_id(event_id, "journal event")
        minor(amount, positive=True)
        db.execute(insert(money_events).values(account_id=account_id, operation=operation,
                   amount=amount, event_id=event_id, occurred_at=utc_now()))

    def check_or_raise(self, db: Connection, account_id: str, operation: str,
                       amount: int) -> RiskDecision:
        decision = self.evaluate(db, account_id, operation, amount)
        if not decision.accepted:
            raise RateLimit(decision.reason)
        return decision


class ActorAuthorization:
    """Minimal role/ownership checks using synthetic sandbox identities only."""

    def __init__(self, ledger: LedgerService):
        self.ledger = ledger

    def require_owner(self, db: Connection, account_id: str, actor_id: str,
                      *, kinds: frozenset[str] | None = None) -> dict:
        sim_id(account_id, "account")
        sim_id(actor_id, "actor")
        row = db.execute(select(accounts).where(accounts.c.account_id == account_id)).mappings().first()
        if row is None:
            raise MissingRecord("Account not found")
        if row["owner_id"] != actor_id:
            raise AuthorizationError("Actor does not own synthetic account")
        if kinds is not None and row["kind"] not in kinds:
            raise AuthorizationError("Actor role cannot initiate this operation")
        if row["frozen"]:
            raise AuthorizationError("Account is frozen")
        return dict(row)

    def require_agent_float(self, db: Connection, account_id: str, actor_id: str) -> dict:
        return self.require_owner(db, account_id, actor_id, kinds=frozenset({"agent_float"}))

    def require_customer(self, db: Connection, account_id: str, actor_id: str) -> dict:
        return self.require_owner(db, account_id, actor_id, kinds=frozenset({"customer"}))


def redact_account(account_id: str) -> str:
    sim_id(account_id, "account")
    return account_id[:6] + "..." + account_id[-4:]


def synthetic_risk_explanation(*, reason: str, amount: int, available: int,
                               profile: LimitProfile) -> dict[str, str | bool]:
    minor(amount, positive=True)
    minor(available)
    return {"allowed": reason == "APPROVED_SYNTHETIC", "reason_code": reason,
            "profile": profile.profile_id, "balance_sufficient": available >= amount,
            "amount_bdt_minor": str(amount), "fictional": True,
            "human_review_required": reason != "APPROVED_SYNTHETIC"}
