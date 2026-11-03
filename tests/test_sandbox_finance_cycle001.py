"""No live credentials, user PII, network calls, or physical currency in this suite."""
import concurrent.futures
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.sandboxfinance.identity import (
    IdentityError, SyntheticRegistry, synthetic_customer, synthetic_agent,
    normalize_bd_phone, masked_phone,
)
from app.sandboxfinance.ledger import (
    SandboxLedger, Posting, InsufficientFunds, DuplicateReference,
    InvariantViolation, AccountBlocked, LedgerError,
)
from app.sandboxfinance.pricing import initial_pilot, bdt_to_poisha, poisha_to_bdt, PriceError
from app.sandboxfinance.workflows import (
    CashDesk, CustomerTransfers, prepare_synthetic_system, WorkflowError,
    LiquidityError, ConsentError, StateConflict,
)
from app.sandboxfinance.api import build_sandbox_app


class Scenario(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = str(Path(self.tmp.name) / "test-finance.sqlite3")
        self.ledger = SandboxLedger(self.db_path)
        self.registry = SyntheticRegistry()
        for party in (
            synthetic_customer("maria", "01710123456", "Maria Sandbox"),
            synthetic_customer("nabil", "01810123456", "Nabil Sandbox"),
            synthetic_agent("agent1", "01910123456", "Agent One"),
        ):
            self.registry.register(party)
            self.registry.approve_sandbox(party.party_id)
        prepare_synthetic_system(self.ledger, self.registry)
        self.cash = CashDesk(self.ledger, self.registry)
        self.transfers = CustomerTransfers(self.ledger, self.registry)
        self.ledger.synthetic_issue("sim_wallet_maria", 1_000_000, reference="fund-maria-0001")
        self.ledger.synthetic_issue("sim_float_agent1", 2_000_000, reference="fund-agent-0001")
        self.ledger.synthetic_issue("sim_platform_treasury", 100_000, reference="fund-treasury-1")
        self.cash.register_agent_cash("sim_agent1", reported_cash_poisha=2_000_000,
                                      limit_poisha=6_000_000)

    def test_exact_bdt_and_quotes(self):
        self.assertEqual(bdt_to_poisha("10.99"), 1099)
        self.assertEqual(poisha_to_bdt(1099), "10.99")
        self.assertEqual(initial_pilot().quote("cash_out", 100_000).customer_fee, 1099)
        self.assertEqual(initial_pilot().quote("cash_out", 100_000).agent_commission, 550)
        self.assertEqual(initial_pilot().quote("cash_in", 100_000).agent_commission, 150)
        for x in (1.2, "NaN", "Infinity", "1e5", "1.001", "-0.01"):
            with self.subTest(x=x), self.assertRaises(PriceError):
                bdt_to_poisha(x)
        self.assertEqual(initial_pilot().quote("customer_transfer", 50_000).customer_fee, 0)
        self.assertFalse(initial_pilot().approved_for_production)

    def test_transfer_is_atomic_and_idempotent(self):
        receipt = self.transfers.send(sender_id="sim_maria",recipient_id="sim_nabil",principal=30_000,
                                      reference="send-001",customer_confirmed=True)
        again = self.transfers.send(sender_id="sim_maria",recipient_id="sim_nabil",principal=30_000,
                                    reference="send-001",customer_confirmed=True)
        self.assertEqual(receipt.event_id, again.event_id)
        self.assertEqual(self.ledger.account("sim_wallet_maria").balance_poisha, 970_000)
        self.assertEqual(self.ledger.account("sim_wallet_nabil").balance_poisha, 30_000)
        with self.assertRaises(DuplicateReference):
            self.transfers.send(sender_id="sim_maria",recipient_id="sim_nabil",principal=10_000,
                                reference="send-001",customer_confirmed=True)
        self.assertEqual(self.ledger.verify()["net_poisha"], 0)

    def test_insufficient_balance_no_mutation(self):
        prior = self.ledger.verify()["events"]
        with self.assertRaises(InsufficientFunds):
            self.transfers.send(sender_id="sim_nabil",recipient_id="sim_maria",principal=1000,
                                reference="send-002",customer_confirmed=True)
        self.assertEqual(self.ledger.verify()["events"], prior)

    def test_invalid_or_frozen_accounts(self):
        self.ledger.freeze("sim_wallet_maria")
        with self.assertRaises(AccountBlocked):
            self.transfers.send(sender_id="sim_maria", recipient_id="sim_nabil", principal=1000,
                                reference="send-003", customer_confirmed=True)
        self.ledger.freeze("sim_wallet_maria", False)
        self.assertFalse(self.ledger.account("sim_wallet_maria").frozen)
        with self.assertRaises(InvariantViolation):
            self.ledger.post(operation="bad_test",idempotency_key="bad-001",postings=[
                Posting("sim_wallet_maria", "debit", 11), Posting("sim_wallet_nabil", "credit", 10)])
        with self.assertRaises(sqlite3.IntegrityError), sqlite3.connect(self.db_path) as db:
            db.execute("DELETE FROM sim_postings")

    def test_concurrent_spend_never_overdraws(self):
        def task(n):
            try:
                self.transfers.send(sender_id="sim_maria",recipient_id="sim_nabil",
                                    principal=600_000,reference=f"concurrent-{n}",customer_confirmed=True)
                return True
            except InsufficientFunds:
                return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            statuses = list(pool.map(task, range(3)))
        self.assertEqual(statuses.count(True), 1)
        self.assertEqual(self.ledger.verify()["net_poisha"], 0)

    def test_cash_in_flow(self):
        request = self.cash.request_cash_in("sim_maria", "sim_agent1", 100_000)
        with self.assertRaises(ConsentError):
            self.cash.confirm(request.request.request_id,agent_id="sim_agent1",
                              customer_token="wrong",cash_handover_confirmed=True)
        completed = self.cash.confirm(request.request.request_id,agent_id="sim_agent1",
                                      customer_token=request.customer_token,cash_handover_confirmed=True)
        self.assertEqual(completed.state, "completed")
        self.assertEqual(self.ledger.account("sim_wallet_maria").balance_poisha, 1_100_000)
        self.assertEqual(self.ledger.account("sim_float_agent1").balance_poisha, 1_900_000)
        self.assertEqual(self.ledger.account("sim_commission_agent1").balance_poisha, 150)
        self.assertEqual(self.cash.cash_available("sim_agent1"), 2_100_000)
        with self.assertRaises(StateConflict):
            self.cash.confirm(request.request.request_id,agent_id="sim_agent1",
                              customer_token=request.customer_token,cash_handover_confirmed=True)
        self.assertEqual(self.ledger.verify()["net_poisha"], 0)

    def test_cash_out_reservation_confirmation(self):
        request = self.cash.request_cash_out("sim_maria", "sim_agent1", 100_000)
        self.assertEqual(request.request.state, "reserved")
        self.assertEqual(self.ledger.account("sim_wallet_maria").balance_poisha, 898_901)
        self.assertEqual(self.cash.cash_available("sim_agent1"), 2_000_000)
        completed = self.cash.confirm(request.request.request_id,agent_id="sim_agent1",
                                      customer_token=request.customer_token,cash_handover_confirmed=True)
        self.assertEqual(completed.state, "completed")
        self.assertEqual(self.ledger.account("sim_platform_revenue").balance_poisha, 549)
        self.assertEqual(self.ledger.account("sim_commission_agent1").balance_poisha, 550)
        self.assertEqual(self.ledger.account("sim_float_agent1").balance_poisha, 2_100_000)
        self.assertEqual(self.cash.cash_available("sim_agent1"), 1_900_000)
        self.assertEqual(self.ledger.verify()["net_poisha"], 0)

    def test_cashout_cancel_restores_reserved_balance(self):
        request = self.cash.request_cash_out("sim_maria", "sim_agent1", 50_000)
        cancelled = self.cash.cancel(request.request.request_id, actor_id="sim_maria")
        self.assertEqual(cancelled.state, "cancelled")
        self.assertEqual(self.ledger.account("sim_wallet_maria").balance_poisha, 1_000_000)
        with self.assertRaises(StateConflict):
            self.cash.confirm(request.request.request_id, agent_id="sim_agent1",
                              customer_token=request.customer_token, cash_handover_confirmed=True)
        self.assertEqual(self.ledger.verify()["net_poisha"], 0)

    def test_cashout_rejects_no_inventory(self):
        self.cash.register_agent_cash("sim_agent1", reported_cash_poisha=0, limit_poisha=100_000)
        with self.assertRaises(LiquidityError):
            self.cash.request_cash_out("sim_maria", "sim_agent1", 30_000)

    def test_atomic_cashout_rollback_on_audit_failure(self):
        request = self.cash.request_cash_out("sim_maria", "sim_agent1", 100_000)
        before_events = self.ledger.verify()["events"]
        before_float = self.ledger.account("sim_float_agent1").balance_poisha
        before_cash = self.cash.cash_available("sim_agent1")
        escrow = "sim_escrow_" + request.request.request_id.split("_")[-1]
        before_escrow = self.ledger.account(escrow).balance_poisha
        with sqlite3.connect(self.db_path) as db:
            db.execute("CREATE TRIGGER test_block_completed BEFORE INSERT ON sim_cash_audit "
                       "WHEN NEW.new_state='completed' BEGIN SELECT RAISE(ABORT,'injected failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.cash.confirm(request.request.request_id, agent_id="sim_agent1",
                              customer_token=request.customer_token,
                              cash_handover_confirmed=True)
        self.assertEqual(self.cash.status(request.request.request_id).state, "reserved")
        self.assertEqual(self.ledger.verify()["events"], before_events)
        self.assertEqual(self.cash.cash_available("sim_agent1"), before_cash)
        self.assertEqual(self.ledger.account("sim_float_agent1").balance_poisha, before_float)
        self.assertEqual(self.ledger.account(escrow).balance_poisha, before_escrow)
        with sqlite3.connect(self.db_path) as db:
            db.execute("DROP TRIGGER test_block_completed")
        self.assertEqual(self.cash.confirm(request.request.request_id, agent_id="sim_agent1",
                                          customer_token=request.customer_token,
                                          cash_handover_confirmed=True).state, "completed")
        self.assertEqual(self.ledger.verify()["net_poisha"], 0)

    def test_atomic_cashin_rollback_on_audit_failure(self):
        request = self.cash.request_cash_in("sim_maria", "sim_agent1", 50_000)
        prior_balance = self.ledger.account("sim_wallet_maria").balance_poisha
        prior_events = self.ledger.verify()["events"]
        with sqlite3.connect(self.db_path) as db:
            db.execute("CREATE TRIGGER test_block_cash_in BEFORE INSERT ON sim_cash_audit "
                       "WHEN NEW.new_state='completed' BEGIN SELECT RAISE(ABORT,'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.cash.confirm(request.request.request_id, agent_id="sim_agent1",
                              customer_token=request.customer_token,
                              cash_handover_confirmed=True)
        self.assertEqual(self.cash.status(request.request.request_id).state, "awaiting_cash")
        self.assertEqual(self.ledger.verify()["events"], prior_events)
        self.assertEqual(self.ledger.account("sim_wallet_maria").balance_poisha, prior_balance)

    def test_phone_normalization_and_masking(self):
        self.assertEqual(normalize_bd_phone("+8801710123456"), "01710123456")
        self.assertEqual(masked_phone("01710123456"), "017****3456")
        with self.assertRaises(IdentityError):
            normalize_bd_phone("123")
        found = self.transfers.recipient_lookup("01810123456")
        self.assertEqual(found["party_id"], "sim_nabil")
        self.assertNotIn("Nabil", found["name_masked"])

    def test_non_authorized_transfer(self):
        with self.assertRaises(ConsentError):
            self.transfers.send(sender_id="sim_maria",recipient_id="sim_nabil",principal=100,
                                reference="send-004",customer_confirmed=False)


class IsolatedAPITests(unittest.TestCase):
    def test_api_is_explicit_and_disconnected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fin.sqlite3"
            with self.assertRaises(ValueError):
                build_sandbox_app(database_path=path,explicit_local_opt_in=False,control_key="x"*40)
            app = build_sandbox_app(database_path=path,explicit_local_opt_in=True,
                                    control_key="local-sandbox-test-key-long-enough-0000")
            c = TestClient(app)
            self.assertTrue(c.get("/simulation/status").json()["simulation"])
            self.assertFalse(c.get("/simulation/status").json()["bank_connected"])
            self.assertEqual(c.post("/simulation/participants",json={"identity":"maria","role":"customer",
                "name":"Maria Sandbox","phone":"01710123456"}).status_code, 401)
            hdr = {"X-Simulation-Key": "local-sandbox-test-key-long-enough-0000"}
            result = c.post("/simulation/participants",json={"identity":"maria","role":"customer",
                "name":"Maria Sandbox","phone":"01710123456"},headers=hdr)
            self.assertEqual(result.status_code, 201)
            self.assertEqual(c.get("/simulation/journal/verify",headers=hdr).status_code, 200)
            self.assertEqual(c.get("/simulation/journal/verify",headers=hdr).json()["net_poisha"], 0)
