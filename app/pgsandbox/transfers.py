"""Authorized, exactly-once synthetic customer and merchant transfers.

All checks and the final journal entry occur under one store transaction. The
source-side account belongs to the synthetic actor; the target never has to
expose its full identity. No bank, payment gateway or real balance is touched.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from sqlalchemy import select, insert, update
from .schema import accounts, journals, chain
from .store import SandboxStore
from .posting import LedgerService, LedgerEntry, JournalReceipt, canonical, digest
from .controls import VelocityController, ActorAuthorization, DEFAULT_LIMITS, LimitProfile
from .guard import event_key, sim_id
from .money import minor, Rate, minor_to_bdt
from .errors import (InvalidValue, Conflict, MissingRecord, AuthorizationError,
                     InsufficientBalance, RateLimit)


@dataclass(frozen=True)
class TransferQuote:
    sender: str
    receiver: str
    amount_poisha: int
    fee_poisha: int
    tax_poisha: int
    total_poisha: int
    version: str = "pilot-2026-11-03-v1"
    simulation: bool = True

    def public(self) -> dict[str, object]:
        return {"sender": self.sender[:6] + "***", "receiver": self.receiver[:6] + "***",
                "principal_bdt": minor_to_bdt(self.amount_poisha),
                "fee_bdt": minor_to_bdt(self.fee_poisha),
                "tax_bdt": minor_to_bdt(self.tax_poisha),
                "total_bdt": minor_to_bdt(self.total_poisha),
                "tariff_version": self.version, "simulation": True}


@dataclass(frozen=True)
class TransferResult:
    event_id: str
    from_account: str
    to_account: str
    principal_poisha: int
    fee_poisha: int
    customer_total_poisha: int
    status: str = "posted"
    simulation: bool = True


class TransferService:
    def __init__(self, ledger: LedgerService, *, limits: LimitProfile = DEFAULT_LIMITS,
                 fee_rate: Rate | None = None, revenue_account: str | None = None):
        self.ledger = ledger
        self.auth = ActorAuthorization(ledger)
        self.velocity = VelocityController(ledger, limits)
        self.fee_rate = fee_rate or Rate("customer_transfer", 0)
        self.revenue_account = revenue_account
        if revenue_account is not None:
            sim_id(revenue_account, "revenue account")

    def quote(self, sender: str, receiver: str, amount_poisha: int) -> TransferQuote:
        sim_id(sender, "sender")
        sim_id(receiver, "receiver")
        minor(amount_poisha, positive=True)
        if sender == receiver:
            raise InvalidValue("Sender and receiver must differ")
        fee = self.fee_rate.fee(amount_poisha)
        return TransferQuote(sender, receiver, amount_poisha, fee, 0, amount_poisha + fee)

    def _lines(self, q: TransferQuote) -> list[LedgerEntry]:
        result = [LedgerEntry(q.sender, "debit", q.total_poisha),
                  LedgerEntry(q.receiver, "credit", q.amount_poisha)]
        if q.fee_poisha:
            if not self.revenue_account:
                raise InvalidValue("Fee revenue account is not configured")
            result.append(LedgerEntry(self.revenue_account, "credit", q.fee_poisha))
        return result

    def send(self, *, actor: str, sender: str, recipient: str, amount_poisha: int,
             key: str) -> TransferResult:
        event_key(key)
        sim_id(actor, "actor")
        q = self.quote(sender, recipient, amount_poisha)
        lines = self._lines(q)
        payload = {"operation": "customer_transfer", "key": key, "actor": actor,
                   "lines": [x.as_dict() for x in lines]}
        req_digest = digest(payload)
        with self.ledger.store.transaction() as db:
            # Global journal head lock must be acquired before velocity inspection
            # so concurrent writers cannot both pass a daily limit.
            head = db.execute(select(chain.c.id).where(chain.c.id == 1).with_for_update()).first()
            if head is None:
                raise MissingRecord("Journal was not initialized")
            prior = db.execute(select(journals).where(journals.c.idempotency_key == key)).mappings().first()
            if prior is not None:
                if prior["request_digest"] != req_digest:
                    raise Conflict("Idempotency key collision")
                return TransferResult(prior["event_id"], sender, recipient, amount_poisha,
                                      q.fee_poisha, q.total_poisha)
            self.auth.require_customer(db, sender, actor)
            target = db.execute(select(accounts.c.kind, accounts.c.frozen)
                                .where(accounts.c.account_id == recipient)).first()
            if target is None or target.frozen or target.kind not in ("customer", "merchant"):
                raise AuthorizationError("Recipient unavailable or ineligible")
            self.velocity.check_or_raise(db, sender, "customer_transfer", amount_poisha)
            receipt = self.ledger.post_in_transaction(db, "customer_transfer", key, lines, actor=actor)
            self.velocity.record(db, sender, "customer_transfer", amount_poisha, receipt.event_id)
            return TransferResult(receipt.event_id, sender, recipient, amount_poisha,
                                  q.fee_poisha, q.total_poisha)

    def inspect(self, idempotency_key: str) -> JournalReceipt:
        return self.ledger.event(idempotency_key)

    def validate_pilot_terms(self) -> bool:
        return self.fee_rate.parts_per_million == 0 and self.fee_rate.minimum_poisha == 0


class MerchantSandboxTransfer:
    """Separate merchant collection; not an external card or MFS checkout."""
    def __init__(self, ledger: LedgerService, *, revenue_account: str,
                 merchant_fee: Rate | None = None):
        self.ledger = ledger
        self.fee = merchant_fee or Rate("merchant_fee", 4500)
        self.revenue_account = sim_id(revenue_account, "revenue account")
        self.auth = ActorAuthorization(ledger)

    def quote(self, amount_poisha: int) -> dict[str, object]:
        minor(amount_poisha, positive=True)
        charge = self.fee.fee(amount_poisha)
        if charge >= amount_poisha:
            raise InvalidValue("Merchant processing fee exceeds principal")
        return {"principal_poisha": amount_poisha, "merchant_fee_poisha": charge,
                "merchant_receives_poisha": amount_poisha - charge,
                "pilot_rate_ppm": self.fee.parts_per_million,
                "simulation": True}

    def capture(self, *, customer_owner: str, customer_account: str,
                merchant_account: str, amount_poisha: int, key: str) -> JournalReceipt:
        event_key(key)
        if customer_account == merchant_account:
            raise InvalidValue("Self payment rejected")
        q = self.quote(amount_poisha)
        charge = int(q["merchant_fee_poisha"])
        lines = [LedgerEntry(customer_account, "debit", amount_poisha),
                 LedgerEntry(merchant_account, "credit", amount_poisha - charge)]
        if charge:
            lines.append(LedgerEntry(self.revenue_account, "credit", charge))
        with self.ledger.store.transaction() as db:
            self.auth.require_customer(db, customer_account, customer_owner)
            merchant = db.execute(select(accounts).where(accounts.c.account_id == merchant_account)).mappings().first()
            if merchant is None or merchant["kind"] != "merchant" or merchant["frozen"]:
                raise AuthorizationError("Merchant is not eligible")
            return self.ledger.post_in_transaction(db, "merchant_payment", key, lines, actor=customer_owner)

    def reverse(self, *, original_key: str, reversal_key: str, operator: str) -> JournalReceipt:
        event_key(original_key)
        event_key(reversal_key)
        sim_id(operator, "operator")
        if original_key == reversal_key:
            raise Conflict("Original and reversal keys cannot match")
        original = self.ledger.event(original_key)
        if original.operation != "merchant_payment":
            raise AuthorizationError("Only simulated merchant captures can be reversed here")
        entries = self.ledger.entries(original.event_id)
        opposite = [LedgerEntry(x.account_id, "credit" if x.direction == "debit" else "debit", x.amount)
                    for x in entries]
        return self.ledger.post("merchant_reversal", reversal_key, opposite, actor=operator)
