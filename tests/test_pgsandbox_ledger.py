"""Isolated SQLite test mode for PostgreSQL-oriented fictitious-money ledger."""
import os
import tempfile
import unittest
from pathlib import Path
from sqlalchemy import text
from app.pgsandbox import SandboxStore, LedgerService, LedgerEntry
from app.pgsandbox.errors import Conflict, InsufficientBalance, FrozenAccount, InvariantError, UnauthorizedEnvironment


class LedgerV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sim-lab-")
        self.addCleanup(self.temp.cleanup)
        self.store = SandboxStore("sqlite+pysqlite:///"+str(Path(self.temp.name)/"test.db"),local_test=True)
        self.addCleanup(self.store.dispose)
        self.ledger = LedgerService(self.store)
        self.ledger.open_account("sim_issuer_primary", "sim_owner_test_issuer", "sim_issuer")
        self.ledger.open_account("sim_customer_aaaa", "sim_owner_aaaa", "customer")
        self.ledger.open_account("sim_customer_bbbb", "sim_owner_bbbb", "customer")
        self.ledger.transfer("sim_issuer_primary","sim_customer_aaaa",100_000,key="issue:funding001",actor="sim_operator_admin")

    def test_double_entry_exact_and_chain(self):
        self.ledger.transfer("sim_customer_aaaa", "sim_customer_bbbb", 5600, key="transfer:key0001",actor="sim_owner_aaaa")
        self.assertEqual(self.ledger.balance("sim_customer_aaaa").poisha, 94400)
        self.assertEqual(self.ledger.balance("sim_customer_bbbb").poisha, 5600)
        proof=self.ledger.verify()
        self.assertTrue(proof.valid, proof.mismatches)
        self.assertEqual(proof.total_credits,proof.total_debits)
        self.assertEqual(proof.count,2)

    def test_idempotency_and_conflict(self):
        a=self.ledger.transfer("sim_customer_aaaa","sim_customer_bbbb",1000,key="transfer:idem002",actor="sim_owner_aaaa")
        b=self.ledger.transfer("sim_customer_aaaa","sim_customer_bbbb",1000,key="transfer:idem002",actor="sim_owner_aaaa")
        self.assertEqual(a.event_id,b.event_id)
        self.assertEqual(self.ledger.balance("sim_customer_bbbb").poisha,1000)
        with self.assertRaises(Conflict):
            self.ledger.transfer("sim_customer_aaaa","sim_customer_bbbb",2000,key="transfer:idem002",actor="sim_owner_aaaa")

    def test_negative_balance_rejected_and_rolled_back(self):
        with self.assertRaises(InsufficientBalance):
            self.ledger.transfer("sim_customer_aaaa","sim_customer_bbbb",100_001,key="transfer:overdraw",actor="sim_owner_aaaa")
        self.assertEqual(self.ledger.balance("sim_customer_aaaa").poisha,100_000)
        self.assertEqual(self.ledger.verify().count,1)

    def test_reject_unbalanced(self):
        with self.assertRaises(InvariantError):
            self.ledger.post("bad_posting","bad:posting",[
                LedgerEntry("sim_customer_aaaa","debit",1000),
                LedgerEntry("sim_customer_bbbb","credit",1001)],actor="sim_owner_aaaa")

    def test_account_frozen(self):
        self.ledger.freeze("sim_customer_bbbb",frozen=True,actor="sim_operator_admin")
        with self.assertRaises(FrozenAccount):
            self.ledger.transfer("sim_customer_aaaa","sim_customer_bbbb",1000,key="transfer:frozen",actor="sim_owner_aaaa")
        self.ledger.freeze("sim_customer_bbbb",frozen=False,actor="sim_operator_admin")
        self.ledger.transfer("sim_customer_aaaa","sim_customer_bbbb",1000,key="transfer:unfrozen",actor="sim_owner_aaaa")
        self.assertTrue(self.ledger.verify().valid)

    def test_immutable_journal_in_local_test(self):
        with self.assertRaises(Exception):
            with self.store.transaction() as db:
                db.execute(text("DELETE FROM s2_journals"))
        self.assertTrue(self.ledger.verify().valid)

    def test_write_guard_rejects_production_host(self):
        from app.pgsandbox.guard import assert_sandbox_target
        os.environ["SLICKK_PG_SANDBOX"]="true"
        try:
            with self.assertRaises(UnauthorizedEnvironment):
                assert_sandbox_target("postgresql://user:pw@bank.example:5432/live")
        finally:
            os.environ.pop("SLICKK_PG_SANDBOX",None)
