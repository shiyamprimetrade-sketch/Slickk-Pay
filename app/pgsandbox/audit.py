"""Immutable, redacted, hash-linked audit evidence for sandbox financial events.

Audit evidence is not regulator certification, real provider validation or a
bank statement. No credentials, phone numbers, PINs, raw callbacks or PII may
be stored in the audit ledger. Its hash chain detects accidental alteration;
without external notarization it cannot defeat a privileged database attacker.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import re
from sqlalchemy import select, insert, func, update
from sqlalchemy.engine import Connection
from .posting import LedgerService, canonical, digest
from .store import SandboxStore, utc_now
from .schema import security_events, chain, journals, postings, accounts, cash_history, requests
from .guard import sim_id
from .errors import InvalidValue, MissingRecord, AuthorizationError, InvariantError


@dataclass(frozen=True)
class SecurityRecord:
    sequence: int
    actor_id: str
    action: str
    reason: str
    entity_digest: str
    event_hash: str
    recorded_at: str
    simulation: bool = True


@dataclass(frozen=True)
class AuditProof:
    valid: bool
    count: int
    head_hash: str
    reasons: tuple[str, ...]
    simulation: bool = True


class SecurityAudit:
    ALLOWED_ACTIONS = frozenset({"unauthorized_transfer", "rate_limit", "invalid_consent",
        "frozen_account", "suspicious_agent", "rejected_replay", "request_expired",
        "statement_mismatch", "credential_rotation", "case_opened", "case_closed",
        "review_required", "restoration_probe", "failed_handover"})
    ALLOWED_REASONS = frozenset({"owner_mismatch", "amount_limit", "count_limit",
        "invalid_state", "wrong_token", "duplicate_reference", "policy_rejection",
        "manual_review", "disputed", "excessive_velocity", "unknown_actor",
        "expired", "unbalanced", "verification_failed", "invalid_signature",
        "replay", "frozen", "missing_inventory"})

    def __init__(self, store: SandboxStore):
        self.store = store

    def _last(self, db: Connection):
        return db.execute(select(security_events).order_by(security_events.c.sequence.desc()).limit(1).with_for_update()).mappings().first()

    def record_in_transaction(self, db: Connection, *, actor_id: str, action: str,
                              reason: str, entity_id: str) -> SecurityRecord:
        sim_id(actor_id, "actor")
        sim_id(entity_id, "subject")
        if action not in self.ALLOWED_ACTIONS or reason not in self.ALLOWED_REASONS:
            raise InvalidValue("Unknown audit code")
        # Serializes with posting operations in the small sandbox. The singleton
        # chain lock prevents two audit writers choosing the same predecessor.
        db.execute(select(chain.c.id).where(chain.c.id == 1).with_for_update()).first()
        predecessor = self._last(db)
        previous = predecessor["event_hash"] if predecessor else "0" * 64
        now = utc_now()
        entity_digest = sha256(entity_id.encode()).hexdigest()
        payload = {"actor_id": actor_id, "action": action, "reason": reason,
                   "entity_digest": entity_digest, "recorded_at": now}
        event_hash = sha256((previous + "|" + canonical(payload)).encode()).hexdigest()
        result = db.execute(insert(security_events).values(**payload, previous_hash=previous,
                             event_hash=event_hash))
        return SecurityRecord(result.inserted_primary_key[0], actor_id, action, reason,
                              entity_digest, event_hash, now)

    def record(self, *, actor_id: str, action: str, reason: str,
               entity_id: str) -> SecurityRecord:
        with self.store.transaction() as db:
            return self.record_in_transaction(db, actor_id=actor_id, action=action,
                                              reason=reason, entity_id=entity_id)

    def verify(self) -> AuditProof:
        problems: list[str] = []
        previous = "0" * 64
        with self.store.engine.connect() as db:
            all_rows = db.execute(select(security_events).order_by(security_events.c.sequence)).mappings().all()
        for i, row in enumerate(all_rows, 1):
            # DB sequence numbers can have gaps after failed inserts.
            if row["previous_hash"] != previous:
                problems.append("link_mismatch")
            payload = {"actor_id": row["actor_id"], "action": row["action"],
                       "reason": row["reason"], "entity_digest": row["entity_digest"],
                       "recorded_at": row["recorded_at"]}
            expected = sha256((previous + "|" + canonical(payload)).encode()).hexdigest()
            if expected != row["event_hash"]:
                problems.append("content_mismatch")
            previous = row["event_hash"]
        return AuditProof(not problems, len(all_rows), previous, tuple(problems))

    def by_actor(self, actor_id: str, *, limit: int = 100) -> tuple[SecurityRecord, ...]:
        sim_id(actor_id, "actor")
        if not 1 <= limit <= 500:
            raise InvalidValue("Invalid query limit")
        with self.store.engine.connect() as db:
            rows = db.execute(select(security_events).where(security_events.c.actor_id == actor_id)
                              .order_by(security_events.c.sequence.desc()).limit(limit)).mappings().all()
        return tuple(SecurityRecord(row["sequence"], row["actor_id"], row["action"],
                                    row["reason"], row["entity_digest"],
                                    row["event_hash"], row["recorded_at"]) for row in rows)


@dataclass(frozen=True)
class AccountEvidence:
    account_id: str
    owner_id: str
    kind: str
    opening: int
    posted_debits: int
    posted_credits: int
    observed: int
    matches: bool
    evidence_hash: str
    simulation: bool = True


class LedgerAuditor:
    """Recompute balances from immutable journal postings, never 'repair' automatically."""

    def __init__(self, ledger: LedgerService):
        self.ledger = ledger

    def audit_account(self, account_id: str) -> AccountEvidence:
        sim_id(account_id, "account")
        with self.ledger.store.engine.connect() as db:
            account = db.execute(select(accounts).where(accounts.c.account_id == account_id)).mappings().first()
            if account is None:
                raise MissingRecord("Account does not exist")
            rows = db.execute(select(postings.c.direction, postings.c.amount)
                              .where(postings.c.account_id == account_id)).mappings().all()
        debits = sum(row["amount"] for row in rows if row["direction"] == "debit")
        credits = sum(row["amount"] for row in rows if row["direction"] == "credit")
        observed = account["balance"]
        expected = credits - debits
        evidence_hash = digest({"account_id": account_id, "debits": debits,
                                "credits": credits, "observed": observed})
        return AccountEvidence(account_id, account["owner_id"], account["kind"], 0,
                               debits, credits, observed, expected == observed,
                               evidence_hash)

    def audit_owner(self, owner_id: str) -> tuple[AccountEvidence, ...]:
        sim_id(owner_id, "owner")
        with self.ledger.store.engine.connect() as db:
            ids = db.execute(select(accounts.c.account_id).where(accounts.c.owner_id == owner_id)
                             .order_by(accounts.c.account_id)).scalars().all()
        return tuple(self.audit_account(account_id) for account_id in ids)

    def audit_all(self, *, max_accounts: int = 10000) -> dict[str, object]:
        if not 1 <= max_accounts <= 100000:
            raise InvalidValue("Invalid bounded scan limit")
        with self.ledger.store.engine.connect() as db:
            ids = db.execute(select(accounts.c.account_id).limit(max_accounts + 1)).scalars().all()
        if len(ids) > max_accounts:
            raise InvalidValue("Audit scan exceeds bounded limit")
        results = [self.audit_account(a) for a in ids]
        proof = self.ledger.verify()
        return {"count": len(results), "account_mismatches": [r.account_id for r in results if not r.matches],
                "journal_chain_valid": proof.valid, "journal_events": proof.count,
                "audit_passed": proof.valid and all(x.matches for x in results),
                "simulation": True}

    def cash_request_evidence(self, request_id: str) -> dict[str, object]:
        sim_id(request_id, "request")
        with self.ledger.store.engine.connect() as db:
            req = db.execute(select(requests).where(requests.c.request_id == request_id)).mappings().first()
            if req is None:
                raise MissingRecord("Cash request missing")
            steps = db.execute(select(cash_history.c.new_state, cash_history.c.reason,
                                       cash_history.c.recorded_at)
                               .where(cash_history.c.request_id == request_id)
                               .order_by(cash_history.c.sequence)).mappings().all()
        return {"request_id": request_id, "state": req["state"], "step_count": len(steps),
                "history_digest": digest([dict(s) for s in steps]),
                "reversal_possible": req["state"] not in ("completed", "disputed"),
                "simulation": True}
