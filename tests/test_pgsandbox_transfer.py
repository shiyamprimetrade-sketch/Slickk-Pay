"""Owner authorization, synthetic velocity, merchant fees and exact amounts."""
import tempfile
import unittest
from pathlib import Path
from app.pgsandbox import SandboxStore, LedgerService
from app.pgsandbox.transfers import TransferService, MerchantSandboxTransfer
from app.pgsandbox.controls import LimitProfile
from app.pgsandbox.errors import RateLimit, AuthorizationError, Conflict, MissingRecord


class TransferV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="sim-transfer-")
        self.addCleanup(self.tmp.cleanup)
        self.store=SandboxStore("sqlite+pysqlite:///"+str(Path(self.tmp.name)/"test.db"),local_test=True)
        self.addCleanup(self.store.dispose)
        self.ledger=LedgerService(self.store)
        for aid,owner,kind in [
            ("sim_issuer_primary","sim_owner_issuer","sim_issuer"),
            ("sim_customer_alpha","sim_owner_alpha","customer"),
            ("sim_customer_bravo","sim_owner_bravo","customer"),
            ("sim_merchant_shop","sim_owner_shop","merchant"),
            ("sim_platform_rev","sim_owner_platform","platform_revenue")]:
            self.ledger.open_account(aid,owner,kind)
        self.ledger.transfer("sim_issuer_primary","sim_customer_alpha",100_000,key="issue:customer0001",actor="sim_operator_admin")
        self.transfers=TransferService(self.ledger,limits=LimitProfile("pilot_low_risk",10000,25000,2))
        self.merchant=MerchantSandboxTransfer(self.ledger,revenue_account="sim_platform_rev")

    def test_transfer_disclosed_free(self):
        r=self.transfers.send(actor="sim_owner_alpha",sender="sim_customer_alpha",
                              recipient="sim_customer_bravo",amount_poisha=5000,key="transfer:one0001")
        self.assertEqual(r.fee_poisha,0)
        self.assertEqual(self.ledger.balance("sim_customer_bravo").poisha,5000)
        self.assertTrue(self.ledger.verify().valid)

    def test_duplicate_does_not_reapply_velocity(self):
        r=self.transfers.send(actor="sim_owner_alpha",sender="sim_customer_alpha",
                              recipient="sim_customer_bravo",amount_poisha=5000,key="transfer:two0001")
        other=self.transfers.send(actor="sim_owner_alpha",sender="sim_customer_alpha",
                              recipient="sim_customer_bravo",amount_poisha=5000,key="transfer:two0001")
        self.assertEqual(r.event_id,other.event_id)
        self.assertEqual(self.ledger.balance("sim_customer_bravo").poisha,5000)
        with self.assertRaises(Conflict):
            self.transfers.send(actor="sim_owner_alpha",sender="sim_customer_alpha",
                              recipient="sim_customer_bravo",amount_poisha=6000,key="transfer:two0001")

    def test_daily_count_atomic(self):
        for suffix in ("aaa", "bbb"):
            self.transfers.send(actor="sim_owner_alpha",sender="sim_customer_alpha",
                    recipient="sim_customer_bravo",amount_poisha=1000,key="transfer:limit"+suffix+"1")
        with self.assertRaises(RateLimit):
            self.transfers.send(actor="sim_owner_alpha",sender="sim_customer_alpha",
                    recipient="sim_customer_bravo",amount_poisha=1000,key="transfer:limitccc1")
        self.assertTrue(self.ledger.verify().valid)

    def test_sender_ownership_enforced(self):
        with self.assertRaises(AuthorizationError):
            self.transfers.send(actor="sim_owner_bravo",sender="sim_customer_alpha",
                    recipient="sim_customer_bravo",amount_poisha=1000,key="transfer:stolen001")

    def test_merchant_fee_never_creates_value(self):
        receipt=self.merchant.capture(customer_owner="sim_owner_alpha",customer_account="sim_customer_alpha",
            merchant_account="sim_merchant_shop",amount_poisha=10000,key="merchant:purchase001")
        self.assertEqual(self.ledger.balance("sim_merchant_shop").poisha,9955)
        self.assertEqual(self.ledger.balance("sim_platform_rev").poisha,45)
        self.assertTrue(self.ledger.verify().valid)
        self.merchant.reverse(original_key="merchant:purchase001",reversal_key="merchant:refund001",
                              operator="sim_operator_admin")
        self.assertEqual(self.ledger.balance("sim_customer_alpha").poisha,100_000)
        self.assertEqual(self.ledger.balance("sim_merchant_shop").poisha,0)
        self.assertTrue(self.ledger.verify().valid)

if __name__=="__main__": unittest.main()
