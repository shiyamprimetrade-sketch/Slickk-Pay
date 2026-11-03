"""Ensure previews are safely integrated into the real checkout app factory."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.live import Config, create_app
from tests.test_ops_reporting_api import AUTH_KEY, AUTH, risk_body
from tests.test_live import sample


class OperationsWiringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = "sqlite+pysqlite:///" + str(Path(self.temp.name) / "wiring.db")

    def factory(self, *, environment="staging"):
        cfg = Config(environment=environment, database_url=self.path,
                     api_key=AUTH_KEY, enabled=False)
        return TestClient(create_app(cfg))

    def test_default_checkout_is_disabled(self):
        with patch.dict(os.environ, {"SLICKK_OPS_PREVIEW_ENABLED":"false"}):
            client = self.factory()
        self.assertEqual(client.get("/healthz").status_code,200)
        self.assertEqual(client.get("/readyz").status_code,503)
        self.assertEqual(client.post("/v1/checkouts",json=sample()).status_code,503)

    def test_ops_contract_is_nonfinancial(self):
        with patch.dict(os.environ, {"SLICKK_OPS_PREVIEW_ENABLED":"false"}):
            client = self.factory()
        info = client.get("/v1/ops/contract").json()
        self.assertFalse(info["enabled"])
        self.assertFalse(info["customer_funds_movement"])
        self.assertFalse(info["loans"])

    def test_opt_in_staging_preview_does_not_enable_checkout(self):
        with patch.dict(os.environ, {"SLICKK_OPS_PREVIEW_ENABLED":"true"}):
            client = self.factory()
        self.assertEqual(client.post("/v1/ops/risk/preview",json=risk_body(),
                                     headers=AUTH).status_code,200)
        self.assertEqual(client.get("/readyz").status_code,503)
        self.assertEqual(client.post("/v1/checkouts",json=sample()).status_code,503)

    def test_production_preview_configuration_fails_closed(self):
        with patch.dict(os.environ, {"SLICKK_OPS_PREVIEW_ENABLED":"true"}):
            with self.assertRaises(ValueError):
                self.factory(environment="production")

    def test_demo_wallet_routes_absent(self):
        with patch.dict(os.environ, {"SLICKK_OPS_PREVIEW_ENABLED":"true"}):
            client = self.factory()
        self.assertEqual(client.post("/api/demo/reset").status_code,404)
        self.assertEqual(client.post("/api/credit/simulate").status_code,404)

    def test_no_api_key_rejected_when_preview_enabled(self):
        with patch.dict(os.environ, {"SLICKK_OPS_PREVIEW_ENABLED":"true"}):
            client = self.factory()
        self.assertEqual(client.post("/v1/ops/risk/preview",json=risk_body()).status_code,401)


if __name__ == "__main__":
    unittest.main()
