"""Slickk Pay sandbox ledger. Simulation only; not a bank or payment processor."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

FEE_TABLE = [
    (250, {7: 3, 15: 4, 30: 6}),
    (500, {7: 5, 15: 8, 30: 15}),
    (1000, {7: 7, 15: 12, 30: 20}),
    (2000, {7: 10, 15: 20, 30: 30}),
    (3000, {7: 15, 15: 30, 30: 50}),
    (5000, {7: 20, 15: 40, 30: 70}),
    (7000, {7: 25, 15: 50, 30: 90}),
    (10000, {7: 35, 15: 70, 30: 130}),
]
APPROVED_DEMO_CATEGORIES = {"utility", "mobile", "education", "healthcare", "government", "savings", "insurance", "toll"}


class DomainError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def taka_to_poisha(amount: Any) -> int:
    if isinstance(amount, bool):
        raise DomainError("Amount must be numeric")
    try:
        number = Decimal(str(amount))
    except (InvalidOperation, ValueError):
        raise DomainError("Invalid amount")
    if not number.is_finite() or number <= 0 or number.as_tuple().exponent < -2:
        raise DomainError("Amount must be positive with at most two decimal places")
    minor = number * 100
    if minor != minor.to_integral_value() or minor > 50_000_000:
        raise DomainError("Amount must be at most BDT 500,000")
    return int(minor)


def display_amount(poisha: int) -> str:
    return f"{Decimal(poisha) / 100:.2f}"


def quote_fee(amount_poisha: int, days: int) -> int:
    if days not in (7, 15, 30) or amount_poisha < 5_000 or amount_poisha > 1_000_000:
        raise DomainError("Demo e-Payment Credit requires BDT 50–10,000 and 7, 15, or 30 days")
    for upper, table in FEE_TABLE:
        if amount_poisha <= upper * 100:
            return table[days] * 100
    raise AssertionError("Unreachable")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, filename: str):
        self.filename = str(Path(filename))
        Path(self.filename).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.filename, timeout=20, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=20000")
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self):
        with self.db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript('''
                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL,
                    category TEXT, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL,
                    payload_hash TEXT NOT NULL, type TEXT NOT NULL,
                    description TEXT NOT NULL, result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ledger_entries (
                    event_id TEXT NOT NULL REFERENCES events(id),
                    account_id TEXT NOT NULL REFERENCES accounts(id),
                    delta_poisha INTEGER NOT NULL CHECK(delta_poisha != 0),
                    PRIMARY KEY(event_id,account_id)
                );
                CREATE TABLE IF NOT EXISTS loans (
                    id TEXT PRIMARY KEY, borrower_id TEXT NOT NULL REFERENCES accounts(id),
                    biller_id TEXT NOT NULL REFERENCES accounts(id),
                    category TEXT NOT NULL,
                    principal_poisha INTEGER NOT NULL,
                    fee_poisha INTEGER NOT NULL,
                    due_at TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('open','repaid')),
                    created_at TEXT NOT NULL, repaid_at TEXT
                );
                CREATE INDEX IF NOT EXISTS ledger_by_account ON ledger_entries(account_id);
            ''')
            if not db.execute("SELECT 1 FROM accounts LIMIT 1").fetchone():
                self.reset(db)

    def reset(self, conn: sqlite3.Connection | None = None):
        if conn is None:
            with self.db() as db:
                return self.reset(db)
        # Demo reset is deliberately destructive; never use on production data.
        conn.execute("BEGIN IMMEDIATE")
        try:
            for table in ("ledger_entries", "loans", "events", "accounts"):
                conn.execute(f"DELETE FROM {table}")
            for key, name, kind, category in [
                ("alice", "Ayesha Rahman · Demo", "customer", None),
                ("rahim", "Rahim Ahmed · Demo", "customer", None),
                ("shop", "Slickk Demo Store", "merchant", "shopping"),
                ("electric", "Electricity Biller · Demo", "merchant", "utility"),
                ("school", "Education Biller · Demo", "merchant", "education"),
                ("issuer", "Demo Issuance (not real money)", "system", None),
                ("lender", "Demo Credit Provider (not real lending)", "system", None),
            ]:
                conn.execute("INSERT INTO accounts VALUES(?,?,?,?,?)", (key, name, kind, category, utcnow()))
            self._record(conn, "seed:alice", {"seed": "alice"}, "seed", "Demo balance creation", [("issuer", -75_000_0), ("alice", 75_000_0)])
            self._record(conn, "seed:rahim", {"seed": "rahim"}, "seed", "Demo balance creation", [("issuer", -32_500_0), ("rahim", 32_500_0)])
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return {"ok": True, "mode": "SANDBOX_ONLY"}

    @staticmethod
    def _payload_hash(payload: dict) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _previous(self, conn: sqlite3.Connection, request_id: str, payload: dict):
        row = conn.execute("SELECT payload_hash, result_json FROM events WHERE request_id=?", (request_id,)).fetchone()
        if row is None:
            return None
        if row["payload_hash"] != self._payload_hash(payload):
            raise DomainError("Idempotency key reused for a different operation", 409)
        return json.loads(row["result_json"])

    def _record(self, conn, request_id, payload, kind, description, entries, extra=None):
        if not isinstance(request_id, str) or not (8 <= len(request_id) <= 128):
            raise DomainError("Request id must contain 8–128 characters")
        previous = self._previous(conn, request_id, payload)
        if previous is not None:
            return previous
        if sum(delta for _account, delta in entries) != 0 or not entries:
            raise DomainError("Unbalanced ledger event")
        if len(set(key for key, _delta in entries)) != len(entries):
            raise DomainError("Duplicate ledger account")
        event_id = uuid4().hex
        result = {"event_id": event_id, "type": kind, "description": description, "simulation": True}
        if extra:
            result.update(extra)
        conn.execute(
            "INSERT INTO events VALUES (?,?,?,?,?,?,?)",
            (event_id, request_id, self._payload_hash(payload), kind, description, json.dumps(result), utcnow()),
        )
        for account_id, delta in entries:
            conn.execute("INSERT INTO ledger_entries VALUES (?,?,?)", (event_id, account_id, delta))
        return result

    @staticmethod
    def _account(conn, account_id: str, expected_kind: str | None = None):
        row = conn.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
        if not row:
            raise DomainError("Account does not exist", 404)
        if expected_kind and row["kind"] != expected_kind:
            raise DomainError("Incorrect account type")
        return row

    @staticmethod
    def _balance(conn, account_id: str) -> int:
        return conn.execute("SELECT COALESCE(SUM(delta_poisha),0) FROM ledger_entries WHERE account_id=?", (account_id,)).fetchone()[0]

    def dashboard(self):
        with self.db() as db:
            accounts = [dict(row) for row in db.execute("SELECT * FROM accounts WHERE kind!='system' ORDER BY kind, id")]
            for account in accounts:
                account["balance_bdt"] = display_amount(self._balance(db, account["id"]))
            events = [dict(row) for row in db.execute("SELECT id, type, description, created_at FROM events WHERE type!='seed' ORDER BY created_at DESC, rowid DESC LIMIT 20")]
            loans = [dict(row) for row in db.execute("SELECT * FROM loans ORDER BY created_at DESC LIMIT 20")]
            for loan in loans:
                loan["principal_bdt"] = display_amount(loan.pop("principal_poisha"))
                loan["fee_bdt"] = display_amount(loan.pop("fee_poisha"))
                loan["total_due_bdt"] = display_amount(int(Decimal(loan["principal_bdt"]) * 100 + Decimal(loan["fee_bdt"]) * 100))
            return {"mode": "SANDBOX_ONLY", "currency": "BDT", "accounts": accounts, "events": events, "loans": loans}

    def transfer(self, sender_id: str, recipient_id: str, amount_bdt: Any, request_id: str, payment=False):
        amount = taka_to_poisha(amount_bdt)
        kind = "payment" if payment else "transfer"
        payload = {"kind": kind, "from": sender_id, "to": recipient_id, "amount_poisha": amount}
        if sender_id == recipient_id:
            raise DomainError("Sender and receiver must differ")
        if amount > 5_000_000:
            raise DomainError("Sandbox transaction limit BDT 50,000")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                previous = self._previous(db, request_id, payload)
                if previous:
                    db.commit()
                    return previous
                self._account(db, sender_id, "customer")
                receiver = self._account(db, recipient_id)
                if payment and receiver["kind"] != "merchant":
                    raise DomainError("Payments must be sent to a demo merchant")
                if not payment and receiver["kind"] not in ("customer", "merchant"):
                    raise DomainError("Invalid recipient type")
                if self._balance(db, sender_id) < amount:
                    raise DomainError("Insufficient demo balance", 409)
                result = self._record(db, request_id, payload, kind,
                                      f"{sender_id} → {recipient_id} · ৳{display_amount(amount)}",
                                      [(sender_id, -amount), (recipient_id, amount)],
                                      {"amount_bdt": display_amount(amount)})
                db.commit()
                return result
            except Exception:
                db.rollback()
                raise

    def credit_quote(self, borrower_id: str, biller_id: str, category: str, amount_bdt: Any, term_days: int):
        amount = taka_to_poisha(amount_bdt)
        fee = quote_fee(amount, term_days)
        if category not in APPROVED_DEMO_CATEGORIES:
            raise DomainError("Category not eligible for this simulated e-Payment Credit")
        with self.db() as db:
            self._account(db, borrower_id, "customer")
            merchant = self._account(db, biller_id, "merchant")
            if merchant["category"] != category:
                raise DomainError("Biller category does not match payment purpose")
        return {"borrower_id": borrower_id, "biller_id": biller_id, "category": category,
                "principal_bdt": display_amount(amount), "fee_bdt": display_amount(fee),
                "total_due_bdt": display_amount(amount+fee), "term_days": term_days,
                "fee_basis": "Bangladesh Bank 2026 e-Payment Credit schedule (maximum fee; illustrative only)",
                "decision": "NO_REAL_CREDIT_APPROVAL", "simulation": True}

    def credit_simulate(self, borrower_id: str, biller_id: str, category: str, amount_bdt: Any, term_days: int, request_id: str):
        quote = self.credit_quote(borrower_id, biller_id, category, amount_bdt, term_days)
        amount = taka_to_poisha(amount_bdt)
        fee = taka_to_poisha(quote["fee_bdt"])
        payload = {"kind": "simulated_credit", "borrower": borrower_id, "biller": biller_id,
                   "category": category, "principal_poisha": amount, "fee_poisha": fee, "term_days": term_days}
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                previous = self._previous(db, request_id, payload)
                if previous:
                    db.commit()
                    return previous
                if db.execute("SELECT 1 FROM loans WHERE borrower_id=? AND status='open'", (borrower_id,)).fetchone():
                    raise DomainError("Sandbox permits one open simulated credit per customer", 409)
                loan_id = uuid4().hex
                due_at = (datetime.now(timezone.utc) + timedelta(days=term_days)).isoformat(timespec="seconds")
                db.execute("INSERT INTO loans VALUES (?,?,?,?,?,?,?,?,?,?)",
                           (loan_id, borrower_id, biller_id, category, amount, fee, due_at, "open", utcnow(), None))
                # Direct to an eligible simulated biller, NEVER to customer wallet or cash.
                result = self._record(db, request_id, payload, "simulated_credit",
                                      f"Demo credit paid to {biller_id} · ৳{display_amount(amount)}",
                                      [("lender", -amount), (biller_id, amount)],
                                      {"loan_id": loan_id, "total_due_bdt": display_amount(amount + fee), "due_at": due_at})
                db.commit()
                return result
            except Exception:
                db.rollback()
                raise

    def repay(self, loan_id: str, borrower_id: str, request_id: str):
        payload = {"kind": "repayment", "loan_id": loan_id, "borrower_id": borrower_id}
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                previous = self._previous(db, request_id, payload)
                if previous:
                    db.commit()
                    return previous
                loan = db.execute("SELECT * FROM loans WHERE id=?", (loan_id,)).fetchone()
                if not loan:
                    raise DomainError("Demo loan not found", 404)
                if loan["borrower_id"] != borrower_id:
                    raise DomainError("This demo customer is not the borrower", 403)
                if loan["status"] != "open":
                    raise DomainError("Loan already repaid", 409)
                total = loan["principal_poisha"] + loan["fee_poisha"]
                if self._balance(db, borrower_id) < total:
                    raise DomainError("Insufficient demo balance for full repayment", 409)
                result = self._record(db, request_id, payload, "repayment",
                                      f"Demo credit repayment · ৳{display_amount(total)}",
                                      [(borrower_id, -total), ("lender", total)],
                                      {"loan_id": loan_id, "amount_bdt": display_amount(total)})
                db.execute("UPDATE loans SET status='repaid', repaid_at=? WHERE id=?", (utcnow(), loan_id))
                db.commit()
                return result
            except Exception:
                db.rollback()
                raise

    def ledger_audit(self):
        with self.db() as db:
            invalid = [dict(x) for x in db.execute("SELECT event_id, SUM(delta_poisha) AS imbalance FROM ledger_entries GROUP BY event_id HAVING SUM(delta_poisha) != 0")]
            balance_total = db.execute("SELECT COALESCE(SUM(delta_poisha),0) FROM ledger_entries").fetchone()[0]
            events_count = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            return {"balanced": not invalid and balance_total == 0, "event_count": events_count,
                    "total_poisha": balance_total, "unbalanced_events": invalid, "simulation": True}
