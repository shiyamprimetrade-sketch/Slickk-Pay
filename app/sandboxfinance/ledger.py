"""Durable, transactional double-entry *fictional-money* ledger for sandbox trials.

Not a bank ledger. All accounts contain fictitious poisha. Never connect to any
production gateway, bank, wallet or live SQLite file.  PostgreSQL integration,
HA, regulatory data retention and a second-party audit are not implemented.

The SQLite design emphasizes invariants and isolation, suitable for deterministic
pilots on a single process (including forced crash/retry tests).  BEGIN IMMEDIATE
serializes writers. In production, use a separately reviewed transactional
PostgreSQL architecture, not this embedded development database.
"""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
from typing import Iterable, Sequence


class LedgerError(Exception):
    pass


class InsufficientFunds(LedgerError):
    pass


class DuplicateReference(LedgerError):
    pass


class AccountBlocked(LedgerError):
    pass


class InvariantViolation(LedgerError):
    pass


KINDS = frozenset({
    "customer", "agent_float", "agent_commission", "platform_revenue",
    "platform_treasury", "escrow", "synthetic_issuer", "merchant",
})

ACCOUNT_PREFIX = "sim_"
MAX_POSTING = 10**14


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _canonical(obj) -> str:
    return json.dumps(obj, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _reference(value: str, field: str = "reference") -> str:
    if not isinstance(value, str) or not (4 <= len(value) <= 96):
        raise LedgerError(f"Invalid {field}")
    if not all(c.isascii() and (c.isalnum() or c in "-_:.") for c in value):
        raise LedgerError(f"Invalid {field} characters")
    return value


def _amount(value: int, *, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < (0 if allow_zero else 1) or value > MAX_POSTING:
        raise LedgerError("Amount must be positive integer poisha")
    return value


@dataclass(frozen=True)
class Posting:
    account_id: str
    direction: str
    amount: int

    def __post_init__(self):
        _reference(self.account_id, "account_id")
        if self.direction not in ("debit", "credit"):
            raise LedgerError("Invalid posting direction")
        _amount(self.amount)

    def balance_change(self) -> int:
        # Customer/agent account balances are credit-normal in this sandbox.
        return self.amount if self.direction == "credit" else -self.amount

    def canonical(self) -> dict[str, str | int]:
        return {"account": self.account_id, "direction": self.direction, "poisha": self.amount}


@dataclass(frozen=True)
class Receipt:
    event_id: str
    idempotency_key: str
    operation: str
    event_hash: str
    posting_count: int
    recorded_at: str
    simulation: bool = True


@dataclass(frozen=True)
class AccountView:
    account_id: str
    owner_id: str
    kind: str
    balance_poisha: int
    frozen: bool
    simulation: bool = True


SCHEMA = """
CREATE TABLE IF NOT EXISTS sim_accounts(
 account_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, kind TEXT NOT NULL,
 balance_poisha INTEGER NOT NULL DEFAULT 0,
 frozen INTEGER NOT NULL DEFAULT 0 CHECK(frozen IN (0,1)),
 created_at TEXT NOT NULL,
 CHECK(length(account_id)>=4), CHECK(length(owner_id)>=4),
 CHECK(kind IN ('customer','agent_float','agent_commission','platform_revenue',
                'platform_treasury','escrow','synthetic_issuer','merchant')),
 CHECK(kind='synthetic_issuer' OR balance_poisha>=0)
);
CREATE INDEX IF NOT EXISTS sim_accounts_owner ON sim_accounts(owner_id, kind);
CREATE TABLE IF NOT EXISTS sim_events(
 event_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE,
 request_digest TEXT NOT NULL, operation TEXT NOT NULL,
 created_at TEXT NOT NULL, previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL,
 posting_count INTEGER NOT NULL CHECK(posting_count>=2)
);
CREATE INDEX IF NOT EXISTS sim_events_created ON sim_events(created_at);
CREATE TABLE IF NOT EXISTS sim_postings(
 event_id TEXT NOT NULL REFERENCES sim_events(event_id),
 line_index INTEGER NOT NULL, account_id TEXT NOT NULL REFERENCES sim_accounts(account_id),
 direction TEXT NOT NULL CHECK(direction IN ('debit','credit')),
 amount_poisha INTEGER NOT NULL CHECK(amount_poisha>0),
 PRIMARY KEY(event_id,line_index)
);
CREATE INDEX IF NOT EXISTS sim_postings_account ON sim_postings(account_id,event_id);
CREATE TABLE IF NOT EXISTS sim_account_audit(
 audit_id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL,
 action TEXT NOT NULL, created_at TEXT NOT NULL, event_digest TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS sim_events_update_block
 BEFORE UPDATE ON sim_events BEGIN SELECT RAISE(ABORT,'immutable journal events'); END;
CREATE TRIGGER IF NOT EXISTS sim_events_delete_block
 BEFORE DELETE ON sim_events BEGIN SELECT RAISE(ABORT,'immutable journal events'); END;
CREATE TRIGGER IF NOT EXISTS sim_postings_update_block
 BEFORE UPDATE ON sim_postings BEGIN SELECT RAISE(ABORT,'immutable ledger postings'); END;
CREATE TRIGGER IF NOT EXISTS sim_postings_delete_block
 BEFORE DELETE ON sim_postings BEGIN SELECT RAISE(ABORT,'immutable ledger postings'); END;
"""


class SandboxLedger:
    """One-process serialized SQLite ledger, intentionally disconnected from live checkout."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path == ":memory:":
            raise LedgerError("Use a named temporary file for repeatable sandbox tests")
        self._lock = threading.RLock()
        self._init()

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=10000")
            db.row_factory = sqlite3.Row
            yield db
            if db.in_transaction:
                db.commit()
        except Exception:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    def _init(self) -> None:
        with self._lock, self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)

    def create_account(self, account_id: str, owner_id: str, kind: str) -> AccountView:
        _reference(account_id, "account_id")
        _reference(owner_id, "owner_id")
        if not account_id.startswith(ACCOUNT_PREFIX) or kind not in KINDS:
            raise LedgerError("Only sandbox accounts are allowed")
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                existing = db.execute("SELECT * FROM sim_accounts WHERE account_id=?", (account_id,)).fetchone()
                if existing:
                    if existing["owner_id"] != owner_id or existing["kind"] != kind:
                        raise DuplicateReference("Account already exists under another owner/kind")
                    db.commit()
                    return self._as_account(existing)
                db.execute("INSERT INTO sim_accounts(account_id,owner_id,kind,created_at) VALUES(?,?,?,?)",
                           (account_id, owner_id, kind, _utc()))
                db.execute("INSERT INTO sim_account_audit(account_id,action,created_at,event_digest) VALUES(?,?,?,?)",
                           (account_id, "created", _utc(), _hash(account_id)))
                row = db.execute("SELECT * FROM sim_accounts WHERE account_id=?", (account_id,)).fetchone()
                db.commit()
                return self._as_account(row)
            except Exception:
                db.rollback()
                raise

    @staticmethod
    def _as_account(row: sqlite3.Row) -> AccountView:
        return AccountView(row["account_id"], row["owner_id"], row["kind"],
                           row["balance_poisha"], bool(row["frozen"]))

    def account(self, account_id: str) -> AccountView:
        with self._connect() as db:
            row = db.execute("SELECT * FROM sim_accounts WHERE account_id=?", (account_id,)).fetchone()
            if row is None:
                raise LedgerError("Account not found")
            return self._as_account(row)

    def accounts_for(self, owner_id: str) -> tuple[AccountView, ...]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM sim_accounts WHERE owner_id=? ORDER BY account_id", (owner_id,))
            return tuple(self._as_account(r) for r in rows)

    def freeze(self, account_id: str, frozen: bool = True) -> None:
        if not isinstance(frozen, bool):
            raise LedgerError("Invalid freeze flag")
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                count = db.execute("UPDATE sim_accounts SET frozen=? WHERE account_id=?",
                                   (int(frozen), account_id)).rowcount
                if count != 1:
                    raise LedgerError("Account not found")
                db.execute("INSERT INTO sim_account_audit(account_id,action,created_at,event_digest) VALUES(?,?,?,?)",
                           (account_id, "frozen" if frozen else "unfrozen", _utc(), _hash(account_id + str(frozen))))
                db.commit()
            except Exception:
                db.rollback()
                raise

    def post(self, *, operation: str, idempotency_key: str, postings: Sequence[Posting]) -> Receipt:
        """Atomically commit balanced journal event and balance changes."""
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            receipt = self.post_in_transaction(db, operation=operation,
                                               idempotency_key=idempotency_key,
                                               postings=postings)
            db.commit()
            return receipt

    def post_in_transaction(self, db: sqlite3.Connection, *, operation: str,
                            idempotency_key: str, postings: Sequence[Posting]) -> Receipt:
        """Stage an event in caller's SQLite transaction for cash-state atomicity.

        Caller MUST hold BEGIN IMMEDIATE and the shared in-process lock. This
        method never commits: a failed cash-state write rolls back the journal.
        """
        if not db.in_transaction:
            raise LedgerError("An active explicit SQLite transaction is required")
        _reference(operation, "operation")
        _reference(idempotency_key, "idempotency_key")
        if not isinstance(postings, (list, tuple)) or len(postings) < 2 or len(postings) > 20:
            raise LedgerError("Require 2–20 journal postings")
        if not all(isinstance(line, Posting) for line in postings):
            raise LedgerError("Invalid posting type")
        debits = sum(line.amount for line in postings if line.direction == "debit")
        credits = sum(line.amount for line in postings if line.direction == "credit")
        if debits != credits or debits <= 0:
            raise InvariantViolation("Every journal event must be balanced")
        if debits > MAX_POSTING:
            raise LedgerError("Posting total exceeds safety bound")
        request = {"operation": operation, "idempotency_key": idempotency_key,
                   "postings": [p.canonical() for p in postings]}
        request_digest = _hash(_canonical(request))
        previous = db.execute("SELECT * FROM sim_events WHERE idempotency_key=?",
                              (idempotency_key,)).fetchone()
        if previous:
            if previous["request_digest"] != request_digest:
                raise DuplicateReference("Idempotency key reused with changed instructions")
            return Receipt(previous["event_id"], previous["idempotency_key"],
                           previous["operation"], previous["event_hash"],
                           previous["posting_count"], previous["created_at"])
        balances: dict[str, int] = {}
        kinds: dict[str, str] = {}
        for line in postings:
            row = db.execute("SELECT * FROM sim_accounts WHERE account_id=?",
                             (line.account_id,)).fetchone()
            if row is None:
                raise LedgerError("Posting refers to nonexistent account")
            if row["frozen"]:
                raise AccountBlocked("Frozen accounts cannot send or receive postings")
            balances.setdefault(line.account_id, row["balance_poisha"])
            kinds[line.account_id] = row["kind"]
            balances[line.account_id] += line.balance_change()
        for account_id, new_balance in balances.items():
            if new_balance < 0 and kinds[account_id] != "synthetic_issuer":
                raise InsufficientFunds("Insufficient sandbox funds")
            if abs(new_balance) > MAX_POSTING:
                raise LedgerError("Balance exceeds safety bound")
        last = db.execute("SELECT event_hash FROM sim_events ORDER BY rowid DESC LIMIT 1").fetchone()
        previous_hash = last[0] if last else "0" * 64
        # Stable ID derived from supplied operation key rather than wallet/customer PII.
        event_id = "evt_" + _hash("event:" + idempotency_key)[:32]
        created_at = _utc()
        event_hash = _hash(_canonical({"id": event_id, "previous": previous_hash,
                                       "request": request_digest, "recorded": created_at}))
        db.execute("INSERT INTO sim_events VALUES (?,?,?,?,?,?,?,?)",
                   (event_id, idempotency_key, request_digest, operation, created_at,
                    previous_hash, event_hash, len(postings)))
        for i, line in enumerate(postings):
            db.execute("INSERT INTO sim_postings VALUES(?,?,?,?,?)",
                       (event_id, i, line.account_id, line.direction, line.amount))
        for account_id, new_balance in balances.items():
            db.execute("UPDATE sim_accounts SET balance_poisha=? WHERE account_id=?",
                       (new_balance, account_id))
        return Receipt(event_id, idempotency_key, operation, event_hash,
                       len(postings), created_at)

    def transfer(self, sender: str, receiver: str, amount: int, *, reference: str,
                 operation: str = "transfer") -> Receipt:
        if sender == receiver:
            raise LedgerError("Sender and recipient cannot be the same")
        _amount(amount)
        return self.post(operation=operation, idempotency_key=reference,
                         postings=[Posting(sender, "debit", amount),
                                   Posting(receiver, "credit", amount)])

    def synthetic_issue(self, recipient: str, amount: int, *, reference: str) -> Receipt:
        """Explicitly manufacture test-only money with matching issuer debit."""
        if self.account(recipient).kind == "synthetic_issuer":
            raise LedgerError("Issuer cannot issue to issuer")
        _amount(amount)
        return self.transfer("sim_issuer", recipient, amount, reference=reference,
                             operation="synthetic_test_funding")

    def postings_for(self, account_id: str, *, limit: int = 100) -> list[dict]:
        if not 1 <= limit <= 500:
            raise LedgerError("Invalid history limit")
        with self._connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT p.event_id,p.direction,p.amount_poisha,e.operation,e.created_at "
                "FROM sim_postings p JOIN sim_events e ON e.event_id=p.event_id "
                "WHERE p.account_id=? ORDER BY e.created_at DESC,p.line_index DESC LIMIT ?",
                (account_id, limit)).fetchall()]

    def verify(self) -> dict[str, int | bool | str]:
        """Reconstruct every account balance and every hash link independently."""
        with self._connect() as db:
            accounts = db.execute("SELECT * FROM sim_accounts").fetchall()
            running = {a["account_id"]: 0 for a in accounts}
            events = db.execute("SELECT * FROM sim_events ORDER BY rowid").fetchall()
            last_hash = "0" * 64
            for event in events:
                lines = db.execute("SELECT * FROM sim_postings WHERE event_id=? ORDER BY line_index",
                                   (event["event_id"],)).fetchall()
                if len(lines) != event["posting_count"] or len(lines) < 2:
                    raise InvariantViolation("Event posting count mismatch")
                debits, credits = 0, 0
                for line in lines:
                    if line["account_id"] not in running:
                        raise InvariantViolation("Dangling posting account")
                    if line["direction"] == "debit":
                        debits += line["amount_poisha"]
                        running[line["account_id"]] -= line["amount_poisha"]
                    else:
                        credits += line["amount_poisha"]
                        running[line["account_id"]] += line["amount_poisha"]
                if debits != credits:
                    raise InvariantViolation("Unbalanced journal event")
                digest = _hash(_canonical({"id": event["event_id"], "previous": last_hash,
                                           "request": event["request_digest"],
                                           "recorded": event["created_at"]}))
                if event["previous_hash"] != last_hash or event["event_hash"] != digest:
                    raise InvariantViolation("Journal hash chain corrupted")
                last_hash = digest
            for account in accounts:
                if account["balance_poisha"] != running[account["account_id"]]:
                    raise InvariantViolation("Stored balance differs from journal reconstruction")
                if account["kind"] != "synthetic_issuer" and account["balance_poisha"] < 0:
                    raise InvariantViolation("Negative participant balance")
            if sum(running.values()) != 0:
                raise InvariantViolation("System-wide journals do not net to zero")
            return {"simulation": True, "accounts": len(accounts), "events": len(events),
                    "posting_lines": sum(e["posting_count"] for e in events),
                    "journal_chain_tip": last_hash, "net_poisha": sum(running.values())}
