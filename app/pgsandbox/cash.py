"""Agent cash-in and cash-out *simulations* with immutable double-entry evidence.

Cash is a synthetic inventory assertion. No agent may use a customer PIN. The
customer's separate confirmation token is generated locally only for testing.
The service requires two independent role assertions and reserves electronic
value before any fictional cash-out handover can be recorded.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
import secrets
from sqlalchemy import select, insert, update
from sqlalchemy.engine import Connection
from .schema import (accounts, requests, cash_inventory, cash_history, journals)
from .posting import LedgerService, LedgerEntry, JournalReceipt, digest
from .controls import ActorAuthorization, VelocityController, DEFAULT_LIMITS
from .money import minor, Rate, minor_to_bdt
from .guard import sim_id, event_key
from .store import utc_now
from .workflow_policy import require_op
from .errors import (InvalidValue, Conflict, StateError, MissingRecord, AuthorizationError,
                     LiquidityError, InvariantError, RateLimit)


@dataclass(frozen=True)
class CashQuote:
    direction: str
    principal: int
    customer_fee: int
    commission: int
    tax: int
    customer_total: int
    version: str
    simulation: bool = True

    def public(self) -> dict[str, object]:
        return {"direction": self.direction, "principal_bdt": minor_to_bdt(self.principal),
                "customer_fee_bdt": minor_to_bdt(self.customer_fee),
                "agent_commission_bdt": minor_to_bdt(self.commission),
                "tax_bdt": minor_to_bdt(self.tax),
                "customer_total_bdt": minor_to_bdt(self.customer_total),
                "version": self.version, "simulation": True}


@dataclass(frozen=True)
class CashRequestResult:
    request_id: str
    direction: str
    state: str
    customer_account: str
    agent_account: str
    principal_poisha: int
    expires_at: str
    journal_event: str | None
    simulation: bool = True


@dataclass(frozen=True)
class SyntheticCustomerApproval:
    request: CashRequestResult
    token: str
    warning: str = "Synthetic laboratory token: never deliver this to an agent"


@dataclass(frozen=True)
class CashInventory:
    agent_account: str
    cash_poisha: int
    ceiling_poisha: int
    simulation: bool = True


class SandboxCashDesk:
    """All postings, request states, and inventory mutations use one DB tx."""

    def __init__(self, ledger: LedgerService, *, platform_revenue: str,
                 platform_treasury: str, agent_commission_lookup: dict[str, str],
                 cashout_fee: Rate | None = None, cashout_commission: Rate | None = None,
                 cashin_commission: Rate | None = None):
        self.ledger = ledger
        self.auth = ActorAuthorization(ledger)
        self.velocity = VelocityController(ledger)
        self.revenue = sim_id(platform_revenue, "platform revenue")
        self.treasury = sim_id(platform_treasury, "treasury")
        self.agent_commission_lookup = dict(agent_commission_lookup)
        self.cashout_fee = cashout_fee or Rate("cashout_fee", 10_990)
        self.cashout_commission = cashout_commission or Rate("cashout_commission", 5_500)
        self.cashin_commission = cashin_commission or Rate("cashin_commission", 1_500)

    def _agent_commission(self, agent_account: str) -> str:
        sim_id(agent_account, "agent")
        try:
            return sim_id(self.agent_commission_lookup[agent_account], "commission account")
        except KeyError as exc:
            raise MissingRecord("Agent commission account not onboarded") from exc

    def quote(self, direction: str, principal_poisha: int) -> CashQuote:
        minor(principal_poisha, positive=True)
        if direction not in ("cash_in", "cash_out"):
            raise InvalidValue("Unknown cash operation")
        if direction == "cash_out":
            fee = self.cashout_fee.fee(principal_poisha)
            commission = self.cashout_commission.fee(principal_poisha)
            if commission > fee:
                raise InvariantError("Pilot cash-out commission exceeds collected fee")
            return CashQuote(direction, principal_poisha, fee, commission, 0,
                             principal_poisha + fee, "pilot-2026-11-03-v1")
        return CashQuote(direction, principal_poisha, 0,
                         self.cashin_commission.fee(principal_poisha), 0,
                         principal_poisha, "pilot-2026-11-03-v1")

    def set_agent_cash(self, *, agent_actor: str, agent_account: str,
                       cash_poisha: int, ceiling_poisha: int) -> CashInventory:
        minor(cash_poisha)
        minor(ceiling_poisha)
        if cash_poisha < 0 or ceiling_poisha < cash_poisha:
            raise InvalidValue("Cash inventory exceeds declared ceiling")
        with self.ledger.store.transaction() as db:
            self.auth.require_agent_float(db, agent_account, agent_actor)
            current = db.execute(select(cash_inventory).where(cash_inventory.c.agent_account == agent_account).with_for_update()).mappings().first()
            values = dict(cash=cash_poisha, cash_ceiling=ceiling_poisha, updated_at=utc_now())
            if current:
                db.execute(update(cash_inventory).where(cash_inventory.c.agent_account == agent_account).values(**values))
            else:
                db.execute(insert(cash_inventory).values(agent_account=agent_account, **values))
            return CashInventory(agent_account, cash_poisha, ceiling_poisha)

    def inventory(self, agent_account: str) -> CashInventory:
        sim_id(agent_account, "agent")
        with self.ledger.store.engine.connect() as db:
            row = db.execute(select(cash_inventory).where(cash_inventory.c.agent_account == agent_account)).mappings().first()
            if not row:
                raise MissingRecord("Agent synthetic cash inventory not configured")
            return CashInventory(agent_account, row["cash"], row["cash_ceiling"])

    def _request(self, db: Connection, request_id: str, *, lock: bool = False):
        sim_id(request_id, "cash request")
        q = select(requests).where(requests.c.request_id == request_id)
        if lock:
            q = q.with_for_update()
        row = db.execute(q).mappings().first()
        if row is None:
            raise MissingRecord("Cash request not found")
        return row

    def _view(self, row) -> CashRequestResult:
        return CashRequestResult(row["request_id"], row["kind"], row["state"],
                                 row["customer_account"], row["agent_account"],
                                 row["amount"], row["expires_at"], row["last_event"])

    def request(self, request_id: str) -> CashRequestResult:
        with self.ledger.store.engine.connect() as db:
            return self._view(self._request(db, request_id))

    def _transition(self, db: Connection, row, new_state: str, reason: str,
                    *, event_id: str | None = None) -> None:
        require_op(row["kind"], row["state"], new_state)
        db.execute(update(requests).where(requests.c.request_id == row["request_id"])
                   .values(state=new_state, last_event=event_id or row["last_event"]))
        db.execute(insert(cash_history).values(request_id=row["request_id"],
                   old_state=row["state"], new_state=new_state,
                   reason=reason, recorded_at=utc_now()))

    def _token_hash(self, request_id: str, token: str) -> str:
        return sha256((request_id + ":" + token).encode()).hexdigest()

    def _assert_token(self, row, token: str) -> None:
        if not isinstance(token, str) or not 16 <= len(token) <= 128:
            raise AuthorizationError("Invalid synthetic customer confirmation")
        expected = self._token_hash(row["request_id"], token)
        if not hmac.compare_digest(expected, row["nonce_digest"]):
            raise AuthorizationError("Synthetic confirmation mismatch")

    def create(self, *, agent_actor: str, agent_account: str, customer_account: str,
               customer_actor: str | None = None, request_id: str, direction: str, principal: int,
               ttl_seconds: int = 300) -> SyntheticCustomerApproval:
        sim_id(request_id, "request")
        sim_id(customer_account, "customer")
        q = self.quote(direction, principal)
        if not 60 <= ttl_seconds <= 900:
            raise InvalidValue("Cash request TTL outside pilot policy")
        commission_account = self._agent_commission(agent_account)
        now = datetime.now(timezone.utc)
        expires = (now + timedelta(seconds=ttl_seconds)).isoformat(timespec="microseconds")
        token = secrets.token_urlsafe(32)
        nonce_digest = self._token_hash(request_id, token)
        input_digest = digest({"id": request_id, "agent": agent_account,
                               "customer": customer_account, "kind": direction,
                               "amount": principal, "fee": q.customer_fee,
                               "commission": q.commission, "ttl": ttl_seconds})
        escrow_id = f"sim_escrow_{sha256(request_id.encode()).hexdigest()[:30]}" if direction == "cash_out" else None
        with self.ledger.store.transaction() as db:
            self.auth.require_agent_float(db, agent_account, agent_actor)
            if direction == "cash_out":
                if customer_actor is None:
                    raise AuthorizationError("Customer must initiate cash-out")
                self.auth.require_customer(db, customer_account, customer_actor)
            customer = db.execute(select(accounts).where(accounts.c.account_id == customer_account)).mappings().first()
            if customer is None or customer["kind"] != "customer" or customer["frozen"]:
                raise AuthorizationError("Customer account not eligible")
            old = db.execute(select(requests).where(requests.c.request_id == request_id).with_for_update()).mappings().first()
            if old:
                if old["request_digest"] != input_digest:
                    raise Conflict("Cash request already used with different details")
                # Original one-time synthetic token cannot be retrieved securely.
                # Never fabricate a new approval for an existing request.
                raise Conflict("Existing request: use customer-side original token")
            inv = db.execute(select(cash_inventory).where(cash_inventory.c.agent_account == agent_account).with_for_update()).mappings().first()
            if inv is None:
                raise MissingRecord("Agent must declare synthetic cash inventory")
            if direction == "cash_out" and inv["cash"] < principal:
                raise LiquidityError("Agent lacks fictional physical cash")
            if direction == "cash_in" and inv["cash"] + principal > inv["cash_ceiling"]:
                raise LiquidityError("Agent's declared cash storage ceiling exceeded")
            if direction == "cash_out":
                db.execute(insert(accounts).values(account_id=escrow_id, owner_id="sim_owner_escrow",
                           kind="escrow", balance=0, frozen=False, version=0,
                           created_at=utc_now()))
            db.execute(insert(requests).values(request_id=request_id,
                       customer_account=customer_account, agent_account=agent_account,
                       agent_commission_account=commission_account, revenue_account=self.revenue,
                       escrow_account=escrow_id, kind=direction, amount=principal,
                       fee=q.customer_fee, commission=q.commission, tax=q.tax,
                       state="awaiting" if direction == "cash_in" else "reserved",
                       nonce_digest=nonce_digest, request_digest=input_digest,
                       expires_at=expires, created_at=now.isoformat(timespec="microseconds")))
            if direction == "cash_out":
                r = self.ledger.post_in_transaction(db, "cashout_reserve", "reserve:"+request_id,
                    [LedgerEntry(customer_account, "debit", q.customer_total),
                     LedgerEntry(escrow_id, "credit", q.customer_total)], actor=agent_actor)
                db.execute(update(requests).where(requests.c.request_id == request_id).values(last_event=r.event_id))
            db.execute(insert(cash_history).values(request_id=request_id, old_state=None,
                       new_state="awaiting" if direction == "cash_in" else "reserved",
                       reason="customer_confirmation_pending", recorded_at=utc_now()))
            view = self._view(self._request(db, request_id))
            return SyntheticCustomerApproval(view, token)

    def confirm_cashin(self, *, customer_actor: str, request_id: str,
                       customer_token: str) -> CashRequestResult:
        with self.ledger.store.transaction() as db:
            row = self._request(db, request_id, lock=True)
            if row["kind"] != "cash_in":
                raise StateError("Not a cash-in request")
            self.auth.require_customer(db, row["customer_account"], customer_actor)
            self._assert_token(row, customer_token)
            if row["state"] == "completed":
                return self._view(row)
            if row["state"] != "awaiting":
                raise StateError("Cash-in request cannot be confirmed")
            self._ensure_unexpired(row)
            inv = db.execute(select(cash_inventory).where(cash_inventory.c.agent_account == row["agent_account"]).with_for_update()).mappings().one()
            if inv["cash"] + row["amount"] > inv["cash_ceiling"]:
                raise LiquidityError("Cash inventory ceiling changed")
            lines = [LedgerEntry(row["agent_account"], "debit", row["amount"]),
                     LedgerEntry(row["customer_account"], "credit", row["amount"])]
            if row["commission"]:
                lines += [LedgerEntry(self.treasury, "debit", row["commission"]),
                          LedgerEntry(row["agent_commission_account"], "credit", row["commission"])]
            receipt = self.ledger.post_in_transaction(db, "cashin_complete",
                "cashin:" + request_id, lines, actor=customer_actor)
            db.execute(update(cash_inventory).where(cash_inventory.c.agent_account == row["agent_account"])
                       .values(cash=inv["cash"] + row["amount"], updated_at=utc_now()))
            self._transition(db, row, "completed", "synthetic_customer_confirmed", event_id=receipt.event_id)
            return self._view(self._request(db, request_id))

    def approve_cashout(self, *, customer_actor: str, request_id: str,
                        customer_token: str) -> CashRequestResult:
        with self.ledger.store.transaction() as db:
            row = self._request(db, request_id, lock=True)
            if row["kind"] != "cash_out":
                raise StateError("Not a cash-out request")
            self.auth.require_customer(db, row["customer_account"], customer_actor)
            self._assert_token(row, customer_token)
            if row["state"] == "customer_confirmed":
                return self._view(row)
            if row["state"] != "reserved":
                raise StateError("Cash-out is not awaiting customer approval")
            self._ensure_unexpired(row)
            self._transition(db, row, "customer_confirmed", "synthetic_customer_approval")
            return self._view(self._request(db, request_id))

    def complete_cashout(self, *, agent_actor: str, request_id: str,
                         handover_reference: str) -> CashRequestResult:
        event_key(handover_reference)
        with self.ledger.store.transaction() as db:
            row = self._request(db, request_id, lock=True)
            if row["kind"] != "cash_out":
                raise StateError("Not a cash-out request")
            self.auth.require_agent_float(db, row["agent_account"], agent_actor)
            proof_digest = sha256(handover_reference.encode()).hexdigest()
            if row["state"] == "completed":
                if row["handover_digest"] != proof_digest:
                    raise Conflict("Completed handover cannot accept another attestation")
                return self._view(row)
            if row["state"] != "customer_confirmed":
                raise StateError("Cash-out requires independent customer confirmation")
            self._ensure_unexpired(row)
            inv = db.execute(select(cash_inventory).where(cash_inventory.c.agent_account == row["agent_account"]).with_for_update()).mappings().one()
            if inv["cash"] < row["amount"]:
                raise LiquidityError("Not enough fictional physical cash")
            fee_after_commission = row["fee"] - row["commission"]
            if fee_after_commission < 0:
                raise InvariantError("Commission exceeds disclosed fee")
            total = row["amount"] + row["fee"] + row["tax"]
            lines = [LedgerEntry(row["escrow_account"], "debit", total),
                     LedgerEntry(row["agent_account"], "credit", row["amount"])]
            if row["commission"]:
                lines.append(LedgerEntry(row["agent_commission_account"], "credit", row["commission"]))
            if fee_after_commission:
                lines.append(LedgerEntry(row["revenue_account"], "credit", fee_after_commission))
            if row["tax"]:
                # Pilot currently has zero tax; nonzero tax requires distinct liability account.
                raise InvariantError("Tax liability account not configured")
            already_used = db.execute(select(requests.c.request_id).where(
                requests.c.handover_digest == proof_digest)).scalar_one_or_none()
            if already_used is not None:
                raise Conflict("Attestation reference already used by another handover")
            receipt = self.ledger.post_in_transaction(db, "cashout_complete",
                "cashout:" + request_id, lines, actor=agent_actor)
            db.execute(update(requests).where(requests.c.request_id == request_id)
                       .values(handover_digest=proof_digest))
            db.execute(update(cash_inventory).where(cash_inventory.c.agent_account == row["agent_account"])
                       .values(cash=inv["cash"] - row["amount"], updated_at=utc_now()))
            self._transition(db, row, "completed", "synthetic_cash_handover_attested", event_id=receipt.event_id)
            return self._view(self._request(db, request_id))

    def cancel(self, *, actor: str, request_id: str, reason: str) -> CashRequestResult:
        sim_id(actor, "actor")
        if reason not in ("customer_declined", "agent_declined", "timeout", "supervisor_cancel"):
            raise InvalidValue("Unsupported cancellation reason")
        with self.ledger.store.transaction() as db:
            row = self._request(db, request_id, lock=True)
            owner = db.execute(select(accounts.c.owner_id).where(accounts.c.account_id == row["customer_account"])).scalar_one()
            agent = db.execute(select(accounts.c.owner_id).where(accounts.c.account_id == row["agent_account"])).scalar_one()
            if actor not in (owner, agent, "sim_operator_admin"):
                raise AuthorizationError("Cannot cancel someone else's request")
            if row["state"] == "cancelled":
                return self._view(row)
            if row["state"] == "completed":
                raise StateError("Completed cash movement needs separate dispute/reversal")
            if row["state"] == "customer_confirmed":
                # Physical handover might already have occurred. Do not silently
                # return the electronic reservation after dual approval.
                raise StateError("After customer approval, use dispute review; do not auto-release")
            if row["state"] not in ("awaiting", "reserved"):
                raise StateError("Cannot cancel terminal request")
            reversal_event = None
            if row["kind"] == "cash_out":
                total = row["amount"] + row["fee"] + row["tax"]
                receipt = self.ledger.post_in_transaction(db, "cashout_release",
                    "release:" + request_id,
                    [LedgerEntry(row["escrow_account"], "debit", total),
                     LedgerEntry(row["customer_account"], "credit", total)], actor=actor)
                reversal_event = receipt.event_id
            self._transition(db, row, "cancelled", reason, event_id=reversal_event)
            return self._view(self._request(db, request_id))

    def _ensure_unexpired(self, row) -> None:
        if datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
            raise StateError("Cash request expired; requires release/reconciliation")

    def expire(self, *, request_id: str) -> CashRequestResult:
        with self.ledger.store.transaction() as db:
            row = self._request(db, request_id, lock=True)
            if row["state"] in ("expired", "cancelled", "completed", "disputed"):
                return self._view(row)
            if datetime.fromisoformat(row["expires_at"]) > datetime.now(timezone.utc):
                raise StateError("Request is still within confirmation window")
            if row["state"] == "customer_confirmed":
                # A customer-approved handover has an ambiguous physical outcome.
                # Keep escrow frozen in place and flag operator dispute review.
                self._transition(db, row, "disputed", "expired_after_customer_approval")
                return self._view(self._request(db, request_id))
            if row["kind"] == "cash_out":
                total = row["amount"] + row["fee"] + row["tax"]
                r = self.ledger.post_in_transaction(db, "cashout_expiry_release",
                    "expiry:" + request_id, [LedgerEntry(row["escrow_account"], "debit", total),
                                             LedgerEntry(row["customer_account"], "credit", total)],
                    actor="sim_operator_expiry")
                self._transition(db, row, "expired", "timeout_release", event_id=r.event_id)
            else:
                self._transition(db, row, "expired", "timeout_without_posting")
            return self._view(self._request(db, request_id))

    def history(self, request_id: str) -> list[dict[str, str | int]]:
        sim_id(request_id, "request")
        with self.ledger.store.engine.connect() as db:
            self._request(db, request_id)
            return [dict(row) for row in db.execute(select(cash_history).where(cash_history.c.request_id == request_id)
                         .order_by(cash_history.c.sequence)).mappings().all()]
