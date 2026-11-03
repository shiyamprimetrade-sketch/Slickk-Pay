"""Reconciliation export and migration checks; no live DB required."""
from datetime import date
from pathlib import Path
import csv
import tempfile
import unittest

from sqlalchemy import create_engine, text

from scripts.export_reconciliation import validate_readonly_url, export_day, FIELDS


class ReportingSafetyTests(unittest.TestCase):
    def test_reporting_requires_postgresql_and_verified_tls(self):
        good = "postgresql://report:dummy@db.example.test/report?sslmode=verify-full"
        self.assertEqual(validate_readonly_url(good).drivername, "postgresql+psycopg")
        for bad in ("", "sqlite:///test.db",
                    "postgresql://r:p@db.example.test/r",
                    "postgresql://r@db.example.test/r?sslmode=verify-full"):
            with self.subTest(db_url=bad), self.assertRaises(ValueError):
                validate_readonly_url(bad)

    def test_report_contains_no_pii_and_never_overwrites(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        with engine.begin() as db:
            db.execute(text("CREATE TABLE merchant_checkout_reconciliation (tran_id TEXT, order_ref TEXT, amount_bdt NUMERIC, currency TEXT, gateway_status TEXT, val_id TEXT, bank_tran_id TEXT, created_at TIMESTAMP, updated_at TIMESTAMP)"))
            db.execute(text("INSERT INTO merchant_checkout_reconciliation VALUES ('SPTEST','ORDER-01',1250.00,'BDT','paid','val-test','bank-test','2026-11-03 09:00:00','2026-11-03 09:00:01')"))
            with tempfile.TemporaryDirectory() as d:
                path = Path(d) / "report.csv"
                self.assertEqual(export_day(date(2026, 11, 3), path, db), 1)
                with path.open(encoding="utf-8") as handle:
                    rows = list(csv.reader(handle))
                self.assertEqual(tuple(rows[0]), FIELDS)
                self.assertEqual(rows[1][0], "SPTEST")
                self.assertNotIn("card_no", path.read_text())
                with self.assertRaises(FileExistsError):
                    export_day(date(2026, 11, 3), path, db)
        engine.dispose()

    def test_migration_reuses_existing_table_and_avoids_card_number(self):
        sql = Path(__file__).resolve().parents[1].joinpath("migrations/001_merchant_checkout_audit.sql").read_text().lower()
        self.assertIn("merchant_checkout_reconciliation", sql)
        self.assertIn("merchant_checkout_state_events", sql)
        self.assertNotIn("create table transactions", sql)
        self.assertNotIn("card_no varchar", sql)
        self.assertIn("timestamptz", sql)


if __name__ == "__main__":
    unittest.main()
