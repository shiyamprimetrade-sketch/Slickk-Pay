"""Append-only *shadow accounting* journal for offline reconciliation evidence.

IMPORTANT: This is not the customer stored-value ledger, bank ledger, or source
of merchant settlement truth. Entries are only analytical assertions and must
be corroborated with real provider and bank records before operational use.
No network, withdrawal, transfer, top-up or payment execution is possible here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from threading import RLock
from typing import Iterable, Sequence

from .primitives import (
    ConflictError, EvidenceError, InvariantError, PolicyError, bdt_from_minor,
    evidence_hash, nonnegative_minor, positive_minor, reference, safe_key,
    timestamp, utc_iso,
)


class AccountClass(str, Enum):
    CLEARING_ASSET = "clearing_asset"
    SETTLEMENT_ASSET = "settlement_asset"
    GATEWAY_FEES = "gateway_fees"
    MERCHANT_PAYABLE = "merchant_payable"
    REFUND_LIABILITY = "refund_liability"
    SUSPENSE_LIABILITY = "suspense_liability"
    OPERATIONAL_EXPENSE = "operational_expense"
    RECONCILIATION_OFFSET = "reconciliation_offset"


class Side(str, Enum):
    DEBIT = "debit"
    CREDIT = "credit"


@dataclass(frozen=True, slots=True)
class Account:
    account_id: str
    merchant_id: str
    account_class: AccountClass
    currency: str = "BDT"
    active: bool = True

    def __post_init__(self) -> None:
        reference(self.account_id, field_name="account_id")
        reference(self.merchant_id, field_name="merchant_id")
        if not isinstance(self.account_class, AccountClass) or self.currency != "BDT":
            raise EvidenceError("Unsupported accounting class or currency")


@dataclass(frozen=True, slots=True)
class Posting:
    account_id: str
    side: Side
    minor: int

    def __post_init__(self) -> None:
        reference(self.account_id, field_name="account_id")
        if not isinstance(self.side, Side):
            raise EvidenceError("Invalid debit/credit side")
        positive_minor(self.minor)

    def as_dict(self) -> dict[str, object]:
        return {"account_id": self.account_id, "side": self.side.value,
                "amount_poisha": self.minor}


@dataclass(frozen=True, slots=True)
class Entry:
    entry_id: str
    merchant_id: str
    event_ref: str
    event_kind: str
    occurred_at: datetime
    postings: tuple[Posting, ...]
    sequence: int
    prior_hash: str
    entry_hash: str
    reverses_entry: str | None = None

    @property
    def total_debit_poisha(self) -> int:
        return sum(x.minor for x in self.postings if x.side == Side.DEBIT)

    @property
    def total_credit_poisha(self) -> int:
        return sum(x.minor for x in self.postings if x.side == Side.CREDIT)

    def checksum_data(self) -> dict:
        return {"entry_id": self.entry_id, "merchant_id": self.merchant_id,
                "event_ref": self.event_ref, "event_kind": self.event_kind,
                "occurred_at": utc_iso(self.occurred_at),
                "postings": [p.as_dict() for p in self.postings],
                "sequence": self.sequence, "prior_hash": self.prior_hash,
                "reverses_entry": self.reverses_entry}

    def verify_hash(self) -> bool:
        return self.entry_hash == evidence_hash(self.checksum_data())

    def public_metadata(self) -> dict:
        return {"entry_id": self.entry_id, "merchant_id": self.merchant_id,
                "event_kind": self.event_kind, "sequence": self.sequence,
                "debits_bdt": bdt_from_minor(self.total_debit_poisha),
                "credits_bdt": bdt_from_minor(self.total_credit_poisha),
                "entry_hash": self.entry_hash,
                "reversal": self.reverses_entry is not None}


@dataclass(frozen=True, slots=True)
class Balance:
    account_id: str
    debits_poisha: int
    credits_poisha: int

    @property
    def net_debit_poisha(self) -> int:
        return self.debits_poisha - self.credits_poisha

    def as_dict(self) -> dict:
        return {"account_id": self.account_id,
                "debits_bdt": bdt_from_minor(self.debits_poisha),
                "credits_bdt": bdt_from_minor(self.credits_poisha),
                "net_debit_bdt": bdt_from_minor(self.net_debit_poisha)}


class ShadowJournal:
    """Thread-safe, merchant-scoped analytical accounting journal.

    Atomicity covers this in-memory journal instance only. This abstraction is
    deliberately NOT a production financial datastore or settlement mechanism.
    """

    GENESIS_HASH = "0" * 64

    def __init__(self) -> None:
        self._lock = RLock()
        self._accounts: dict[str, Account] = {}
        self._entries: list[Entry] = []
        self._event_index: dict[tuple[str, str], str] = {}
        self._by_id: dict[str, Entry] = {}
        self._reversals: dict[str, str] = {}

    def add_account(self, account: Account) -> None:
        if not isinstance(account, Account):
            raise EvidenceError("Expected Account")
        with self._lock:
            if account.account_id in self._accounts:
                if account != self._accounts[account.account_id]:
                    raise ConflictError("Account identity cannot be redefined")
                return
            self._accounts[account.account_id] = account

    def account(self, account_id: str) -> Account:
        reference(account_id, field_name="account_id")
        with self._lock:
            if account_id not in self._accounts:
                raise EvidenceError("Account not registered")
            return self._accounts[account_id]

    def _validate_postings(self, merchant_id: str, postings: Sequence[Posting]) -> tuple[Posting, ...]:
        if not isinstance(postings, Sequence) or not 2 <= len(postings) <= 32:
            raise EvidenceError("A balanced journal requires 2–32 postings")
        if any(not isinstance(p, Posting) for p in postings):
            raise EvidenceError("Non-Posting provided")
        debit = sum(p.minor for p in postings if p.side == Side.DEBIT)
        credit = sum(p.minor for p in postings if p.side == Side.CREDIT)
        if debit != credit or debit <= 0:
            raise InvariantError("Journal entry debits and credits must balance")
        if debit > 9_000_000_000_000:
            raise EvidenceError("Journal amount exceeds limit")
        for posting in postings:
            account = self._accounts.get(posting.account_id)
            if account is None:
                raise EvidenceError("Posting refers to unknown account")
            if account.merchant_id != merchant_id:
                raise PolicyError("Posting crosses merchant boundary")
            if not account.active:
                raise PolicyError("Inactive account cannot receive posting")
            if account.currency != "BDT":
                raise EvidenceError("Unapproved posting currency")
        return tuple(postings)

    def append(self, *, entry_id: str, merchant_id: str, event_ref: str,
               event_kind: str, occurred_at: datetime, postings: Sequence[Posting],
               reverses_entry: str | None = None) -> Entry:
        reference(entry_id, field_name="entry_id")
        reference(merchant_id, field_name="merchant_id")
        reference(event_ref, field_name="event_ref")
        safe_key(event_kind, field_name="event_kind")
        occurred_at = timestamp(occurred_at)
        with self._lock:
            posted = self._validate_postings(merchant_id, postings)
            key = merchant_id, event_ref
            if reverses_entry is not None:
                if reverses_entry not in self._by_id:
                    raise EvidenceError("Reversed entry not found")
                target = self._by_id[reverses_entry]
                if target.merchant_id != merchant_id:
                    raise PolicyError("Cannot reverse another merchant's entry")
                if reverses_entry in self._reversals:
                    raise ConflictError("Entry already reversed")
                if target.reverses_entry:
                    raise PolicyError("A reversal cannot itself be reversed")
                expected = tuple(Posting(p.account_id,
                                         Side.CREDIT if p.side == Side.DEBIT else Side.DEBIT,
                                         p.minor) for p in target.postings)
                if posted != expected:
                    raise InvariantError("Reversal postings must exactly negate original")
            if key in self._event_index:
                existing = self._by_id[self._event_index[key]]
                if (existing.entry_id != entry_id or existing.event_kind != event_kind
                        or existing.postings != posted or existing.reverses_entry != reverses_entry):
                    raise ConflictError("Evidence event reference reused with different contents")
                return existing
            if entry_id in self._by_id:
                raise ConflictError("Journal entry ID already used")
            sequence = len(self._entries) + 1
            prior = self._entries[-1].entry_hash if self._entries else self.GENESIS_HASH
            data = {"entry_id": entry_id, "merchant_id": merchant_id,
                    "event_ref": event_ref, "event_kind": event_kind,
                    "occurred_at": utc_iso(occurred_at),
                    "postings": [p.as_dict() for p in posted],
                    "sequence": sequence, "prior_hash": prior,
                    "reverses_entry": reverses_entry}
            entry = Entry(entry_id, merchant_id, event_ref, event_kind, occurred_at,
                          posted, sequence, prior, evidence_hash(data), reverses_entry)
            self._entries.append(entry)
            self._by_id[entry_id] = entry
            self._event_index[key] = entry_id
            if reverses_entry is not None:
                self._reversals[reverses_entry] = entry_id
            return entry

    def reverse(self, entry_id: str, *, reversal_id: str,
                reversal_event_ref: str, occurred_at: datetime) -> Entry:
        reference(entry_id, field_name="entry_id")
        with self._lock:
            if entry_id not in self._by_id:
                raise EvidenceError("Cannot reverse missing entry")
            target = self._by_id[entry_id]
            reversed_postings = [Posting(p.account_id,
                                         Side.CREDIT if p.side == Side.DEBIT else Side.DEBIT,
                                         p.minor) for p in target.postings]
            return self.append(entry_id=reversal_id, merchant_id=target.merchant_id,
                               event_ref=reversal_event_ref, event_kind="manual_reversal",
                               occurred_at=occurred_at, postings=reversed_postings,
                               reverses_entry=entry_id)

    def entry(self, entry_id: str, *, merchant_id: str) -> Entry:
        reference(entry_id, field_name="entry_id")
        reference(merchant_id, field_name="merchant_id")
        with self._lock:
            entry = self._by_id.get(entry_id)
            if entry is None or entry.merchant_id != merchant_id:
                raise EvidenceError("Journal entry not found for merchant")
            return entry

    def entries(self, merchant_id: str) -> tuple[Entry, ...]:
        reference(merchant_id, field_name="merchant_id")
        with self._lock:
            return tuple(entry for entry in self._entries if entry.merchant_id == merchant_id)

    def balance(self, account_id: str) -> Balance:
        account = self.account(account_id)
        with self._lock:
            debits = credits = 0
            for entry in self._entries:
                for posting in entry.postings:
                    if posting.account_id == account.account_id:
                        if posting.side == Side.DEBIT:
                            debits += posting.minor
                        else:
                            credits += posting.minor
            return Balance(account_id, debits, credits)

    def trial_balance(self, merchant_id: str) -> dict:
        reference(merchant_id, field_name="merchant_id")
        with self._lock:
            accounts = sorted((a for a in self._accounts.values()
                               if a.merchant_id == merchant_id), key=lambda a: a.account_id)
            balances = [self.balance(a.account_id) for a in accounts]
            debit_total = sum(x.debits_poisha for x in balances)
            credit_total = sum(x.credits_poisha for x in balances)
            if debit_total != credit_total:
                raise InvariantError("Shadow journal trial balance is broken")
            return {"merchant_id": merchant_id,
                    "account_count": len(accounts),
                    "entry_count": len(self.entries(merchant_id)),
                    "total_debits_bdt": bdt_from_minor(debit_total),
                    "total_credits_bdt": bdt_from_minor(credit_total),
                    "balances": [b.as_dict() for b in balances],
                    "verified_chain": self.verify_chain()}

    def verify_chain(self) -> bool:
        with self._lock:
            prior = self.GENESIS_HASH
            event_keys: set[tuple[str, str]] = set()
            ids: set[str] = set()
            for seq, entry in enumerate(self._entries, 1):
                if entry.sequence != seq or entry.prior_hash != prior:
                    return False
                if not entry.verify_hash():
                    return False
                if entry.total_credit_poisha != entry.total_debit_poisha:
                    return False
                if entry.entry_id in ids or (entry.merchant_id, entry.event_ref) in event_keys:
                    return False
                ids.add(entry.entry_id)
                event_keys.add((entry.merchant_id, entry.event_ref))
                prior = entry.entry_hash
            return True

    def chain_root(self) -> str:
        with self._lock:
            if not self.verify_chain():
                raise InvariantError("Cannot export unverified journal")
            return self._entries[-1].entry_hash if self._entries else self.GENESIS_HASH

    def stats(self) -> dict[str, object]:
        with self._lock:
            return {"entry_count": len(self._entries),
                    "account_count": len(self._accounts),
                    "reversal_count": len(self._reversals),
                    "chain_root": self.chain_root(),
                    "network_or_settlement_capability": False}
