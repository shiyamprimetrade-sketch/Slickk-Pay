"""Recovery, stress, terminal policy, and SQL conformance checks."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import select,update
from app.pgsandbox import SandboxStore, LedgerService
from app.pgsandbox.scenarios import SyntheticStressScenarios,atomic_failure_probe,FailureInjectionPlan
from app.pgsandbox.workflow_policy import chain_transitions,require_transition
from app.pgsandbox.cash import SandboxCashDesk
from app.pgsandbox.recovery import CashRecovery,DiagnosticScans
from app.pgsandbox.pg_migrations import split_sql
from app.pgsandbox.errors import StateError,InvalidValue
from app.pgsandbox.schema import requests


class RecoveryV2Tests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix="sim-recovery-");self.addCleanup(t.cleanup)
        self.store=SandboxStore("sqlite+pysqlite:///"+str(Path(t.name)/"test.db"),local_test=True)
        self.addCleanup(self.store.dispose)
        self.ledger=LedgerService(self.store)
        for aid,owner,kind in [
            ("sim_issuer_primary","sim_owner_issuer","sim_issuer"),
            ("sim_customer_alpha","sim_owner_alpha","customer"),
            ("sim_customer_bravo","sim_owner_bravo","customer"),
            ("sim_customer_charlie","sim_owner_charlie","customer"),
            ("sim_treasury_sandbox","sim_owner_treasury","platform_treasury"),
            ("sim_platform_revenue","sim_owner_platform","platform_revenue"),
            ("sim_agent_float","sim_owner_agent","agent_float"),
            ("sim_agent_commission","sim_owner_agent","agent_commission")]:
            self.ledger.open_account(aid,owner,kind)
        for aid,amount in (("sim_customer_alpha",20000),("sim_agent_float",20000),
                           ("sim_treasury_sandbox",20000)):
            self.ledger.transfer("sim_issuer_primary",aid,amount,
                                 key="issue:"+aid,actor="sim_operator_admin")
        self.cash=SandboxCashDesk(self.ledger,platform_revenue="sim_platform_revenue",
                                  platform_treasury="sim_treasury_sandbox",
                                  agent_commission_lookup={"sim_agent_float":"sim_agent_commission"})
        self.cash.set_agent_cash(agent_actor="sim_owner_agent",agent_account="sim_agent_float",
                                 cash_poisha=10000,ceiling_poisha=50000)

    def test_failure_before_commit_rolls_back(self):
        p=atomic_failure_probe(self.ledger,debit="sim_customer_alpha",credit="sim_customer_bravo",
                               amount=1000,key="probe:rollback0001",actor="sim_owner_alpha",
                               plan=FailureInjectionPlan(fail_after_posting_before_commit=True))
        self.assertTrue(p["rollback_complete"])
        self.assertTrue(p["hash_chain_valid"])
        self.assertEqual(self.ledger.balance("sim_customer_bravo").poisha,0)

    def test_simultaneous_customer_spend_no_overdraft(self):
        x=SyntheticStressScenarios(self.ledger).race_for_funds(sender="sim_customer_alpha",
            sender_owner="sim_owner_alpha",recipients=("sim_customer_bravo","sim_customer_charlie"),
            each_poisha=15000,batch_reference="sim_race001",concurrency=2)
        self.assertTrue(x.invariant_passed)
        self.assertEqual(x.posted,1)
        self.assertEqual(x.rejected,1)

    def test_terminal_cash_policy(self):
        self.assertTrue(chain_transitions("cash_out",("reserved","customer_confirmed","completed"))["valid"])
        self.assertFalse(chain_transitions("cash_out",("reserved","completed"))["valid"])
        with self.assertRaises(StateError):
            require_transition("cancelled","completed")

    def test_ambiguous_approved_handover_goes_dispute(self):
        a=self.cash.create(agent_actor="sim_owner_agent",customer_actor="sim_owner_alpha",
               agent_account="sim_agent_float",customer_account="sim_customer_alpha",
               request_id="sim_req_approved_expiry",direction="cash_out",principal=5000)
        self.cash.approve_cashout(customer_actor="sim_owner_alpha",request_id=a.request.request_id,customer_token=a.token)
        with self.assertRaises(StateError):
            self.cash.cancel(actor="sim_owner_alpha",request_id=a.request.request_id,reason="customer_declined")
        with self.store.transaction() as db:
            db.execute(update(requests).where(requests.c.request_id==a.request.request_id)
                       .values(expires_at=(datetime.now(timezone.utc)-timedelta(seconds=10)).isoformat()))
        expired=self.cash.expire(request_id=a.request.request_id)
        self.assertEqual(expired.state,"disputed")
        self.assertGreater(self.ledger.balance("sim_escrow_"+__import__('hashlib').sha256(a.request.request_id.encode()).hexdigest()[:30]).poisha,0)
        self.assertTrue(self.ledger.verify().valid)

    def test_handover_digest_replay(self):
        a=self.cash.create(agent_actor="sim_owner_agent",customer_actor="sim_owner_alpha",
               agent_account="sim_agent_float",customer_account="sim_customer_alpha",
               request_id="sim_req_handover_1",direction="cash_out",principal=5000)
        self.cash.approve_cashout(customer_actor="sim_owner_alpha",request_id=a.request.request_id,customer_token=a.token)
        self.cash.complete_cashout(agent_actor="sim_owner_agent",request_id=a.request.request_id,
                                   handover_reference="cashout:uniquehandover1")
        self.assertEqual(self.cash.complete_cashout(agent_actor="sim_owner_agent",request_id=a.request.request_id,
                          handover_reference="cashout:uniquehandover1").state,"completed")
        with self.assertRaises(Exception):
            self.cash.complete_cashout(agent_actor="sim_owner_agent",request_id=a.request.request_id,
                                       handover_reference="cashout:differenthandover")

    def test_postgres_trigger_message_avoids_psycopg_percent_placeholders(self):
        from app.pgsandbox.pg_migrations import migration_content, split_sql
        migration = migration_content()
        self.assertIn("RAISE EXCEPTION 'immutable fictional ledger audit record';", migration)
        self.assertNotIn("ledger audit record: %", migration)
        self.assertGreater(len(split_sql(migration)), 5)

    def test_sql_script_parser_rejects_unclosed_dollar(self):
        with self.assertRaises(InvalidValue):
            split_sql("DO $$ BEGIN RAISE EXCEPTION 'bad'; END;")

if __name__=="__main__": unittest.main()
