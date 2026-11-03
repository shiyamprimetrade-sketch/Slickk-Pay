"""Isolated disposable PostgreSQL Cycle 002 conformance test.

Never invoke with real secrets or production URLs. The target guard rejects
anything except the GitHub Actions localhost database slickk_ci_test.
"""
from __future__ import annotations
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.pgsandbox import SandboxStore,LedgerService,LedgerEntry
from app.pgsandbox.pg_migrations import install_pg_sandbox
from app.pgsandbox.pg_conformance import PostgresConformance,replay_concurrent_debits
from app.pgsandbox.scenarios import atomic_failure_probe,FailureInjectionPlan
from app.pgsandbox.outbox import DurableOutbox
from app.pgsandbox.authz import SyntheticTokenService,KeyVersion
from app.pgsandbox.errors import BankingError


def verify():
    if os.getenv("SLICKK_PG_SANDBOX")!="true" or os.getenv("CI")!="true":
        raise SystemExit("CI + guarded PostgreSQL sandbox flags required")
    url=os.getenv("SLICKK_PG_TEST_DATABASE_URL", "")
    if not url or "slickk_ci_test" not in url:
        raise SystemExit("Disallowed database target")
    with SandboxStore(url,bootstrap=True) as store:
        if store.dialect!="postgresql":
            raise SystemExit("PostgreSQL sandbox conformance expected")
        # Rehearse migration repeatability on the same disposable DB.
        first=install_pg_sandbox(store.engine)
        second=install_pg_sandbox(store.engine)
        if first.sha256!=second.sha256:
            raise AssertionError("Schema migration digest drift")
        pg=PostgresConformance(store)
        installed=pg.require_healthy()
        print("PostgreSQL schema, immutable triggers, chain head: PASS")
        ledger=LedgerService(store)
        for account,owner,kind in (
            ("sim_pg_issuer","sim_owner_pg_issuer","sim_issuer"),
            ("sim_pg_sender","sim_owner_pg_sender","customer"),
            ("sim_pg_receiver","sim_owner_pg_receiver","customer")):
            ledger.open_account(account,owner,kind)
        ledger.transfer("sim_pg_issuer","sim_pg_sender",20000,
                        key="issue:postgres_test01",actor="sim_operator_pg")
        race=replay_concurrent_debits(ledger,sender="sim_pg_sender",
                     receiver="sim_pg_receiver",amount=5000,
                     operation_key="postgres:replay0001",clients=6)
        if not race["deduplicated"] or not race["journal_valid"]:
            raise AssertionError(f"Concurrent PG idempotency failed: {race}")
        # A SERIALIZABLE writer can return a retryable 40001. Ensure eventual
        # same-key retry does not produce a second financial posting.
        ledger.transfer("sim_pg_sender","sim_pg_receiver",5000,
                        key="postgres:replay0001",actor="sim_operator_concurrency")
        if ledger.balance("sim_pg_receiver").poisha!=5000:
            raise AssertionError("Provider-independent exactly-once journal failed")
        failure=atomic_failure_probe(ledger,debit="sim_pg_sender",credit="sim_pg_receiver",
                amount=1000,key="postgres:rollback0001",actor="sim_operator_pg",
                plan=FailureInjectionPlan(fail_after_posting_before_commit=True))
        if not failure["rollback_complete"]:
            raise AssertionError("Crash-before-commit left partial financial posting")
        journal=ledger.verify()
        if not journal.valid or journal.total_debits!=journal.total_credits:
            raise AssertionError("PostgreSQL journal reconstruction failed")
        notice=DurableOutbox(store).enqueue(event_id=ledger.event("postgres:replay0001").event_id,
            destination="sim_operator_audit",payload={"type":"POSTED","currency":"BDT","amount_poisha":5000})
        if not notice.simulation:
            raise AssertionError("Outbox lost sandbox classification")
        identity=SyntheticTokenService(store,(KeyVersion("sim_ci_key_001",b"T"*32),),"sim_ci_key_001")
        token=identity.issue(actor_id="sim_owner_pg_sender",scope="sim_inspect",device_id="sim_device_ci_01")
        identity.validate(token=token,scope="sim_inspect",actor_id="sim_owner_pg_sender",device_id="sim_device_ci_01")
        try:
            identity.validate(token=token,scope="sim_inspect",actor_id="sim_owner_pg_sender",device_id="sim_device_ci_01")
        except BankingError:
            pass
        else:
            raise AssertionError("Authorization nonce replay was accepted")
        if not pg.require_healthy().balanced:
            raise AssertionError("Cross-posting reconciliation failed")
        print("PostgreSQL SERIALIZABLE replay, rollback, outbox and auth nonce: PASS")
        print("Verified fictional journal event count:",journal.count)
        print("NO LIVE RAILS, NO PRODUCTION DATABASE, NO ACTUAL FINANCIAL ACTIVITY")


if __name__=="__main__":
    verify()
