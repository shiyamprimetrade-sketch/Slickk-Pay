"""Sandbox-only transaction control and fail-closed connection management.

SQLite support exists solely for deterministic local tests. PostgreSQL uses
SERIALIZABLE transactions with explicit sorted row locking in ledger operations.
"""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from sqlalchemy import create_engine, select, insert, event, Engine
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.engine import Connection
from sqlalchemy.pool import NullPool
from .guard import assert_sandbox_target, assert_not_live_environment
from .schema import metadata, chain
from .errors import TransientStorage, UnauthorizedEnvironment

GENESIS = "0" * 64


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


@dataclass(frozen=True)
class StoreSnapshot:
    dialect: str
    tables: tuple[str, ...]
    simulation: bool = True
    accepts_live_money: bool = False


class SandboxStore:
    def __init__(self, database_url: str, *, local_test: bool = False,
                 bootstrap: bool = True, isolation: str = "SERIALIZABLE"):
        assert_not_live_environment()
        url = assert_sandbox_target(database_url, allow_local_sqlite=local_test)
        self._dialect = "sqlite" if url.drivername.startswith("sqlite") else "postgresql"
        if self._dialect == "sqlite" and not local_test:
            raise UnauthorizedEnvironment("SQLite is local-test-only")
        if isolation != "SERIALIZABLE":
            raise UnauthorizedEnvironment("Sandbox ledger requires serializable semantics")
        self.engine: Engine = create_engine(url, pool_pre_ping=True,
            connect_args={"timeout": 15} if self._dialect == "sqlite" else {},
            poolclass=NullPool if self._dialect == "sqlite" else None,
            isolation_level=isolation if self._dialect == "postgresql" else None)
        if self._dialect == "sqlite":
            @event.listens_for(self.engine, "connect")
            def sqlite_pragmas(dbapi_connection, _connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=15000")
                cursor.close()
        if bootstrap:
            self.bootstrap()

    @property
    def dialect(self) -> str:
        return self._dialect

    def bootstrap(self) -> None:
        assert_not_live_environment()
        metadata.create_all(self.engine, checkfirst=True)
        if self._dialect == "postgresql":
            # The guarded, local-only migration adds immutable journal triggers.
            from .pg_migrations import install_pg_sandbox
            install_pg_sandbox(self.engine)
        with self.transaction() as db:
            head = db.execute(select(chain.c.id).where(chain.c.id == 1)).first()
            if head is None:
                db.execute(insert(chain).values(id=1, latest_hash=GENESIS, latest_sequence=0))
        if self._dialect == "sqlite":
            # Only for local integrity tests; PG trigger DDL is installed by migration 004.
            with self.engine.begin() as db:
                for table in ("s2_journals", "s2_postings", "s2_security_events"):
                    for operation in ("UPDATE", "DELETE"):
                        db.exec_driver_sql(
                            f"CREATE TRIGGER IF NOT EXISTS {table}_{operation.lower()}_guard "
                            f"BEFORE {operation} ON {table} BEGIN "
                            "SELECT RAISE(ABORT,'immutable sandbox audit'); END;")

    @contextmanager
    def transaction(self):
        """Open one ACID transaction; higher-level services must not commit inside.

        PG SERIALIZABLE handles isolation and recovery by explicit caller retry.
        SQLite uses BEGIN IMMEDIATE to serialize local test writers across processes.
        """
        with self.engine.connect() as db:
            if self._dialect == "sqlite":
                db.exec_driver_sql("BEGIN IMMEDIATE")
                try:
                    yield db
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
            else:
                with db.begin():
                    yield db

    def snapshot(self) -> StoreSnapshot:
        return StoreSnapshot(self.dialect, tuple(metadata.tables.keys()))

    def dispose(self) -> None:
        self.engine.dispose()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.dispose()


def is_retryable_db_failure(error: BaseException) -> bool:
    """Recognize PG serialization/deadlock SQLSTATE, not arbitrary exceptions."""
    if not isinstance(error, DBAPIError):
        return False
    origin = error.orig
    sqlstate = getattr(origin, "sqlstate", None) or getattr(origin, "pgcode", None)
    return sqlstate in ("40001", "40P01")
