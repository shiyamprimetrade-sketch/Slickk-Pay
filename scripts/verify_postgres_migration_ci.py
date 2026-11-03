"""Verify the merchant checkout PostgreSQL migration on a disposable localhost CI database only."""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]

def validate_ephemeral_target(raw_url: str, env: dict[str, str] | None = None) -> None:
    flags = os.environ if env is None else env
    if flags.get("CI", "").lower() != "true" or flags.get("SLICKK_EPHEMERAL_DB_TEST", "").lower() != "true":
        raise ValueError("Ephemeral migration verification requires explicit CI opt-in")
    if not raw_url:
        raise ValueError("Missing CI test database URL")
    try:
        target = make_url(raw_url)
    except Exception as exc:
        raise ValueError("Malformed CI test database URL") from exc
    if (target.drivername not in ("postgresql", "postgresql+psycopg")
            or target.host not in ("127.0.0.1", "localhost")
            or target.port != 5432 or target.database != "slickk_ci_test"):
        raise ValueError("Refusing migration: not the isolated local CI PostgreSQL database")

def verify_migration(url: str) -> None:
    validate_ephemeral_target(url)
    import psycopg
    from sqlalchemy import create_engine
    from app.live import Base, Checkout, _database_url

    engine = create_engine(_database_url(url), pool_pre_ping=True)
    try:
        Base.metadata.create_all(engine, tables=[Checkout.__table__])
        sql = (ROOT / "migrations" / "001_merchant_checkout_audit.sql").read_text(encoding="utf-8")
        ipn_sql = (ROOT / "migrations" / "002_ipn_terminal_security_events.sql").read_text(encoding="utf-8")
        with psycopg.connect(url, autocommit=True) as db:
            db.execute(sql)
            db.execute(sql)  # repeatability test
            db.execute(ipn_sql)
            db.execute(ipn_sql)  # repeatability test
            ref = "ci-" + uuid4().hex[:18]
            order = "ci-order-" + uuid4().hex[:16]
            with db.transaction():
                db.execute("""INSERT INTO merchant_checkouts
                    (id,order_ref,amount_poisha,fingerprint,state)
                    VALUES (%s,%s,%s,%s,%s)""",
                    (ref, order, 125000, "0" * 64, "initiating"))
                db.execute("UPDATE merchant_checkouts SET state=%s WHERE id=%s",
                           ("pending_payment", ref))
            rows = db.execute("""SELECT previous_state,current_state
                FROM merchant_checkout_state_events
                WHERE checkout_id=%s ORDER BY event_id""", (ref,)).fetchall()
            assert rows == [(None, "initiating"), ("initiating", "pending_payment")], rows
            row = db.execute("""SELECT amount_bdt,currency,gateway_status,created_at,updated_at
                FROM merchant_checkout_reconciliation WHERE tran_id=%s""", (ref,)).fetchone()
            assert row and str(row[0]) == "1250.00" and row[1] == "BDT" and row[2] == "pending_payment", row
            assert row[3] and row[4], row
            columns = {r[0] for r in db.execute("""SELECT column_name FROM information_schema.columns
                WHERE table_name='merchant_checkouts'""").fetchall()}
            assert not ({"card_no", "card_no_masked", "store_passwd"} & columns)
            audit_columns = {r[0] for r in db.execute("""SELECT column_name FROM information_schema.columns
                WHERE table_name='merchant_checkout_ipn_security_events'""").fetchall()}
            assert {"event_id", "checkout_id", "existing_state", "reason",
                    "status_hint", "val_id_digest", "recorded_at"} <= audit_columns
            assert not ({"raw_payload", "card_no", "customer_name", "customer_email",
                         "customer_phone", "store_passwd"} & audit_columns)
            db.execute("""INSERT INTO merchant_checkout_ipn_security_events
                 (event_id, checkout_id, existing_state, reason, status_hint, val_id_digest)
                 VALUES (%s,%s,%s,%s,%s,%s)""",
                 (uuid4().hex, ref, "failed", "terminal_state_blocked", "VALID", "0"*64))
        print("PASS: disposable PostgreSQL migrations 001/002; state audit, security event and reconciliation verified")
    finally:
        engine.dispose()

if __name__ == "__main__":
    verify_migration(os.getenv("SLICKK_CI_DATABASE_URL", ""))
