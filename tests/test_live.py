"""Live checkout integration tests use mocked gateway HTTP only; ZERO real transactions."""
import tempfile
import unittest
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.live import Config, create_app


KEY = "sandbox-testing-secret-key-long-enough-00000000"
GATEWAY_HOST = "sandbox.sslcommerz.com"
VALID_URL = f"https://{GATEWAY_HOST}/gwprocess/v4/gw.php?Q=test"


def sample(order_ref="order-test-0001", amount="100.00"):
    return {"order_ref": order_ref, "amount_bdt": amount, "product_name": "Testing", "product_category": "general",
            "customer_name": "Example Customer", "customer_email": "example@example.com", "customer_phone": "01700000000"}


class LiveCheckoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_url = "sqlite+pysqlite:///" + str(Path(self.temp.name) / "checkout.db")
        self.gateway_calls = []
        self.validation_override = {}
        self.initiation_override = {}

        def mock_handler(request):
            self.gateway_calls.append(request)
            self.assertEqual(request.url.host, GATEWAY_HOST)
            if request.method == "POST":
                assert "gwprocess/v4/api.php" in str(request.url)
                return httpx.Response(200, json={"status": "SUCCESS", "GatewayPageURL": VALID_URL,
                                                  "sessionkey": "gateway-session-123"} | self.initiation_override)
            q = dict(request.url.params)
            return httpx.Response(200, json={"status": "VALID", "val_id": q["val_id"],
                                              "tran_id": self.transaction_id, "amount": "100.00",
                                              "currency": "BDT", "risk_level": "0",
                                              "bank_tran_id": "provider-bank-123", "store_id": "merchant-test"} | self.validation_override)
        self.transport = httpx.MockTransport(mock_handler)
        self.cfg = Config(environment="staging", enabled=True, gateway_live=False,
                          api_key=KEY, gateway_store_id="merchant-test", gateway_store_password="fake-password",
                          public_base_url="https://payments.example.test", database_url=self.db_url)
        self.client = TestClient(create_app(self.cfg, client_factory=lambda: httpx.Client(transport=self.transport)))
        self.auth = {"X-Slickk-Api-Key": KEY}

    def checkout(self, body=None):
        result = self.client.post("/v1/checkouts", json=body or sample(), headers=self.auth)
        if result.status_code == 201:
            self.transaction_id = result.json()["transaction_id"]
        return result

    def send_ipn(self, **kwargs):
        return self.client.post("/v1/gateway/ipn", data={"status": "VALID", "tran_id": self.transaction_id,
                                                       "val_id": "valid-token-001"} | kwargs)

    def test_auth_and_demo_routes_absent(self):
        self.assertEqual(self.client.post("/v1/checkouts", json=sample()).status_code, 401)
        self.assertEqual(self.client.post("/v1/checkouts", json=sample(), headers={"X-Slickk-Api-Key":"bad"}).status_code, 401)
        self.assertEqual(self.client.post("/api/demo/reset").status_code, 404)
        self.assertEqual(self.client.post("/api/transfers").status_code, 404)
        self.assertEqual(self.client.post("/api/credit/simulate").status_code, 404)
        self.assertEqual(self.client.get("/readyz").status_code, 200)

    def test_init_and_idempotency_and_order_status(self):
        first = self.checkout()
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.json()["status"], "pending_payment")
        self.assertEqual(first.json()["gateway_url"], VALID_URL)
        self.assertEqual(len(self.gateway_calls), 1)
        self.assertEqual(self.checkout().json()["transaction_id"], self.transaction_id)
        self.assertEqual(len(self.gateway_calls), 1)
        order = self.client.get("/v1/orders/order-test-0001", headers=self.auth)
        self.assertEqual(order.json()["status"], "pending_payment")
        self.assertEqual(self.checkout(sample(amount="120")).status_code, 409)

    def test_amount_limits_and_no_provider_call(self):
        for value in ("0", "-1", "9.99", "500000.01", "NaN", "abc", "1.111"):
            with self.subTest(value=value):
                self.assertEqual(self.checkout(sample(amount=value)).status_code, 422)
        self.assertEqual(len(self.gateway_calls), 0)

    def test_valid_ipn_paid_once_and_false_callbacks_not_trusted(self):
        self.checkout()
        fake = self.client.post("/v1/gateway/ipn", data={"status": "FAILED", "tran_id": self.transaction_id})
        self.assertEqual(fake.json()["verified"], False)
        self.assertEqual(self.client.get("/v1/orders/order-test-0001", headers=self.auth).json()["status"], "pending_payment")
        r = self.send_ipn()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "paid")
        self.assertEqual(self.send_ipn().json()["status"], "paid")
        self.assertEqual(len(self.gateway_calls), 2)  # one session, one validation only
        self.assertEqual(self.client.get("/v1/orders/order-test-0001", headers=self.auth).json()["status"], "paid")
        return_response = self.client.post("/v1/gateway/return/fail")
        self.assertEqual(return_response.status_code, 200)
        self.assertEqual(self.client.get("/v1/orders/order-test-0001", headers=self.auth).json()["status"], "paid")

    def test_amount_mismatch_never_marks_paid(self):
        self.checkout()
        self.validation_override = {"amount": "5.00"}
        self.assertEqual(self.send_ipn().json()["verified"], False)
        self.assertEqual(self.client.get("/v1/orders/order-test-0001", headers=self.auth).json()["status"], "pending_payment")

    def test_transaction_mismatch_never_marks_paid(self):
        self.checkout()
        self.validation_override = {"tran_id": "other-transaction"}
        self.assertEqual(self.send_ipn().json()["verified"], False)
        self.assertEqual(self.client.get("/v1/orders/order-test-0001", headers=self.auth).json()["status"], "pending_payment")

    def test_risky_payment_hold(self):
        self.checkout()
        self.validation_override = {"risk_level": "1"}
        self.assertEqual(self.send_ipn().json()["status"], "risk_review")
        self.assertEqual(self.client.get("/v1/orders/order-test-0001", headers=self.auth).json()["status"], "risk_review")

    def test_unapproved_gateway_redirect_fails_closed(self):
        self.initiation_override = {"GatewayPageURL": "https://example.attacker.test/collect"}
        self.assertEqual(self.checkout().status_code, 502)
        self.assertEqual(self.client.get("/v1/orders/order-test-0001", headers=self.auth).json()["status"], "initiation_unknown")
        self.assertEqual(self.checkout().status_code, 409)
        self.assertEqual(len(self.gateway_calls), 1)

    def test_bad_content_type_and_large_ipn(self):
        self.checkout()
        self.assertEqual(self.client.post("/v1/gateway/ipn", json={"status": "VALID"}).status_code, 415)
        self.assertEqual(self.client.post("/v1/gateway/ipn", data={"pad":"X"*17000}).status_code, 413)

    def test_provider_timeout_does_not_change_payment_status(self):
        self.checkout()
        self.validation_override = {"status": "INVALID_TRANSACTION"}
        self.assertEqual(self.send_ipn().json()["verified"], False)
        self.assertEqual(self.client.get("/v1/orders/order-test-0001", headers=self.auth).json()["status"], "pending_payment")


class ConfigurationTests(unittest.TestCase):
    def test_disabled_default(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = Config(database_url="sqlite+pysqlite:///" + temp + "/disabled.db")
            client = TestClient(create_app(cfg))
            self.assertEqual(client.get("/healthz").status_code, 200)
            self.assertEqual(client.get("/readyz").status_code, 503)
            self.assertEqual(client.post("/v1/checkouts", json=sample()).status_code, 503)

    def test_live_must_be_explicit_and_on_postgres(self):
        with self.assertRaises(ValueError):
            Config(enabled=True, gateway_live=True).validate()
        with self.assertRaises(ValueError):
            Config(environment="production", enabled=True, gateway_live=True,
                   regulatory_confirmation=True, api_key=KEY, gateway_store_id="id", gateway_store_password="pwd",
                   public_base_url="https://payments.example.com").validate()
        with self.assertRaises(ValueError):
            Config(environment="staging", enabled=True, api_key=KEY, gateway_store_id="id",
                   gateway_store_password="pwd", public_base_url="http://public.example.com").validate()
        with self.assertRaises(ValueError):
            Config(environment="staging", enabled=True, api_key="weak", gateway_store_id="id", gateway_store_password="pwd").validate()


if __name__ == "__main__":
    unittest.main()
