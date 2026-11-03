"""Provider compatibility tests. All provider HTTP calls are mocked."""
import os
import unittest
from dataclasses import replace
from unittest.mock import patch
from urllib.parse import parse_qs
import httpx
from fastapi.testclient import TestClient
from app.live import Config, create_app, _gateway_net_amount_plausible
from tests import test_live as old

class EnvironmentTests(unittest.TestCase):
    def test_new_and_old_password_aliases(self):
        for name in ("SSLCOMMERZ_STORE_PASSWD", "SSLCOMMERZ_STORE_PASSWORD"):
            with self.subTest(name=name), patch.dict(os.environ, {name:"fictional-secret"}, clear=True):
                self.assertEqual(Config.from_env().gateway_store_password, "fictional-secret")
                self.assertFalse(Config.from_env().enabled)
    def test_conflicting_passwords_fail(self):
        with patch.dict(os.environ, {"SSLCOMMERZ_STORE_PASSWD":"fictional-a",
                                    "SSLCOMMERZ_STORE_PASSWORD":"fictional-b"}, clear=True):
            with self.assertRaises(ValueError): Config.from_env()
    def test_conflicting_gateway_flags_fail(self):
        cases = ({"SSLCOMMERZ_IS_SANDBOX":"false"},
                 {"SSLCOMMERZ_IS_SANDBOX":"false","SLICKK_GATEWAY_LIVE":"false"},
                 {"SSLCOMMERZ_IS_SANDBOX":"true","SLICKK_GATEWAY_LIVE":"true"},
                 {"SSLCOMMERZ_IS_SANDBOX":"invalid"},
                 {"SLICKK_GATEWAY_LIVE":"invalid"})
        for values in cases:
            with self.subTest(values=values), patch.dict(os.environ,values,clear=True):
                with self.assertRaises(ValueError): Config.from_env()
    def test_gateway_live_requires_full_startup_gate(self):
        with patch.dict(os.environ, {"SSLCOMMERZ_IS_SANDBOX":"false","SLICKK_GATEWAY_LIVE":"true"}, clear=True):
            cfg=Config.from_env()
            self.assertTrue(cfg.gateway_live)
            self.assertFalse(cfg.enabled)
            with self.assertRaises(ValueError): cfg.validate()
    def test_callback_prefix_is_allowlisted(self):
        with self.assertRaises(ValueError): Config(callback_prefix="https://evil.example/ipn").validate()
    def test_gateway_net_is_never_greater_than_gross(self):
        self.assertTrue(_gateway_net_amount_plausible("2437.50",250000))
        self.assertTrue(_gateway_net_amount_plausible(None,250000))
        for bad in ("2500.01","0","NaN","2.345","-1.00"):
            with self.subTest(bad=bad): self.assertFalse(_gateway_net_amount_plausible(bad,250000))

class CallbackTests(unittest.TestCase):
    setUp=old.LiveCheckoutTests.setUp
    checkout=old.LiveCheckoutTests.checkout
    def test_aliases_and_verified_ipn(self):
        self.cfg=replace(self.cfg,callback_prefix="/v1/payments")
        self.client=TestClient(create_app(self.cfg,client_factory=lambda:httpx.Client(transport=self.transport)))
        response=self.checkout()
        self.assertEqual(response.status_code,201)
        data=parse_qs(self.gateway_calls[0].content.decode())
        for key,end in {"success_url":"success","fail_url":"fail","cancel_url":"cancel","ipn_url":"ipn"}.items():
            self.assertEqual(data[key],["https://payments.example.test/v1/payments/"+end])
        for end in ("success","fail","cancel"):
            self.assertEqual(self.client.get("/v1/payments/"+end).status_code,200)
        ipn=self.client.post("/v1/payments/ipn",data={
            "status":"VALID","tran_id":self.transaction_id,"val_id":"fixture-val-id"})
        self.assertEqual(ipn.status_code,200)
        self.assertEqual(ipn.json()["status"],"paid")
    def test_mismatched_store_amount_is_not_paid(self):
        self.checkout()
        self.validation_override={"store_amount":"120.00"}
        r=self.client.post("/v1/payments/ipn",data={
            "status":"VALID","tran_id":self.transaction_id,"val_id":"fixture-val-id"})
        self.assertFalse(r.json()["verified"])
        order=self.client.get("/v1/orders/order-test-0001",headers=self.auth)
        self.assertEqual(order.json()["status"],"pending_payment")
    def test_browser_return_and_wallet_refill_cannot_credit_balance(self):
        self.assertEqual(self.checkout({**old.sample(),"product_name":"Merchant Wallet Refill",
                          "product_category":"Digital Wallet"}).status_code,422)
        self.assertEqual(len(self.gateway_calls),0)
        self.checkout()
        self.assertEqual(self.client.post("/v1/payments/success").status_code,200)
        order=self.client.get("/v1/orders/order-test-0001",headers=self.auth)
        self.assertEqual(order.json()["status"],"pending_payment")

if __name__=="__main__": unittest.main()
