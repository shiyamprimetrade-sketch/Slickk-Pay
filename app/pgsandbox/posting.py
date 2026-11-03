"""Serializable sandbox double-entry posting and immutable journal verification.

**Fictional value only.** A single database transaction updates journal rows,
postings, account balances, and the chained head. PostgreSQL writers lock the
head row and sorted affected accounts before posting. On serialization failure,
callers must retry the entire operation with the SAME idempotency key.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable, Sequence
import json
from sqlalchemy import select, insert, update, func, and_
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError
from .errors import (InvalidValue, Conflict, InvariantError, InsufficientBalance,
                     MissingRecord, FrozenAccount, AuthorizationError)
from .guard import sim_id, event_key
from .money import minor
from .schema import accounts, journals, postings, chain, KIND_VALUES
from .store import SandboxStore, utc_now, GENESIS


def canonical(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=True)


def digest(value: object) -> str:
    return sha256(canonical(value).encode("utf-8")).hexdigest()


def sha_event(previous: str, payload: dict[str, object]) -> str:
    return sha256((previous + "|" + canonical(payload)).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    account_id: str
    direction: str
    amount: int

    def __post_init__(self):
        sim_id(self.account_id, "account")
        if self.direction not in ("credit", "debit"):
            raise InvalidValue("Ledger side must be debit or credit")
        minor(self.amount, positive=True)

    @property
    def delta(self) -> int:
        return self.amount if self.direction == "credit" else -self.amount

    def as_dict(self) -> dict[str, str | int]:
        return {"account": self.account_id, "side": self.direction, "poisha": self.amount}


@dataclass(frozen=True, slots=True)
class JournalReceipt:
    event_id: str
    operation: str
    idempotency_key: str
    entry_hash: str
    previous_hash: str
    number_of_lines: int
    simulation: bool = True


@dataclass(frozen=True, slots=True)
class AccountBalance:
    account_id: str
    owner_id: str
    kind: str
    poisha: int
    version: int
    frozen: bool
    simulation: bool = True


@dataclass(frozen=True)
class ChainProof:
    count: int
    valid: bool
    latest_hash: str
    total_debits: int
    total_credits: int
    mismatches: tuple[str, ...]
    simulation: bool = True


def _row_to_account(row) -> AccountBalance:
    return AccountBalance(row["account_id"], row["owner_id"], row["kind"],
                          row["balance"], row["version"], bool(row["frozen"]))


class LedgerService:
    def __init__(self, store: SandboxStore):
        self.store = store

    def open_account(self, account_id: str, owner_id: str, kind: str) -> AccountBalance:
        sim_id(account_id, "account")
        sim_id(owner_id, "owner")
        if kind not in KIND_VALUES:
            raise InvalidValue("Unknown sandbox account category")
        with self.store.transaction() as db:
            row = db.execute(select(accounts).where(accounts.c.account_id == account_id).with_for_update()).mappings().first()
            if row is not None:
                if row["owner_id"] != owner_id or row["kind"] != kind:
                    raise Conflict("Account cannot be reassigned")
                return _row_to_account(row)
            db.execute(insert(accounts).values(account_id=account_id, owner_id=owner_id,
                       kind=kind, balance=0, frozen=False, version=0, created_at=utc_now()))
            return _row_to_account(db.execute(select(accounts).where(accounts.c.account_id == account_id)).mappings().one())

    def balance(self, account_id: str) -> AccountBalance:
        sim_id(account_id, "account")
        with self.store.engine.connect() as db:
            row = db.execute(select(accounts).where(accounts.c.account_id == account_id)).mappings().first()
        if row is None:
            raise MissingRecord("Unknown sandbox account")
        return _row_to_account(row)

    def freeze(self, account_id: str, *, frozen: bool, actor: str) -> AccountBalance:
        sim_id(actor, "operator")
        if not isinstance(frozen, bool):
            raise InvalidValue("Invalid frozen flag")
        with self.store.transaction() as db:
            row = db.execute(select(accounts).where(accounts.c.account_id == account_id).with_for_update()).mappings().first()
            if row is None:
                raise MissingRecord("Unknown account")
            if row["kind"] == "sim_issuer":
                raise AuthorizationError("Issuer controls are test operator only")
            if row["frozen"] != frozen:
                db.execute(update(accounts).where(accounts.c.account_id == account_id).values(frozen=frozen, version=row["version"] + 1))
            result = db.execute(select(accounts).where(accounts.c.account_id == account_id)).mappings().one()
            return _row_to_account(result)

    def post(self, operation: str, idempotency_key: str, entries: Sequence[LedgerEntry], *, actor: str) -> JournalReceipt:
        with self.store.transaction() as db:
            return self.post_in_transaction(db, operation, idempotency_key, entries, actor=actor)

    def post_in_transaction(self, db: Connection, operation: str, idempotency_key: str,
                            entries: Sequence[LedgerEntry], *, actor: str) -> JournalReceipt:
        event_key(idempotency_key)
        sim_id(actor, "actor")
        if not isinstance(operation, str) or not 3 <= len(operation) <= 50 or not operation.replace("_", "").isalnum():
            raise InvalidValue("Invalid posting operation")
        if isinstance(entries, (str, bytes)) or not isinstance(entries, Sequence) or not 2 <= len(entries) <= 32:
            raise InvalidValue("Posting requires 2–32 lines")
        if not all(isinstance(x, LedgerEntry) for x in entries):
            raise InvalidValue("Invalid posting structure")
        debit_total = sum(x.amount for x in entries if x.direction == "debit")
        credit_total = sum(x.amount for x in entries if x.direction == "credit")
        if debit_total != credit_total or debit_total <= 0:
            raise InvariantError("Every journal must have equal nonzero debits and credits")
        if debit_total > 10**14:
            raise InvalidValue("Journal exceeds sandbox posting limit")
        payload = {"operation": operation, "key": idempotency_key,
                   "actor": actor, "lines": [x.as_dict() for x in entries]}
        request_digest = digest(payload)
        # Serialize writers through the singleton chain head on PostgreSQL. On
        # SQLite BEGIN IMMEDIATE already serializes local test writers.
        head = db.execute(select(chain).where(chain.c.id == 1).with_for_update()).mappings().first()
        if head is None:
            raise InvariantError("Missing journal chain head")
        existing = db.execute(select(journals).where(journals.c.idempotency_key == idempotency_key)).mappings().first()
        if existing is not None:
            if existing["request_digest"] != request_digest:
                raise Conflict("Same idempotency key with changed request")
            return JournalReceipt(existing["event_id"], existing["operation"], idempotency_key,
                                  existing["entry_hash"], existing["previous_hash"],
                                  len(entries))
        locked: dict[str, dict] = {}
        for account_id in sorted({x.account_id for x in entries}):
            row = db.execute(select(accounts).where(accounts.c.account_id == account_id).with_for_update()).mappings().first()
            if row is None:
                raise MissingRecord("Posting references an unknown account")
            if row["frozen"]:
                raise FrozenAccount("Frozen account cannot be posted")
            locked[account_id] = dict(row)
        changes: dict[str, int] = {}
        for entry in entries:
            changes[entry.account_id] = changes.get(entry.account_id, 0) + entry.delta
        for account_id, delta in changes.items():
            account = locked[account_id]
            resulting = account["balance"] + delta
            if account["kind"] != "sim_issuer" and resulting < 0:
                raise InsufficientBalance("No overdrafts for fictitious participant accounts")
            minor(resulting)
        previous_hash = head["latest_hash"]
        sequence = head["latest_sequence"] + 1
        event_id = f"sim_evt_{sha256((idempotency_key + ':' + request_digest).encode()).hexdigest()[:40]}"
        entry_payload = {**payload, "sequence": sequence, "event_id": event_id}
        entry_hash = sha_event(previous_hash, entry_payload)
        db.execute(insert(journals).values(event_id=event_id, idempotency_key=idempotency_key,
                   operation=operation, request_digest=request_digest, previous_hash=previous_hash,
                   entry_hash=entry_hash, created_at=utc_now(), actor_id=actor))
        for index, entry in enumerate(entries):
            db.execute(insert(postings).values(event_id=event_id, line_index=index,
                       account_id=entry.account_id, direction=entry.direction, amount=entry.amount))
        for account_id, delta in sorted(changes.items()):
            current = locked[account_id]
            db.execute(update(accounts).where(accounts.c.account_id == account_id)
                       .values(balance=current["balance"] + delta, version=current["version"] + 1))
        db.execute(update(chain).where(chain.c.id == 1).values(latest_hash=entry_hash, latest_sequence=sequence))
        return JournalReceipt(event_id, operation, idempotency_key, entry_hash, previous_hash, len(entries))

    def transfer(self, debit: str, credit: str, amount: int, *, key: str, actor: str,
                 operation: str = "sim_transfer") -> JournalReceipt:
        sim_id(debit, "sender")
        sim_id(credit, "recipient")
        if debit == credit:
            raise InvalidValue("Account cannot transfer to itself")
        minor(amount, positive=True)
        return self.post(operation, key, [LedgerEntry(debit, "debit", amount),
                                          LedgerEntry(credit, "credit", amount)], actor=actor)

    def _read_events(self, db: Connection):
        return db.execute(select(journals).order_by(journals.c.sequence)).mappings().all()

    def verify(self) -> ChainProof:
        mismatches: list[str] = []
        debits, credits = 0, 0
        with self.store.engine.connect() as db:
            events = self._read_events(db)
            account_rows = db.execute(select(accounts)).mappings().all()
            expected: dict[str, int] = {r["account_id"]: 0 for r in account_rows}
            previous = GENESIS
            for idx, event in enumerate(events, 1):
                rows = db.execute(select(postings).where(postings.c.event_id == event["event_id"])
                                  .order_by(postings.c.line_index)).mappings().all()
                lines = [{"account": r["account_id"], "side": r["direction"], "poisha": r["amount"]} for r in rows]
                # PostgreSQL sequences are not transactional; rollbacks can
                # leave harmless auto-increment gaps. Hash order is defined by
                # the locked chain head counter, not the SQL surrogate PK.
                if event["previous_hash"] != previous:
                    mismatches.append(f"chain_link:{idx}")
                if len(rows) < 2 or any(r["line_index"] != j for j, r in enumerate(rows)):
                    mismatches.append(f"posting_positions:{idx}")
                payload = {"operation": event["operation"], "key": event["idempotency_key"],
                           "actor": event["actor_id"], "lines": lines}
                if digest(payload) != event["request_digest"]:
                    mismatches.append(f"request_digest:{idx}")
                expected_hash = sha_event(previous, {**payload, "sequence": idx,
                                                     "event_id": event["event_id"]})
                if expected_hash != event["entry_hash"]:
                    mismatches.append(f"event_hash:{idx}")
                inside_debits = sum(r["amount"] for r in rows if r["direction"] == "debit")
                inside_credits = sum(r["amount"] for r in rows if r["direction"] == "credit")
                debits += inside_debits
                credits += inside_credits
                if inside_debits != inside_credits:
                    mismatches.append(f"unbalanced:{idx}")
                for row in rows:
                    delta = row["amount"] * (1 if row["direction"] == "credit" else -1)
                    expected[row["account_id"]] = expected.get(row["account_id"], 0) + delta
                previous = event["entry_hash"]
            head = db.execute(select(chain).where(chain.c.id == 1)).mappings().one()
            if head["latest_sequence"] != len(events) or head["latest_hash"] != previous:
                mismatches.append("head_mismatch")
            for row in account_rows:
                if expected[row["account_id"]] != row["balance"]:
                    mismatches.append("account_balance:" + row["account_id"])
        return ChainProof(len(events), len(mismatches) == 0, previous,
                          debits, credits, tuple(mismatches))

    def event(self, key: str) -> JournalReceipt:
        event_key(key)
        with self.store.engine.connect() as db:
            event = db.execute(select(journals).where(journals.c.idempotency_key == key)).mappings().first()
            if not event:
                raise MissingRecord("Event reference not found")
            count = db.execute(select(func.count()).select_from(postings).where(postings.c.event_id == event["event_id"])).scalar_one()
            return JournalReceipt(event["event_id"], event["operation"], key,
                                  event["entry_hash"], event["previous_hash"], count)

    def entries(self, event_id: str) -> tuple[LedgerEntry, ...]:
        sim_id(event_id, "event")
        with self.store.engine.connect() as db:
            rows = db.execute(select(postings).where(postings.c.event_id == event_id)
                              .order_by(postings.c.line_index)).mappings().all()
            if not rows:
                raise MissingRecord("Journal event not found")
            return tuple(LedgerEntry(r["account_id"], r["direction"], r["amount"]) for r in rows)

    def statement(self, account_id: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, object]]:
        sim_id(account_id, "account")
        if not 1 <= limit <= 250 or not 0 <= offset <= 1_000_000:
            raise InvalidValue("Invalid statement pagination")
        with self.store.engine.connect() as db:
            rows = db.execute(select(postings.c.event_id, postings.c.direction, postings.c.amount,
                       journals.c.created_at, journals.c.operation)
                       .join(journals, postings.c.event_id == journals.c.event_id)
                       .where(postings.c.account_id == account_id).order_by(journals.c.sequence, postings.c.line_index)
                       .limit(limit).offset(offset)).mappings().all()
            return [dict(row) | {"simulation": True} for row in rows]
