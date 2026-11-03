"""Financial cash-handling invariants, fictional balances only."""
import tempfile
import unittest
from pathlib import Path
from app.pgsandbox import SandboxStore, LedgerService
from app.pgsandbox.cash import SandboxCashDesk
from app.pgsandbox.errors import Conflict, AuthorizationError, LiquidityError, StateError


class CashV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="sim-cash-")
        self.addCleanup(self.tmp.cleanup)
        self.store=SandboxStore("sqlite+pysqlite:///"+str(Path(self.tmp.name)/"test.db"),local_test=True)
        self.addCleanup(self.store.dispose)
        self.ledger=LedgerService(self.store)
        for aid,owner,kind in [
            ("sim_issuer_primary","sim_owner_issuer","sim_issuer"),
            ("sim_treasury_bank","sim_owner_treasury","platform_treasury"),
            ("sim_platform_revenue","sim_owner_platform","platform_revenue"),
            ("sim_customer_alpha","sim_owner_alpha","customer"),
            ("sim_agent_float_one","sim_owner_agent_one","agent_float"),
            ("sim_agent_commission_one","sim_owner_agent_one","agent_commission")]:
            self.ledger.open_account(aid,owner,kind)
        self.ledger.transfer("sim_issuer_primary","sim_customer_alpha",100_000,key="issue:test_customer",actor="sim_operator_admin")
        self.ledger.transfer("sim_issuer_primary","sim_agent_float_one",100_000,key="issue:test_float",actor="sim_operator_admin")
        self.ledger.transfer("sim_issuer_primary","sim_treasury_bank",100_000,key="issue:test_treasury",actor="sim_operator_admin")
        self.cash=SandboxCashDesk(self.ledger,platform_revenue="sim_platform_revenue",
            platform_treasury="sim_treasury_bank",agent_commission_lookup={"sim_agent_float_one":"sim_agent_commission_one"})
        self.cash.set_agent_cash(agent_actor="sim_owner_agent_one",agent_account="sim_agent_float_one",cash_poisha=50_000,ceiling_poisha=200_000)

    def test_cashin_correct_and_idempotent(self):
        a=self.cash.create(agent_actor="sim_owner_agent_one",agent_account="sim_agent_float_one",
            customer_account="sim_customer_alpha",request_id="sim_req_cash_in_0001",direction="cash_in",principal=20_000)
        result=self.cash.confirm_cashin(customer_actor="sim_owner_alpha",request_id=a.request.request_id,customer_token=a.token)
        self.assertEqual(result.state,"completed")
        self.assertEqual(self.cash.confirm_cashin(customer_actor="sim_owner_alpha",request_id=a.request.request_id,customer_token=a.token).state,"completed")
        self.assertEqual(self.ledger.balance("sim_customer_alpha").poisha,120_000)
        self.assertEqual(self.ledger.balance("sim_agent_float_one").poisha,80_000)
        self.assertEqual(self.cash.inventory("sim_agent_float_one").cash_poisha,70_000)
        self.assertEqual(self.ledger.balance("sim_agent_commission_one").poisha,30)
        self.assertTrue(self.ledger.verify().valid,self.ledger.verify().mismatches)

    def test_cashout_reserve_approve_complete(self):
        a=self.cash.create(agent_actor="sim_owner_agent_one",customer_actor="sim_owner_alpha",
            agent_account="sim_agent_float_one",customer_account="sim_customer_alpha",
            request_id="sim_req_cash_out_0001",direction="cash_out",principal=20_000)
        self.assertEqual(a.request.state,"reserved")
        q=self.cash.quote("cash_out",20_000)
        self.assertEqual(q.customer_fee,220)
        self.assertEqual(q.commission,110)
        self.assertEqual(self.ledger.balance("sim_customer_alpha").poisha,100_000 - 20_220)
        self.cash.approve_cashout(customer_actor="sim_owner_alpha",request_id=a.request.request_id,customer_token=a.token)
        result=self.cash.complete_cashout(agent_actor="sim_owner_agent_one",request_id=a.request.request_id,handover_reference="cashout:handover0001")
        self.assertEqual(result.state,"completed")
        self.assertEqual(self.cash.inventory("sim_agent_float_one").cash_poisha,30_000)
        self.assertEqual(self.ledger.balance("sim_agent_float_one").poisha,120_000)
        self.assertEqual(self.ledger.balance("sim_platform_revenue").poisha,110)
        self.assertTrue(self.ledger.verify().valid,self.ledger.verify().mismatches)

    def test_cancel_releases_reservation(self):
        a=self.cash.create(agent_actor="sim_owner_agent_one",customer_actor="sim_owner_alpha",
            agent_account="sim_agent_float_one",customer_account="sim_customer_alpha",
            request_id="sim_req_cancel_0001",direction="cash_out",principal=10_000)
        self.cash.cancel(actor="sim_owner_alpha",request_id=a.request.request_id,reason="customer_declined")
        self.assertEqual(self.ledger.balance("sim_customer_alpha").poisha,100_000)
        self.assertEqual(self.cash.request(a.request.request_id).state,"cancelled")
        with self.assertRaises(StateError):
            self.cash.complete_cashout(agent_actor="sim_owner_agent_one",request_id=a.request.request_id,handover_reference="cashout:invalid0001")
        self.assertTrue(self.ledger.verify().valid)

    def test_requires_independent_customer(self):
        with self.assertRaises(AuthorizationError):
            self.cash.create(agent_actor="sim_owner_agent_one",agent_account="sim_agent_float_one",
                customer_account="sim_customer_alpha",request_id="sim_req_no_owner_001",
                direction="cash_out",principal=10_000)
        self.assertEqual(self.ledger.balance("sim_customer_alpha").poisha,100_000)

    def test_wrong_token_rollback(self):
        a=self.cash.create(agent_actor="sim_owner_agent_one",agent_account="sim_agent_float_one",
            customer_account="sim_customer_alpha",request_id="sim_req_bad_token_001",direction="cash_in",principal=10_000)
        with self.assertRaises(AuthorizationError):
            self.cash.confirm_cashin(customer_actor="sim_owner_alpha",request_id=a.request.request_id,customer_token="not-a-real-test-token-000")
        self.assertEqual(self.cash.request(a.request.request_id).state,"awaiting")
        self.assertEqual(self.ledger.balance("sim_customer_alpha").poisha,100_000)


if __name__=="__main__":
    unittest.main()
