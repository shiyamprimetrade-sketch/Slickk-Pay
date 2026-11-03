"""Deterministic transaction-limit and financial-velocity policy for synthetic funds.

This is an internal policy sandbox, NOT regulatory AML/CTF compliance. It models
limits, roles, merchant caps, unusual activity flags and simultaneous consumers.
Cash or transfer journal postings must be guarded in the same database transaction
as velocity reservations to avoid read-check-write races.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3
import threading
from typing import Iterable


class LimitError(ValueError):
    pass


class LimitExceeded(LimitError):
    pass


class ReviewRequired(LimitError):
    pass


@dataclass(frozen=True)
class LimitPolicy:
    version: str
    category: str
    per_transaction_poisha: int
    daily_total_poisha: int
    daily_count: int
    rolling_hour_poisha: int
    rolling_hour_count: int
    max_distinct_counterparties_daily: int
    review_amount_poisha: int
    active: bool = True
    approved_for_real_money: bool = False

    def __post_init__(self):
        if not self.version or not self.category or self.approved_for_real_money:
            raise LimitError("Sandbox limits cannot authorize real payments")
        for field_name in ("per_transaction_poisha", "daily_total_poisha", "daily_count",
                           "rolling_hour_poisha", "rolling_hour_count",
                           "max_distinct_counterparties_daily", "review_amount_poisha"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise LimitError("Invalid limit policy field: " + field_name)
        if self.per_transaction_poisha > self.daily_total_poisha:
            raise LimitError("Single payment must not exceed daily cap")


@dataclass(frozen=True)
class LimitDecision:
    accepted: bool
    review: bool
    reason_codes: tuple[str, ...]
    policy_version: str
    daily_count_including_candidate: int
    daily_poisha_including_candidate: int
    hour_count_including_candidate: int
    simulated: bool = True


SCHEMA = """
CREATE TABLE IF NOT EXISTS sim_velocity_events(
 event_ref TEXT PRIMARY KEY,
 owner_id TEXT NOT NULL,
 counterparty_id TEXT NOT NULL,
 category TEXT NOT NULL,
 amount_poisha INTEGER NOT NULL CHECK(amount_poisha>0),
 occurred_at TEXT NOT NULL,
 policy_version TEXT NOT NULL,
 review_flag INTEGER NOT NULL DEFAULT 0 CHECK(review_flag IN (0,1)),
 request_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sim_velocity_owner_time
 ON sim_velocity_events(owner_id,occurred_at);
CREATE INDEX IF NOT EXISTS sim_velocity_category_time
 ON sim_velocity_events(category,occurred_at);
CREATE TRIGGER IF NOT EXISTS sim_velocity_immutable_update
 BEFORE UPDATE ON sim_velocity_events BEGIN SELECT RAISE(ABORT,'velocity evidence immutable'); END;
CREATE TRIGGER IF NOT EXISTS sim_velocity_immutable_delete
 BEFORE DELETE ON sim_velocity_events BEGIN SELECT RAISE(ABORT,'velocity evidence immutable'); END;
"""


def pilot_limits() -> dict[str, LimitPolicy]:
    """Illustrative limits, not public/legal thresholds."""
    return {
        "transfer": LimitPolicy("pilot-limits-v1", "transfer", 200_000, 1_000_000,
                                15, 300_000, 6, 8, 100_000),
        "cash_in": LimitPolicy("pilot-limits-v1", "cash_in", 250_000, 1_000_000,
                               12, 400_000, 5, 4, 120_000),
        "cash_out": LimitPolicy("pilot-limits-v1", "cash_out", 200_000, 700_000,
                                10, 300_000, 4, 3, 100_000),
        "merchant": LimitPolicy("pilot-limits-v1", "merchant", 300_000, 1_000_000,
                                20, 450_000, 10, 12, 150_000),
    }


def _utc_at(t: datetime | None = None) -> datetime:
    value = t or datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise LimitError("Clock must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="microseconds")


def _request_hash(*, owner_id: str, counterparty_id: str, category: str, amount: int,
                  policy_version: str) -> str:
    data = {"owner": owner_id, "counterparty": counterparty_id, "category": category,
            "amount": amount, "policy": policy_version}
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(",", ":")).encode()).hexdigest()


class VelocityBook:
    """A persistent limit book sharing a transaction with sandbox journal.

    `reserve_in_transaction` never commits; caller owns BEGIN IMMEDIATE. A policy
    rejection aborts before a ledger posting and callers must roll back.
    """

    def __init__(self, connect, policies: dict[str, LimitPolicy] | None = None):
        self.connect = connect
        self.policies = policies or pilot_limits()
        with connect() as db:
            db.executescript(SCHEMA)

    def policy_for(self, category: str) -> LimitPolicy:
        policy = self.policies.get(category)
        if policy is None or not policy.active:
            raise LimitExceeded("Unsupported or inactive transaction category")
        return policy

    def _aggregate(self, db: sqlite3.Connection, owner_id: str, category: str,
                   now: datetime) -> tuple[int,int,int,int,int]:
        midnight = now.replace(hour=0,minute=0,second=0,microsecond=0)
        hour_ago = now - timedelta(hours=1)
        daily = db.execute(
            "SELECT COUNT(*),COALESCE(SUM(amount_poisha),0),COUNT(DISTINCT counterparty_id) "
            "FROM sim_velocity_events WHERE owner_id=? AND category=? AND occurred_at>=? AND occurred_at<=?",
            (owner_id,category,_iso(midnight),_iso(now))).fetchone()
        hourly = db.execute(
            "SELECT COUNT(*),COALESCE(SUM(amount_poisha),0) FROM sim_velocity_events "
            "WHERE owner_id=? AND category=? AND occurred_at>=? AND occurred_at<=?",
            (owner_id,category,_iso(hour_ago),_iso(now))).fetchone()
        return int(daily[0]),int(daily[1]),int(daily[2]),int(hourly[0]),int(hourly[1])

    def evaluate(self, db: sqlite3.Connection, *, event_ref: str, owner_id: str,
                 counterparty_id: str, category: str, amount_poisha: int,
                 now: datetime | None = None) -> LimitDecision:
        policy = self.policy_for(category)
        instant = _utc_at(now)
        if not all(isinstance(s, str) and 4 <= len(s) <= 96 for s in
                   (event_ref,owner_id,counterparty_id)):
            raise LimitError("Missing bounded references")
        if isinstance(amount_poisha, bool) or not isinstance(amount_poisha,int) or amount_poisha <= 0:
            raise LimitError("Amount must be positive poisha")
        expected = _request_hash(owner_id=owner_id,counterparty_id=counterparty_id,
                                 category=category,amount=amount_poisha,
                                 policy_version=policy.version)
        existing = db.execute("SELECT * FROM sim_velocity_events WHERE event_ref=?",
                              (event_ref,)).fetchone()
        if existing:
            if existing["request_hash"] != expected:
                raise LimitError("Reference reused for different velocity event")
            return LimitDecision(True, bool(existing["review_flag"]), ("IDEMPOTENT_REPLAY",),
                                 policy.version, 0, 0, 0)
        daily_count,daily_value,distinct_count,hour_count,hour_value = self._aggregate(
            db,owner_id,category,instant)
        prior_counterparty = db.execute(
            "SELECT 1 FROM sim_velocity_events WHERE owner_id=? AND category=? "
            "AND counterparty_id=? AND occurred_at>=? LIMIT 1",
            (owner_id,category,counterparty_id,
             _iso(instant.replace(hour=0,minute=0,second=0,microsecond=0)))).fetchone()
        reasons=[]
        if amount_poisha > policy.per_transaction_poisha:
            reasons.append("PER_TRANSACTION_LIMIT")
        if daily_value+amount_poisha > policy.daily_total_poisha:
            reasons.append("DAILY_AMOUNT_LIMIT")
        if daily_count+1 > policy.daily_count:
            reasons.append("DAILY_COUNT_LIMIT")
        if hour_value+amount_poisha > policy.rolling_hour_poisha:
            reasons.append("HOURLY_AMOUNT_LIMIT")
        if hour_count+1 > policy.rolling_hour_count:
            reasons.append("HOURLY_COUNT_LIMIT")
        if distinct_count+(0 if prior_counterparty else 1) > policy.max_distinct_counterparties_daily:
            reasons.append("COUNTERPARTY_LIMIT")
        review = amount_poisha >= policy.review_amount_poisha
        if review:
            reasons.append("HUMAN_REVIEW_THRESHOLD")
        return LimitDecision(not any(x.endswith("LIMIT") for x in reasons), review,
                             tuple(reasons),policy.version,
                             daily_count+1,daily_value+amount_poisha,hour_count+1)

    def reserve_in_transaction(self, db: sqlite3.Connection, *, event_ref: str,
                               owner_id: str, counterparty_id: str, category: str,
                               amount_poisha: int, now: datetime | None = None) -> LimitDecision:
        if not db.in_transaction:
            raise LimitError("BEGIN IMMEDIATE transaction required")
        instant = _utc_at(now)
        result = self.evaluate(db,event_ref=event_ref,owner_id=owner_id,
                               counterparty_id=counterparty_id,category=category,
                               amount_poisha=amount_poisha,now=instant)
        if not result.accepted:
            raise LimitExceeded("Transaction exceeds sandbox velocity policy: " + ",".join(result.reason_codes))
        if result.reason_codes == ("IDEMPOTENT_REPLAY",):
            return result
        digest = _request_hash(owner_id=owner_id,counterparty_id=counterparty_id,
                               category=category,amount=amount_poisha,
                               policy_version=result.policy_version)
        db.execute("INSERT INTO sim_velocity_events VALUES(?,?,?,?,?,?,?,?,?)",
                   (event_ref,owner_id,counterparty_id,category,amount_poisha,
                    _iso(instant),result.policy_version,int(result.review),digest))
        return result

    def event_count(self, owner_id: str) -> int:
        with self.connect() as db:
            return db.execute("SELECT COUNT(*) FROM sim_velocity_events WHERE owner_id=?",
                              (owner_id,)).fetchone()[0]

    def aggregate_snapshot(self, owner_id: str, *, now: datetime | None = None) -> dict[str,dict]:
        instant = _utc_at(now)
        with self.connect() as db:
            return {category:{"daily_count":values[0],"daily_poisha":values[1],
                              "unique_counterparties":values[2],"hour_count":values[3],
                              "hour_poisha":values[4],"simulation":True}
                    for category in self.policies
                    for values in [self._aggregate(db,owner_id,category,instant)]}

    def verify_no_duplicate_references(self) -> bool:
        with self.connect() as db:
            total=db.execute("SELECT COUNT(*) FROM sim_velocity_events").fetchone()[0]
            distinct=db.execute("SELECT COUNT(DISTINCT event_ref) FROM sim_velocity_events").fetchone()[0]
        return total==distinct
