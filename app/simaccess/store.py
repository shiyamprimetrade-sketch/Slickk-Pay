"""Transactional persistence scoped strictly to a local fictional-data lab.

The storage path guard prevents accidental reuse of merchant/prod databases.
SQLite does not provide PostgreSQL SERIALIZABLE; CI tests process safety here,
while Cycle 002 already covers the PostgreSQL accounting sandbox separately.
"""
from __future__ import annotations
from contextlib import contextmanager, closing
from pathlib import Path
from threading import RLock
import os
import sqlite3
from collections.abc import Iterator
from .errors import LabError, require
from .schema import SCHEMA_SQL, SCHEMA_VERSION, REQUIRED_TABLES
from .clock import Clock

_ALLOWED_ENV = frozenset({"development", "staging", "sandbox", "test"})


def assert_lab_environment() -> None:
    if os.environ.get("SLICKK_ENV", "sandbox").lower() not in _ALLOWED_ENV:
        raise LabError("LAB_DISABLED")
    for name in ("SLICKK_ENABLE_CHECKOUTS", "SLICKK_GATEWAY_LIVE", "SLICKK_REGULATORY_SIGNOFF"):
        if os.environ.get(name, "false").lower() == "true":
            raise LabError("LAB_DISABLED")


def safe_database_path(value: str) -> Path:
    require(isinstance(value, str) and value and not value.startswith("file:"), "LAB_DISABLED")
    require(not value.startswith(("postgres", "mysql", "sqlite:")), "LAB_DISABLED")
    path = Path(value).expanduser().absolute()
    name = path.name.lower()
    require(name.startswith("sim_access_") and name.endswith(".sqlite3"), "LAB_DISABLED")
    require(not any(x in str(path).lower() for x in ("production", "prod_db", "customer_real", "live_data")), "LAB_DISABLED")
    require(path.parent.exists() and path.parent.is_dir(), "LAB_DISABLED")
    if path.is_symlink():
        raise LabError("LAB_DISABLED")
    return path


class LabStore:
    def __init__(self, database_path: str, *, opted_in: bool, clock: Clock | None = None):
        assert_lab_environment()
        if opted_in is not True:
            raise LabError("LAB_DISABLED")
        self.path = safe_database_path(database_path)
        self.clock = clock or Clock()
        self._lock = RLock()
        self._bootstrap()

    def _connect(self) -> sqlite3.Connection:
        assert_lab_environment()
        conn = sqlite3.connect(str(self.path), timeout=15, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        return conn

    def _bootstrap(self) -> None:
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.executescript(SCHEMA_SQL)
                conn.execute("INSERT OR IGNORE INTO lab_schema_version(version,created_at) VALUES(?,?)",
                             (SCHEMA_VERSION, self.clock.now()))
                versions = [x[0] for x in conn.execute("SELECT version FROM lab_schema_version")]
                if versions != [SCHEMA_VERSION]:
                    raise LabError("LAB_DISABLED")
                conn.execute("INSERT OR IGNORE INTO lab_audit_head(id,sequence,hash) VALUES(1,0,?)", ("0" * 64,))
                conn.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        assert_lab_environment()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        assert_lab_environment()
        conn = self._connect()
        try:
            conn.execute("BEGIN")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def count(self, table: str) -> int:
        if table not in REQUIRED_TABLES:
            raise LabError("INVALID_INPUT")
        with self.read() as conn:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def health(self) -> dict[str, object]:
        with self.read() as db:
            version = db.execute("SELECT version FROM lab_schema_version").fetchone()[0]
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
            fk = db.execute("PRAGMA foreign_key_check").fetchall()
            return {
                "simulation": True,
                "money_movement": False,
                "database": "isolated_sqlite_local_test_only",
                "schema": version,
                "sqlite_integrity": integrity == "ok",
                "foreign_key_violations": len(fk),
            }

    def checkpoint(self, mode: str = "PASSIVE") -> tuple[int, int, int]:
        require(mode in ("PASSIVE", "FULL"), "INVALID_INPUT")
        with closing(self._connect()) as conn:
            row = conn.execute(f"PRAGMA wal_checkpoint({mode})").fetchone()
            return tuple(int(v) for v in row)

    def close(self) -> None:
        """Connections are per-transaction; no long-lived shared connector to close."""
        return None

    def __enter__(self) -> "LabStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
