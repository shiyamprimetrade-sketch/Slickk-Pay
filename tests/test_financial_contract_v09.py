"""v0.9 regression tests: provider responses mocked, no actual gateway calls."""
from dataclasses import replace
import time, unittest
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.contracts import InvalidProviderForm, parse_provider_form, financial_capabilities, sign_merchant_order, merchant_order_signature_valid
from app.live import Checkout, create_app
from tests import test_live

SECRET="fictional-merchant-signature-for-tests-only-abcdefgh"

class ContractTests(unittest.TestCase):
    def test_ambiguous_forms_rejected(self):
        for raw in (b"status=VALID&status=FAILED",b"val_id=x&val%5Fid=y",
                    b"x=bad%Q1",b"badsegment",b"a=%00",b"a=\xff",b""):
            with self.subTest(raw=raw),self.assertRaises(InvalidProviderForm):
                parse_provider_form(raw)
        self.assertEqual(parse_provider_form(b"x=%2B&y="),{"x":"+","y":""})
    def test_capabilities_are_truthful(self):
        for active in (True,False):
            data=financial_capabilities(configured=active,environment="staging")
            self.assertEqual(data["merchant_checkout"]["enabled"],active)
            self.assertFalse(data["wallet_stored_value"]["enabled"])
            self.assertFalse(data["microcredit"]["enabled"])
            self.assertFalse(data["bank_settlement_reporting"]["verified"])
    def test_signed_order_binds_price_and_time(self):
        args=dict(timestamp="1730650000",order_ref="merchant-order-01",amount_poisha=10000,
                  product_name="Service",product_category="general")
        sig=sign_merchant_order(SECRET,**args)
        self.assertTrue(merchant_order_signature_valid(SECRET,signature=sig,now=1730650000,**args))
        self.assertFalse(merchant_order_signature_valid(SECRET,signature=sig,now=1730650301,**args))
        self.assertFalse(merchant_order_signature_valid(SECRET,signature=sig,now=1730650000,**(args|{"amount_poisha":10001})))

class CheckoutTests(unittest.TestCase):
    setUp=test_live.LiveCheckoutTests.setUp
    checkout=test_live.LiveCheckoutTests.checkout
    send_ipn=test_live.LiveCheckoutTests.send_ipn
    def test_ipn_duplicate_does_not_call_provider(self):
        self.checkout()
        before=len(self.gateway_calls)
        for body in ("status=VALID&status=FAILED","val_id=a&val_id=b","val_id=x%Q1"):
            r=self.client.post("/v1/payments/ipn",content=f"tran_id={self.transaction_id}&"+body,
                headers={"Content-Type":"application/x-www-form-urlencoded"})
            self.assertEqual(r.status_code,400)
        self.assertEqual(len(self.gateway_calls),before)
        self.assertFalse(self.client.get("/v1/capabilities").json()["microcredit"]["enabled"])
    def test_verified_net_stored_separately(self):
        self.checkout()
        self.validation_override={"store_amount":"96.75"}
        self.assertTrue(self.send_ipn().json()["verified"])
        eng=create_engine(self.db_url)
        with Session(eng) as db:
            o=db.scalar(select(Checkout).where(Checkout.id==self.transaction_id))
            self.assertEqual(o.amount_poisha,10000)
            self.assertEqual(o.gateway_reported_net_poisha,9675)
        eng.dispose()
        self.assertEqual(self.client.get("/v1/orders/order-test-0001",headers=self.auth).json()["provider_reported_net_bdt"],"96.75")
    def test_unsigned_or_tampered_order_blocked(self):
        self.cfg=replace(self.cfg,require_signed_orders=True,order_signing_secret=SECRET)
        self.client=TestClient(create_app(self.cfg,client_factory=lambda:httpx.Client(transport=self.transport)))
        body=test_live.sample()
        self.assertEqual(self.client.post("/v1/checkouts",json=body,headers=self.auth).status_code,401)
        ts=str(int(time.time()))
        sig=sign_merchant_order(SECRET,timestamp=ts,order_ref=body["order_ref"],amount_poisha=10000,
                                product_name=body["product_name"],product_category=body["product_category"])
        headers={**self.auth,"X-Slickk-Order-Timestamp":ts,"X-Slickk-Order-Signature":sig}
        self.assertEqual(self.client.post("/v1/checkouts",json=body|{"amount_bdt":"101.00"},headers=headers).status_code,401)
        self.assertEqual(len(self.gateway_calls),0)
        self.assertEqual(self.client.post("/v1/checkouts",json=body,headers=headers).status_code,201)
