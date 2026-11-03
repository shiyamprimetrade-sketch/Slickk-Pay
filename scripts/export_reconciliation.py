"""Private UTC-day merchant checkout report. Not a regulatory filing."""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, time, timedelta, timezone
import os
from pathlib import Path
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

FIELDS = ("tran_id", "order_ref", "amount_bdt", "currency", "gateway_status",
          "val_id", "bank_tran_id", "created_at", "updated_at")


def validate_readonly_url(raw: str):
    if not raw:
        raise ValueError("DATABASE_READ_URL is required")
    try:
        url = make_url(raw)
    except Exception as exc:
        raise ValueError("Invalid reporting database URL") from exc
    if url.drivername not in ("postgresql", "postgresql+psycopg"):
        raise ValueError("Reporting requires PostgreSQL")
    if url.query.get("sslmode") != "verify-full":
        raise ValueError("Reporting requires sslmode=verify-full and a trusted CA")
    if not url.username or not url.password or not url.host:
        raise ValueError("Incomplete reporting database connection")
    return url.set(drivername="postgresql+psycopg")


def export_day(day: date, output: Path, connection):
    start = datetime.combine(day, time.min, timezone.utc)
    end = start + timedelta(days=1)
    rows = connection.execute(text("""
        SELECT tran_id, order_ref, amount_bdt, currency, gateway_status,
               val_id, bank_tran_id, created_at, updated_at
          FROM merchant_checkout_reconciliation
         WHERE created_at >= :start AND created_at < :end
         ORDER BY created_at, tran_id
    """), {"start": start, "end": end})
    if output.exists():
        raise FileExistsError("Refusing to overwrite existing report")
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(FIELDS)
            count = 0
            for row in rows:
                writer.writerow(["" if v is None else str(v) for v in row])
                count += 1
        return count
    except BaseException:
        output.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description="Private UTC checkout reconciliation")
    parser.add_argument("--day", required=True, help="YYYY-MM-DD in UTC")
    parser.add_argument("--output", required=True, type=Path, help="New private CSV file")
    args = parser.parse_args()
    try:
        url = validate_readonly_url(os.getenv("DATABASE_READ_URL", ""))
        day = date.fromisoformat(args.day)
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as db:
            count = export_day(day, args.output, db)
        engine.dispose()
        print(f"Exported {count} checkout records to {args.output}")
        return 0
    except (ValueError, OSError, FileExistsError) as exc:
        print(f"Export refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
