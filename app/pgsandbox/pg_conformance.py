"""PostgreSQL sandbox capability probes; never query production database names.

These checks are read-only after migrations and help a reviewer distinguish
SQLite unit results from true PostgreSQL row locks and transaction semantics.
"""
from __future__ import annotations
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select, inspect, text, func
from sqlalchemy.exc import SQLAlchemyError
from .store import SandboxStore, is_retryable_db_failure
from .schema import metadata, chain, accounts, journals, postings, requests
from .posting import LedgerService
from .errors import UnauthorizedEnvironment, InvalidValue, ReportMismatch

REQUIRED_PG_TABLES=frozenset(metadata.tables)
IMMUTABLE_TABLES=frozenset({"s2_journals","s2_postings","s2_security_events",
                            "s2_cash_history","s2_auth_nonces"})


@dataclass(frozen=True)
class DatabaseProof:
    engine_kind: str
    tables_checked: int
    missing_tables: tuple[str,...]
    missing_immutable_triggers: tuple[str,...]
    chain_row_count: int
    account_count: int
    journal_count: int
    balanced: bool
    simulation: bool = True
    production_approved: bool = False


class PostgresConformance:
    def __init__(self, store: SandboxStore):
        self.store=store

    def schema(self) -> DatabaseProof:
        if self.store.dialect!="postgresql":
            raise UnauthorizedEnvironment("PostgreSQL conformance is not a SQLite test")
        inspector=inspect(self.store.engine)
        actual=set(inspector.get_table_names())
        missing=tuple(sorted(REQUIRED_PG_TABLES-actual))
        with self.store.engine.connect() as db:
            triggers=db.execute(text("""
                SELECT event_object_table, trigger_name
                FROM information_schema.triggers
                WHERE event_object_schema = current_schema()
                  AND event_object_table LIKE 's2_%'
            """)).all()
            names={row[0] for row in triggers}
            immutable_missing=tuple(sorted(IMMUTABLE_TABLES-names))
            heads=db.execute(select(func.count()).select_from(chain)).scalar_one()
            num_accounts=db.execute(select(func.count()).select_from(accounts)).scalar_one()
            num_journals=db.execute(select(func.count()).select_from(journals)).scalar_one()
            debit=db.execute(select(func.coalesce(func.sum(postings.c.amount),0))
                             .where(postings.c.direction=="debit")).scalar_one()
            credit=db.execute(select(func.coalesce(func.sum(postings.c.amount),0))
                              .where(postings.c.direction=="credit")).scalar_one()
        return DatabaseProof("postgresql",len(REQUIRED_PG_TABLES),missing,immutable_missing,
                             heads,num_accounts,num_journals,debit==credit)

    def require_healthy(self) -> DatabaseProof:
        proof=self.schema()
        if proof.missing_tables or proof.missing_immutable_triggers or proof.chain_row_count!=1 or not proof.balanced:
            raise ReportMismatch("Isolated PostgreSQL sandbox installation is incomplete")
        return proof

    def pg_server_info(self) -> dict[str,object]:
        if self.store.dialect!="postgresql":
            raise UnauthorizedEnvironment("Server information requires PG sandbox")
        with self.store.engine.connect() as db:
            version=db.execute(text("SHOW server_version_num")).scalar_one()
            name=db.execute(text("SELECT current_database()")).scalar_one()
            isolation=db.execute(text("SHOW default_transaction_isolation")).scalar_one()
        if name!="slickk_ci_test":
            raise UnauthorizedEnvironment("Unexpected database identity")
        return {"server_version_num":int(version),"database":"sandbox_ci_only",
                "connection_isolation":"SERIALIZABLE (requested per transaction)",
                "server_default_isolation":isolation,"simulation":True}


def replay_concurrent_debits(ledger: LedgerService, *, sender: str,
                             receiver: str, amount: int, operation_key: str,
                             clients: int=8) -> dict[str,object]:
    """Race identical idempotency keys; successful retries share one journal."""
    if not 2<=clients<=32 or amount<=0:
        raise InvalidValue("Invalid database concurrency probe")
    outcomes=[]

    def one():
        try:
            receipt=ledger.transfer(sender,receiver,amount,key=operation_key,
                                    actor="sim_operator_concurrency")
            return ("posted",receipt.event_id)
        except Exception as exc:
            if is_retryable_db_failure(exc):
                return ("retry",None)
            return ("rejected",type(exc).__name__)

    with ThreadPoolExecutor(max_workers=clients) as pool:
        outcomes=list(pool.map(lambda _:one(),range(clients)))
    references={ref for state,ref in outcomes if state=="posted"}
    proof=ledger.verify()
    return {"clients":clients,"successful_acknowledgements":sum(s=="posted" for s,_ in outcomes),
            "retryable_serialization_failures":sum(s=="retry" for s,_ in outcomes),
            "unique_posted_events":len(references),"deduplicated":len(references)<=1,
            "journal_valid":proof.valid,"simulation":True}
