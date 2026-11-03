"""Deployment guardrails; does not require a Render or provider account."""
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

from app.live import Config, _database_url, _gateway_url_valid, create_app


ROOT = Path(__file__).resolve().parents[1]


class RenderReadinessTests(unittest.TestCase):
    def test_render_postgres_database_url_normalization(self):
        for raw in ("postgres://alice:pa%24ss@internal:5432/slickk",
                    "postgresql://alice:pa%24ss@internal:5432/slickk",
                    "postgresql+psycopg://alice:pa%24ss@internal:5432/slickk"):
            with self.subTest(raw=raw.split(":")[0]):
                parsed = _database_url(raw)
                self.assertEqual(parsed.drivername, "postgresql+psycopg")
                self.assertEqual(parsed.password, "pa$ss")
        self.assertEqual(_database_url("sqlite+pysqlite:///:memory:").drivername, "sqlite+pysqlite")

    def test_production_without_signoff_fails_closed_even_in_gateway_sandbox(self):
        with self.assertRaisesRegex(ValueError, "regulatory signoff"):
            Config(environment="production", enabled=True, gateway_live=False,
                   api_key="x" * 48, gateway_store_id="store", gateway_store_password="pass",
                   public_base_url="https://example.com", database_url="postgresql://db/db").validate()

    def test_checkout_gateway_redirect_must_not_have_unusual_port_or_path(self):
        host = "sandbox.sslcommerz.com"
        self.assertTrue(_gateway_url_valid(f"https://{host}/gwprocess/v4/gw.php?Q=test", host))
        for url in (f"https://{host}:444/gwprocess/v4/gw.php", f"https://{host}/not-checkout",
                    f"https://{host}/gwprocess/v4/gw.php#fragment", "https://evil.example/gwprocess/v4/gw.php"):
            with self.subTest(url=url):
                self.assertFalse(_gateway_url_valid(url, host))

    def test_disabled_staging_is_healthy_but_not_ready(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = Config(database_url="sqlite+pysqlite:///" + temp + "/db.sqlite3")
            client = TestClient(create_app(cfg))
            self.assertEqual(client.get("/healthz").status_code, 200)
            self.assertEqual(client.get("/readyz").status_code, 503)
            self.assertFalse(client.get("/").json()["enabled"])
            self.assertEqual(client.post("/v1/checkouts", json={}).status_code, 422)

    def test_blueprint_fails_closed_and_excludes_secrets(self):
        blueprint = (ROOT / "render.yaml").read_text()
        self.assertIn("autoDeployTrigger: \"off\"", blueprint)
        self.assertIn("healthCheckPath: /healthz", blueprint)
        self.assertIn("value: \"false\"", blueprint)
        self.assertIn("property: connectionString", blueprint)
        self.assertIn("plan: free", blueprint)
        self.assertNotIn("store_passwd:", blueprint)
        self.assertNotIn("SLICKK_GATEWAY_LIVE\n        value: \"true\"", blueprint)
        self.assertNotIn("SLICKK_ENABLE_CHECKOUTS\n        value: \"true\"", blueprint)


if __name__ == "__main__":
    unittest.main()
