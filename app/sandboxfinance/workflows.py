"""Two-party sandbox customer transfers and controlled agent cash operations.

No physical cash is actually received or disbursed. Cash inventory is an
operator-provided synthetic number and the user confirmation token is only a
local simulation of a separate customer authentication channel. No real SMS,
PIN, device enrollment, financial authorization or customer funds are involved.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
from typing import Literal

from .identity import SyntheticRegistry, IdentityError, synthetic_confirmation_token, masked_phone
from .ledger import SandboxLedger, LedgerError, Posting, Receipt, DuplicateReference
from .pricing import PilotPricing, initial_pilot, Quote, PriceError


class WorkflowError(Exception):
    pass


class ConsentError(WorkflowError):
    pass


class LiquidityError(WorkflowError):
    pass


class StateConflict(WorkflowError):
    pass


TERMINAL = frozenset({"completed", "cancelled", "expired", "disputed"})


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _ts(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def _new_reference(prefix: str) -> str:
    return f"sim_{prefix}_{secrets.token_hex(12)}"


def _digest(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class CashRequest:
    request_id: str
    direction: Literal["cash_in", "cash_out"]
    customer_id: str
    agent_id: str
    principal_poisha: int
    fee_poisha: int
    tax_poisha: int
    commission_poisha: int
    state: str
    created_at: str
    expires_at: str
    event_id: str | None = None
    simulation: bool = True


@dataclass(frozen=True)
class CashRequestConfirmation:
    """Synthetic customer-side delivery result. Never show the token to an agent UI."""
    request: CashRequest
    customer_token: str
    warning: str = "LOCAL TEST TOKEN ONLY; not a real SMS or payment PIN"


CASH_SCHEMA = """
CREATE TABLE IF NOT EXISTS sim_agent_cash (
 agent_id TEXT PRIMARY KEY, cash_poisha INTEGER NOT NULL DEFAULT 0 CHECK(cash_poisha>=0),
 cash_limit_poisha INTEGER NOT NULL DEFAULT 0 CHECK(cash_limit_poisha>=0),
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sim_cash_requests (
 request_id TEXT PRIMARY KEY,
 direction TEXT NOT NULL CHECK(direction IN ('cash_in','cash_out')),
 customer_id TEXT NOT NULL, agent_id TEXT NOT NULL,
 principal_poisha INTEGER NOT NULL CHECK(principal_poisha>0),
 fee_poisha INTEGER NOT NULL CHECK(fee_poisha>=0),
 tax_poisha INTEGER NOT NULL CHECK(tax_poisha>=0),
 commission_poisha INTEGER NOT NULL CHECK(commission_poisha>=0),
 state TEXT NOT NULL CHECK(state IN ('awaiting_cash','reserved','completed','cancelled','expired','disputed')),
 token_digest TEXT NOT NULL,
 request_digest TEXT NOT NULL,
 expires_at TEXT NOT NULL,
 created_at TEXT NOT NULL,
 settled_event_id TEXT,
 reserved_event_id TEXT
);
CREATE TABLE IF NOT EXISTS sim_cash_audit (
 entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
 request_id TEXT NOT NULL REFERENCES sim_cash_requests(request_id),
 old_state TEXT, new_state TEXT NOT NULL, reason TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS sim_cash_audit_immutable_update BEFORE UPDATE ON sim_cash_audit
 BEGIN SELECT RAISE(ABORT,'immutable cash audit events'); END;
CREATE TRIGGER IF NOT EXISTS sim_cash_audit_immutable_delete BEFORE DELETE ON sim_cash_audit
 BEGIN SELECT RAISE(ABORT,'immutable cash audit events'); END;
"""


class CashDesk:
    """Local single-process agent cash sandbox; no external network calls.

    A separate SQLite state machine tracks the fictional physical-cash assertion.
    The shared ledger database stores all electronic money movements atomically.
    The module uses the *same SQLite file* for state changes, so a single DB
    transaction can update cash inventory and journal postings together.
    """

    def __init__(self, ledger: SandboxLedger, registry: SyntheticRegistry,
                 pricing: PilotPricing | None = None):
        self.ledger = ledger
        self.registry = registry
        self.pricing = pricing or initial_pilot()
        self._lock = ledger._lock
        with self._lock, ledger._connect() as db:
            db.executescript(CASH_SCHEMA)

    def _party(self, party_id: str, role: str):
        p = self.registry.lookup(party_id, required_role=role)
        if p.status != "sandbox_verified":
            raise ConsentError("Synthetic actor not approved")
        return p

    def register_agent_cash(self, agent_id: str, *, reported_cash_poisha: int,
                            limit_poisha: int) -> None:
        """Operator-provided fictional cash inventory; *not a physical cash audit*."""
        self._party(agent_id, "agent")
        if (not all(isinstance(x, int) and not isinstance(x, bool) for x in
                    (reported_cash_poisha, limit_poisha))
                or min(reported_cash_poisha, limit_poisha) < 0
                or reported_cash_poisha > limit_poisha):
            raise LiquidityError("Invalid simulated cash inventory")
        with self._lock, self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO sim_agent_cash VALUES (?,?,?,?) ON CONFLICT(agent_id) "
                       "DO UPDATE SET cash_poisha=excluded.cash_poisha, "
                       "cash_limit_poisha=excluded.cash_limit_poisha,updated_at=excluded.updated_at",
                       (agent_id, reported_cash_poisha, limit_poisha, _ts(_utc())))
            db.commit()

    def cash_available(self, agent_id: str) -> int:
        with self.ledger._connect() as db:
            row = db.execute("SELECT cash_poisha FROM sim_agent_cash WHERE agent_id=?", (agent_id,)).fetchone()
            if row is None:
                raise LiquidityError("Agent synthetic cash not declared")
            return row[0]

    def _new_request(self, direction: str, customer_id: str, agent_id: str,
                     principal: int, expires_seconds: int) -> CashRequestConfirmation:
        self._party(customer_id, "customer")
        self._party(agent_id, "agent")
        if not isinstance(expires_seconds, int) or not 60 <= expires_seconds <= 1800:
            raise WorkflowError("Simulation consent expiry must be 60–1800 seconds")
        quote = self.pricing.quote(direction, principal)
        request_id = _new_reference(direction)
        token, token_hash = synthetic_confirmation_token()
        now = _utc()
        state = "awaiting_cash" if direction == "cash_in" else "reserved"
        expires = now + timedelta(seconds=expires_seconds)
        row = CashRequest(request_id, direction, customer_id, agent_id,
                          quote.principal, quote.customer_fee, quote.tax,
                          quote.agent_commission, state, _ts(now), _ts(expires))
        escrow = "sim_escrow_" + request_id.split("_")[-1]
        with self._lock:
            if direction == "cash_out":
                if self.cash_available(agent_id) < principal:
                    raise LiquidityError("Insufficient reported fictional physical cash")
                self.ledger.create_account(escrow, request_id, "escrow")
            with self.ledger._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                try:
                    if direction == "cash_out":
                        # Reserve and persist the state machine in ONE SQL transaction.
                        self.ledger.post_in_transaction(
                            db, operation="cashout_reserve",
                            idempotency_key=request_id + ":reserve",
                            postings=[Posting("sim_wallet_" + customer_id[4:], "debit",
                                              principal + quote.customer_fee + quote.tax),
                                      Posting(escrow, "credit", principal + quote.customer_fee + quote.tax)])
                    db.execute("INSERT INTO sim_cash_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (request_id, direction, customer_id, agent_id, principal,
                                quote.customer_fee, quote.tax, quote.agent_commission, state,
                                token_hash, _digest({"customer":customer_id,"agent":agent_id,
                                                     "principal":principal,"direction":direction}),
                                _ts(expires), _ts(now), None,
                                (request_id + ":reserve") if direction == "cash_out" else None))
                    db.execute("INSERT INTO sim_cash_audit(request_id,old_state,new_state,reason,created_at) "
                               "VALUES(?,?,?,?,?)", (request_id, None, state, "synthetic_request", _ts(now)))
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
        return CashRequestConfirmation(row, token)

    def request_cash_in(self, customer_id: str, agent_id: str, principal: int,
                        *, expires_seconds: int = 300) -> CashRequestConfirmation:
        return self._new_request("cash_in", customer_id, agent_id, principal, expires_seconds)

    def request_cash_out(self, customer_id: str, agent_id: str, principal: int,
                         *, expires_seconds: int = 300) -> CashRequestConfirmation:
        return self._new_request("cash_out", customer_id, agent_id, principal, expires_seconds)

    def _load(self, db: sqlite3.Connection, request_id: str):
        row = db.execute("SELECT * FROM sim_cash_requests WHERE request_id=?", (request_id,)).fetchone()
        if row is None:
            raise WorkflowError("Cash request not found")
        return row

    def status(self, request_id: str) -> CashRequest:
        with self.ledger._connect() as db:
            r = self._load(db, request_id)
            return CashRequest(r["request_id"], r["direction"], r["customer_id"], r["agent_id"],
                               r["principal_poisha"], r["fee_poisha"], r["tax_poisha"],
                               r["commission_poisha"], r["state"], r["created_at"],
                               r["expires_at"], r["settled_event_id"])

    def _transition(self, db: sqlite3.Connection, r: sqlite3.Row, new_state: str, reason: str,
                    event_id: str | None = None) -> None:
        count = db.execute("UPDATE sim_cash_requests SET state=?,settled_event_id=COALESCE(?,settled_event_id) "
                           "WHERE request_id=? AND state=?",
                           (new_state, event_id, r["request_id"], r["state"])).rowcount
        if count != 1:
            raise StateConflict("Cash request was concurrently changed")
        db.execute("INSERT INTO sim_cash_audit(request_id,old_state,new_state,reason,created_at) VALUES(?,?,?,?,?)",
                   (r["request_id"], r["state"], new_state, reason, _ts(_utc())))

    def confirm(self, request_id: str, *, agent_id: str, customer_token: str,
                cash_handover_confirmed: bool) -> CashRequest:
        """Complete a *simulated* cash handover with independently supplied customer proof.

        For a real product, never reuse this token channel; integrate approved
        customer authentication, agent cash-control and controlled cash handover.
        """
        self._party(agent_id, "agent")
        if not cash_handover_confirmed or not isinstance(cash_handover_confirmed, bool):
            raise ConsentError("Explicit simulated physical handover is required")
        if not isinstance(customer_token, str) or len(customer_token) > 256:
            raise ConsentError("Invalid consent token")
        with self._lock, self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                r = self._load(db, request_id)
                if r["agent_id"] != agent_id:
                    raise ConsentError("Request belongs to another agent")
                self._party(r["customer_id"], "customer")
                if r["state"] in TERMINAL:
                    raise StateConflict("Terminal cash request is immutable")
                if _utc() > datetime.fromisoformat(r["expires_at"]):
                    raise StateConflict("Cash request expired; cancel reservation")
                if not hmac.compare_digest(hashlib.sha256(customer_token.encode()).hexdigest(), r["token_digest"]):
                    raise ConsentError("Customer did not authorize this sandbox handover")
                if r["direction"] == "cash_in":
                    agent_float = "sim_float_" + agent_id[4:]
                    if self.ledger.account(agent_float).balance_poisha < r["principal_poisha"]:
                        raise LiquidityError("Insufficient electronic agent float")
                    cash_row = db.execute("SELECT * FROM sim_agent_cash WHERE agent_id=?", (agent_id,)).fetchone()
                    if cash_row is None or cash_row["cash_poisha"] + r["principal_poisha"] > cash_row["cash_limit_poisha"]:
                        raise LiquidityError("Synthetic cash capacity exhausted")
                    lines = [Posting(agent_float,"debit",r["principal_poisha"]),
                             Posting("sim_wallet_" + r["customer_id"][4:],"credit",r["principal_poisha"])]
                    if r["commission_poisha"]:
                        lines += [Posting("sim_platform_treasury","debit",r["commission_poisha"]),
                                  Posting("sim_commission_" + agent_id[4:],"credit",r["commission_poisha"])]
                    change_cash = +r["principal_poisha"]
                else:
                    cash_row = db.execute("SELECT * FROM sim_agent_cash WHERE agent_id=?", (agent_id,)).fetchone()
                    if cash_row is None or cash_row["cash_poisha"] < r["principal_poisha"]:
                        raise LiquidityError("No simulated agent cash available")
                    escrow = "sim_escrow_" + request_id.split("_")[-1]
                    total = r["principal_poisha"] + r["fee_poisha"] + r["tax_poisha"]
                    lines = [Posting(escrow,"debit",total),
                             Posting("sim_float_" + agent_id[4:],"credit",r["principal_poisha"])]
                    if r["fee_poisha"]:
                        lines.append(Posting("sim_platform_revenue","credit",r["fee_poisha"]))
                    if r["tax_poisha"]:
                        lines.append(Posting("sim_platform_treasury","credit",r["tax_poisha"]))
                    if r["commission_poisha"]:
                        lines += [Posting("sim_platform_revenue","debit",r["commission_poisha"]),
                                  Posting("sim_commission_" + agent_id[4:],"credit",r["commission_poisha"])]
                    change_cash = -r["principal_poisha"]
                # The journal, agent cash inventory, and workflow transition are
                # committed or rolled back as ONE transaction in this SQLite file.
                receipt = self.ledger.post_in_transaction(
                    db, operation=r["direction"] + "_finalize",
                    idempotency_key=request_id + ":finalize", postings=lines)
                current = self._load(db, request_id)
                if current["state"] != r["state"]:
                    raise StateConflict("Cash request changed after ledger event")
                db.execute("UPDATE sim_agent_cash SET cash_poisha=cash_poisha+?,updated_at=? WHERE agent_id=?",
                           (change_cash, _ts(_utc()), agent_id))
                self._transition(db, r, "completed", "sandbox_customer_and_agent_confirmed", receipt.event_id)
                db.commit()
                return self.status(request_id)
            except Exception:
                db.rollback()
                raise

    def cancel(self, request_id: str, *, actor_id: str, reason: str = "cancelled") -> CashRequest:
        if not 1 <= len(reason) <= 100:
            raise WorkflowError("Invalid cancellation reason")
        with self._lock, self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                r = self._load(db, request_id)
                if actor_id not in (r["agent_id"], r["customer_id"]):
                    raise ConsentError("Unauthorized cancellation actor")
                if r["state"] in TERMINAL:
                    raise StateConflict("Terminal cash request cannot be cancelled")
                if r["direction"] == "cash_out":
                    escrow = "sim_escrow_" + request_id.split("_")[-1]
                    amount = r["principal_poisha"] + r["fee_poisha"] + r["tax_poisha"]
                    self.ledger.post_in_transaction(
                        db, operation="cashout_reservation_cancel",
                        idempotency_key=request_id + ":refund_reservation",
                        postings=[Posting(escrow, "debit", amount),
                                  Posting("sim_wallet_" + r["customer_id"][4:], "credit", amount)])
                self._transition(db, r, "cancelled", reason)
                db.commit()
                return self.status(request_id)
            except Exception:
                db.rollback()
                raise

    def audit(self, request_id: str) -> tuple[dict, ...]:
        with self.ledger._connect() as db:
            self._load(db, request_id)
            events = db.execute("SELECT old_state,new_state,reason,created_at FROM sim_cash_audit "
                                "WHERE request_id=? ORDER BY entry_id", (request_id,)).fetchall()
            return tuple(dict(e) for e in events)


class CustomerTransfers:
    """Safe customer-to-customer fictitious transfer, with versioned price quote."""

    def __init__(self, ledger: SandboxLedger, registry: SyntheticRegistry,
                 pricing: PilotPricing | None = None):
        self.ledger = ledger
        self.registry = registry
        self.pricing = pricing or initial_pilot()

    def quote(self, amount: int) -> Quote:
        return self.pricing.quote("customer_transfer", amount)

    def recipient_lookup(self, phone: str) -> dict[str, str | bool]:
        recipient = self.registry.by_phone(phone)
        if recipient.role != "customer" or recipient.status != "sandbox_verified":
            raise ConsentError("Recipient unavailable")
        return recipient.public()

    def send(self, *, sender_id: str, recipient_id: str, principal: int,
             reference: str, customer_confirmed: bool) -> Receipt:
        if not customer_confirmed or not isinstance(customer_confirmed, bool):
            raise ConsentError("Explicit sender confirmation required")
        sender = self.registry.lookup(sender_id, required_role="customer")
        recipient = self.registry.lookup(recipient_id, required_role="customer")
        if sender_id == recipient_id:
            raise WorkflowError("Cannot send to the same account")
        if sender.status != "sandbox_verified" or recipient.status != "sandbox_verified":
            raise ConsentError("Sandbox participant not approved")
        quote = self.quote(principal)
        lines = [Posting("sim_wallet_" + sender_id[4:], "debit", quote.customer_total_debit),
                 Posting("sim_wallet_" + recipient_id[4:], "credit", principal)]
        if quote.customer_fee:
            lines.append(Posting("sim_platform_revenue", "credit", quote.customer_fee))
        if quote.tax:
            lines.append(Posting("sim_platform_treasury", "credit", quote.tax))
        return self.ledger.post(operation="customer_transfer", idempotency_key=reference,
                                postings=lines)


def prepare_synthetic_system(ledger: SandboxLedger, registry: SyntheticRegistry) -> None:
    """Create sandbox accounts once; issue no money and grant no real privileges."""
    ledger.create_account("sim_issuer", "sim_system", "synthetic_issuer")
    ledger.create_account("sim_platform_treasury", "sim_system", "platform_treasury")
    ledger.create_account("sim_platform_revenue", "sim_system", "platform_revenue")
    for party in registry.parties.values():
        if party.status != "sandbox_verified":
            continue
        suffix = party.party_id[4:]
        if party.role == "customer":
            ledger.create_account("sim_wallet_" + suffix, party.party_id, "customer")
        elif party.role == "agent":
            ledger.create_account("sim_float_" + suffix, party.party_id, "agent_float")
            ledger.create_account("sim_commission_" + suffix, party.party_id, "agent_commission")
        elif party.role == "merchant":
            ledger.create_account("sim_merchant_" + suffix, party.party_id, "merchant")
