"""Reproducible fault-injection and concurrency scenarios on fictional accounts.

These probes are not production load tests. A correct result is measured from
database-ledger evidence after failures and retries, not optimistic HTTP ACKs.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from hashlib import sha256
import random
from typing import Callable
from .store import SandboxStore, is_retryable_db_failure
from .posting import LedgerService, LedgerEntry, digest
from .transfers import TransferService
from .errors import BankingError, InvalidValue, InsufficientBalance
from .money import minor
from .guard import sim_id


@dataclass(frozen=True)
class TransferAttempt:
    idempotency_key: str
    requested_poisha: int
    outcome: str
    event_id: str | None
    exception_code: str | None
    simulation: bool = True


@dataclass(frozen=True)
class ScenarioProof:
    name: str
    requested: int
    posted: int
    rejected: int
    initial_funds: int
    ending_sender_funds: int
    total_recipient_credits: int
    journal_valid: bool
    invariant_passed: bool
    observations_hash: str
    simulation: bool = True


class SyntheticStressScenarios:
    def __init__(self, ledger: LedgerService, *, seed: int = 20261103):
        self.ledger = ledger
        if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed <= 2**32-1:
            raise InvalidValue("Invalid reproducibility seed")
        self.seed = seed

    def race_for_funds(self, *, sender: str, sender_owner: str, recipients: tuple[str,...],
                       each_poisha: int, batch_reference: str, concurrency: int = 6) -> ScenarioProof:
        if not 2 <= len(recipients) <= 64 or not 1 <= concurrency <= 16:
            raise InvalidValue("Scenario bounds exceeded")
        if len(set(recipients)) != len(recipients):
            raise InvalidValue("Scenario recipients must be distinct")
        sim_id(sender,"sender")
        sim_id(sender_owner,"owner")
        if any(recipient == sender for recipient in recipients):
            raise InvalidValue("Self-transfer race is unsupported")
        minor(each_poisha,positive=True)
        if not batch_reference.startswith("sim_") or len(batch_reference)>48:
            raise InvalidValue("Only synthetic stress references allowed")
        initial=self.ledger.balance(sender).poisha
        balances_before={r:self.ledger.balance(r).poisha for r in recipients}
        shuffled=list(recipients)
        random.Random(self.seed).shuffle(shuffled)
        observations=[]

        def run(position: int, recipient: str) -> TransferAttempt:
            key=f"scenario:{batch_reference}:{position}"
            try:
                receipt=self.ledger.transfer(sender,recipient,each_poisha,key=key,actor=sender_owner)
                return TransferAttempt(key,each_poisha,"posted",receipt.event_id,None)
            except BankingError as exc:
                return TransferAttempt(key,each_poisha,"rejected",None,exc.code)
            except Exception as exc:
                if is_retryable_db_failure(exc):
                    return TransferAttempt(key,each_poisha,"retryable",None,"SERIALIZATION_RETRY")
                return TransferAttempt(key,each_poisha,"failed",None,type(exc).__name__)

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures=[pool.submit(run,index,recipient) for index,recipient in enumerate(shuffled)]
            for future in as_completed(futures):
                observations.append(future.result())
        count=sum(row.outcome=="posted" for row in observations)
        rejected=sum(row.outcome!="posted" for row in observations)
        recipient_gain=sum(self.ledger.balance(r).poisha-balances_before[r] for r in recipients)
        sender_end=self.ledger.balance(sender).poisha
        proof=self.ledger.verify()
        invariant=(proof.valid and sender_end >= 0 and
                   sender_end+recipient_gain == initial and
                   recipient_gain == count*each_poisha)
        evidence_hash=digest([row.__dict__ for row in sorted(observations,key=lambda a:a.idempotency_key)])
        return ScenarioProof("concurrent_spend",len(recipients),count,rejected,initial,
                             sender_end,recipient_gain,proof.valid,invariant,evidence_hash)

    def verify_idempotent_retries(self, *, debit: str, credit: str, amount: int,
                                  key: str, actor: str, repeat: int = 20) -> dict[str, object]:
        if not 2 <= repeat <= 100:
            raise InvalidValue("Invalid test replay count")
        minor(amount,positive=True)
        initial_debit=self.ledger.balance(debit).poisha
        initial_credit=self.ledger.balance(credit).poisha
        results=[]
        for _ in range(repeat):
            results.append(self.ledger.transfer(debit,credit,amount,key=key,actor=actor))
        exactly_once=(len({r.event_id for r in results}) == 1 and
            self.ledger.balance(debit).poisha == initial_debit - amount and
            self.ledger.balance(credit).poisha == initial_credit + amount)
        return {"retries":repeat,"all_same_event":len({r.event_id for r in results})==1,
                "exactly_once":exactly_once,"journal_valid":self.ledger.verify().valid,
                "simulation":True}

    def baseline_invariants(self) -> dict[str, object]:
        proof=self.ledger.verify()
        return {"balanced":proof.total_debits==proof.total_credits,
                "hash_chain_valid":proof.valid,"journal_event_count":proof.count,
                "mismatches":proof.mismatches,"simulation":True}


@dataclass(frozen=True)
class FailureInjectionPlan:
    fail_before_posting: bool = False
    fail_after_posting_before_commit: bool = False
    raise_error_code: str = "INJECTED_ROLLBACK"

    def __post_init__(self):
        if self.raise_error_code != "INJECTED_ROLLBACK":
            raise InvalidValue("Only deterministic rollback signal permitted")


def atomic_failure_probe(ledger: LedgerService, *, debit: str, credit: str,
                         amount: int, key: str, actor: str,
                         plan: FailureInjectionPlan) -> dict[str, object]:
    """Prove an exception before COMMIT erases both account and journal writes."""
    before_sender=ledger.balance(debit).poisha
    before_recipient=ledger.balance(credit).poisha
    before_events=ledger.verify().count
    rejected=False
    try:
        with ledger.store.transaction() as db:
            if plan.fail_before_posting:
                raise RuntimeError(plan.raise_error_code)
            ledger.post_in_transaction(db,"sim_failure_probe",key,[
                LedgerEntry(debit,"debit",amount),LedgerEntry(credit,"credit",amount)],actor=actor)
            if plan.fail_after_posting_before_commit:
                raise RuntimeError(plan.raise_error_code)
    except RuntimeError as exc:
        if str(exc) != plan.raise_error_code:
            raise
        rejected=True
    after=ledger.verify()
    unchanged=(ledger.balance(debit).poisha==before_sender and
               ledger.balance(credit).poisha==before_recipient and
               after.count==before_events)
    return {"failure_injected":rejected,"rollback_complete":unchanged if rejected else False,
            "hash_chain_valid":after.valid,"simulation":True}
