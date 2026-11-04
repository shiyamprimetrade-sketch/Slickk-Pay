"""Real executable tests of the fictional-money customer/agent access lab."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.simaccess.clock import FrozenClock
from app.simaccess.crypto import SigningKey, KeyRing, check_pin, derive_pin
from app.simaccess.errors import LabError
from app.simaccess.identity import IdentityRegistry
from app.simaccess.store import LabStore, safe_database_path
from app.simaccess.sessions import SessionManager
from app.simaccess.service import AccessLab
from app.simaccess.api import create_local_access_app
from app.simaccess.policy import AccessPolicy
from app.simaccess.pricing import PricingEngine
from app.simaccess.risk import SyntheticRiskEngine
from app.simaccess.qr import SampleQrService
from app.simaccess.receipts import ReceiptService
from app.simaccess.offline import NetworkState, OfflineContract
from app.simaccess.device_policy import DevicePolicy, DeviceSignals
from app.simaccess.disclosures import DisclosureService
from app.simaccess.directory import AgentDirectory, default_sample_agents
from app.simaccess.conformance import ConformanceSuite
from app.simaccess.contract import ResponseContract
from app.simaccess.consistency import ConsistencyAuditor
from app.simaccess.search import ActivitySearch, ActivityQuery
from app.simaccess.faults import FaultProbe

PIN = "Sample-only-Pin-004!"
A = "sim_customer_alpha"
B = "sim_customer_beta"
AGENT = "sim_agent_alpha"
MERCHANT = "sim_merchant_alpha"
OP = "sim_operator_alpha"
DEV_A = "sim_device_cust_alpha_004"
DEV_B = "sim_device_cust_beta_004"
DEV_AGENT = "sim_device_agent_alpha_004"
DEV_MERCHANT = "sim_device_merchant_alpha_004"
DEV_OP = "sim_device_operator_alpha_004"
AT = 1_800_000_000


class LocalFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = FrozenClock(AT)
        self.env = patch.dict(os.environ, {"SLICKK_ENV":"sandbox", "SLICKK_GATEWAY_LIVE":"false",
            "SLICKK_ENABLE_CHECKOUTS":"false", "SLICKK_REGULATORY_SIGNOFF":"false",
            "SLICKK_SIM_ACCESS_ENABLED":"true"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.store = LabStore(str(Path(self.tmp.name) / "sim_access_fixture.sqlite3"), opted_in=True,clock=self.clock)
        self.keyring = KeyRing((SigningKey("sim_key_test004",bytes(range(32)),AT-60),),"sim_key_test004")
        self.lab = AccessLab(self.store,qr_keyring=self.keyring)
        self.devices = {A:DEV_A,B:DEV_B,AGENT:DEV_AGENT,MERCHANT:DEV_MERCHANT,OP:DEV_OP}
        roles = {A:"customer",B:"customer",AGENT:"agent",MERCHANT:"merchant",OP:"operator"}
        for ident,device in self.devices.items():
            self.lab.identity.enroll_fixture(actor_id=ident,role=roles[ident],label="Fixture "+roles[ident],
                                             demo_pin=PIN,sample_balance_poisha=100_000)
            self.lab.identity.enroll_device(actor_id=ident,device_id=device,label="Test Android")
        # Authenticate the default customer once; other personas log in lazily.
        # This keeps the test suite fast while retaining actual session verification.
        initial=self.lab.sessions.login(actor_id=A,device_id=DEV_A,demo_pin=PIN)
        self.auth = {A:(initial.bearer,DEV_A)}

    def ctx(self,ident=A):
        if ident not in self.auth:
            device=self.devices[ident]
            session=self.lab.sessions.login(actor_id=ident,device_id=device,demo_pin=PIN)
            self.auth[ident]=(session.bearer,device)
        bearer,device = self.auth[ident]
        return self.lab.sessions.require(bearer=bearer,device_id=device)

    def quote(self,kind="transfer",owner=A,counterpart=B,amount=100_000,ref="pilot_order_00001"):
        return self.lab.quotes.quote(context=self.ctx(owner),operation=kind,counterpart_id=counterpart,
                                      principal_poisha=amount,source_ref=ref)


class IdentityTests(LocalFixture):
    def test_identity_is_synthetic_and_not_kyc(self):
        actor=self.lab.identity.get(A)
        self.assertEqual(actor.role,"customer")
        self.assertTrue(actor.simulation)
        self.assertEqual(self.lab.capabilities.customer_auth_mode,"SYNTHETIC_FIXTURE_ONLY")

    def test_enrollment_is_idempotency_conflict(self):
        with self.assertRaises(LabError) as err:
            self.lab.identity.enroll_fixture(actor_id=A,role="customer",label="Other",demo_pin=PIN)
        self.assertEqual(err.exception.code,"CONFLICT")

    def test_device_is_hashed_and_revoke_revokes_session(self):
        result=self.lab.identity.list_devices(A)
        self.assertEqual(len(result),1)
        self.assertNotEqual(result[0].device_digest,DEV_A)
        self.assertTrue(self.lab.identity.revoke_device(actor_id=A,device_id=DEV_A))
        with self.assertRaises(LabError):
            self.ctx(A)

    def test_wrong_device_rejected(self):
        token,_=self.auth[A]
        with self.assertRaises(LabError) as err:
            self.lab.sessions.require(bearer=token,device_id=DEV_B)
        self.assertEqual(err.exception.code,"DEVICE_MISMATCH")

    def test_wrong_demo_pin_rejected(self):
        with self.assertRaises(LabError) as err:
            self.lab.sessions.login(actor_id=A,device_id=DEV_A,demo_pin="wrong-password")
        self.assertEqual(err.exception.code,"UNAUTHORIZED")

    def test_wrong_pin_locks_after_five(self):
        for _ in range(5):
            with self.assertRaises(LabError):
                self.lab.sessions.login(actor_id=A,device_id=DEV_A,demo_pin="wrong-password")
        with self.assertRaises(LabError) as err:
            self.lab.sessions.login(actor_id=A,device_id=DEV_A,demo_pin=PIN)
        self.assertEqual(err.exception.code,"RATE_LIMIT")

    def test_session_expires(self):
        self.clock.advance(901)
        with self.assertRaises(LabError) as err:
            self.ctx(A)
        self.assertEqual(err.exception.code,"SESSION_EXPIRED")

    def test_idle_timeout(self):
        self.clock.advance(301)
        with self.assertRaises(LabError) as err:
            self.ctx(A)
        self.assertEqual(err.exception.code,"SESSION_EXPIRED")

    def test_logout(self):
        bearer,device=self.auth[A]
        self.assertTrue(self.lab.sessions.logout(bearer=bearer,device_id=device))
        with self.assertRaises(LabError):
            self.ctx(A)

    def test_freeze_revokes_existing_sessions(self):
        self.lab.identity.change_state(A,state="frozen")
        with self.assertRaises(LabError):
            self.ctx(A)

    def test_no_cross_persona_access(self):
        access=AccessPolicy.decide(self.ctx(A),"balance:read",resource_owner=B)
        self.assertFalse(access.allowed)

    def test_all_money_permissions_forbidden(self):
        for operation in ("ledger:post","credit:issue","real_cash:confirm","bank:settle"):
            self.assertFalse(AccessPolicy.decide(self.ctx(A),operation).allowed)

    def test_pin_derivation_verifies_only_exact_value(self):
        salt,digest=derive_pin("synthetic-unique-secret")
        self.assertTrue(check_pin("synthetic-unique-secret",salt,digest))
        self.assertFalse(check_pin("different",salt,digest))


class PricingQuoteTests(LocalFixture):
    def test_cash_out_fee_exact(self):
        result=PricingEngine().quote("cash_out",100_000)
        self.assertEqual(result.customer_fee_poisha,1099)
        self.assertEqual(result.agent_commission_preview_poisha,550)
        self.assertFalse(result.tax_verified)

    def test_cash_in_commission_and_free_transfer(self):
        self.assertEqual(PricingEngine().quote("cash_in",100_000).agent_commission_preview_poisha,150)
        self.assertEqual(PricingEngine().quote("transfer",100_000).customer_fee_poisha,0)

    def test_merchant_processing_fee_is_not_customer_fee(self):
        disclosure=PricingEngine().quote("merchant_payment",100_000)
        self.assertEqual(disclosure.merchant_processing_fee_poisha,450)
        self.assertEqual(disclosure.customer_fee_poisha,0)

    def test_quote_is_idempotent(self):
        first=self.quote()
        second=self.quote()
        self.assertEqual(first.id,second.id)
        self.assertEqual(self.store.count("lab_quotes"),1)

    def test_quote_reference_conflict(self):
        self.quote()
        with self.assertRaises(LabError) as err:
            self.quote(amount=90_000)
        self.assertEqual(err.exception.code,"CONFLICT")

    def test_quote_rejects_non_owner(self):
        item=self.quote()
        with self.assertRaises(LabError):
            self.lab.quotes.get(self.ctx(B),item.id)

    def test_cash_out_counterpart_role(self):
        item=self.quote("cash_out",owner=A,counterpart=AGENT,ref="pilot_cash_out_001")
        self.assertEqual(item.fee_poisha,1099)
        with self.assertRaises(LabError):
            self.quote("cash_out",owner=A,counterpart=B,ref="pilot_cash_out_002")

    def test_agent_cash_in_preview(self):
        item=self.quote("cash_in",owner=AGENT,counterpart=A,ref="pilot_cash_in_001")
        self.assertEqual(item.fee_poisha,0)
        self.assertFalse(item.can_execute)

    def test_quote_review_creates_no_payment(self):
        item=self.quote()
        review=self.lab.requests.review(self.ctx(A),item.id,explicit_preview_consent=True)
        self.assertEqual(review.status,"reviewed")
        self.assertFalse(review.financial_posting)
        with self.assertRaises(LabError):
            self.lab.requests.attempt_execution(self.ctx(A),review.id)

    def test_review_idempotency(self):
        item=self.quote()
        a=self.lab.requests.review(self.ctx(A),item.id,explicit_preview_consent=True)
        b=self.lab.requests.review(self.ctx(A),item.id,explicit_preview_consent=True)
        self.assertEqual(a.id,b.id)
        self.assertEqual(self.store.count("lab_requests"),1)

    def test_review_requires_explicit_consent(self):
        item=self.quote()
        with self.assertRaises(LabError):
            self.lab.requests.review(self.ctx(A),item.id,explicit_preview_consent=False)

    def test_request_cancel_immutable(self):
        item=self.quote()
        review=self.lab.requests.review(self.ctx(A),item.id,explicit_preview_consent=True)
        cancelled=self.lab.requests.cancel(self.ctx(A),review.id)
        self.assertEqual(cancelled.status,"cancelled")
        self.assertEqual(self.lab.requests.cancel(self.ctx(A),review.id).revision,cancelled.revision)

    def test_quote_cancel_and_review_denied(self):
        item=self.quote()
        self.lab.quotes.cancel(self.ctx(A),item.id)
        with self.assertRaises(LabError):
            self.lab.requests.review(self.ctx(A),item.id,explicit_preview_consent=True)

    def test_expired_quote_rejected(self):
        item=self.quote()
        self.clock.advance(181)
        with self.assertRaises(LabError):
            self.lab.requests.review(self.ctx(A),item.id,explicit_preview_consent=True)

    def test_receipt_watermark_in_bangla(self):
        item=self.quote()
        request=self.lab.requests.review(self.ctx(A),item.id,explicit_preview_consent=True)
        receipt=self.lab.receipts.for_request(self.ctx(A),request.id,"bn")
        self.assertFalse(receipt.payment_proof)
        self.assertIn("নমুনা",receipt.public()["watermark"])

    def test_contribution_loss_visible(self):
        result=PricingEngine().project_agent_margin(100_000,"cash_in",provider_fee=20,operations_cost=50)
        self.assertLess(result["contribution_poisha"],0)

    def test_fee_disclosure_warns_tax(self):
        page=DisclosureService().for_amount("cash_out",100_000,"en")
        self.assertFalse(page.amount_is_final)
        self.assertIn("tax",str(page.public()).lower())

    def test_cross_persona_request_list_is_scoped(self):
        item=self.quote()
        self.lab.requests.review(self.ctx(A),item.id,explicit_preview_consent=True)
        self.assertEqual(self.lab.requests.list(self.ctx(B)),[])


if __name__=="__main__":
    unittest.main()
