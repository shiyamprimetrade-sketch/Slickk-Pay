"""Transaction-boundary probes for deliberate crash and rollback experiments.

Only synthetic preview/audit records are mutated by this diagnostic tool. The
failure injection runs *inside* the local SQLite transaction and must roll
back every row if any later operation raises.
"""
from __future__ import annotations
from dataclasses import dataclass
import sqlite3
from typing import Callable
from .audit import AccessAudit
from .errors import LabError,require
from .store import LabStore


@dataclass(frozen=True)
class RollbackEvidence:
    before_rows:int
    after_rows:int
    before_audit_events:int
    after_audit_events:int
    injected_error_seen:bool
    data_unchanged:bool
    simulation:bool=True


class FaultProbe:
    def __init__(self,store:LabStore):
        self.store=store

    def _counts(self)->tuple[int,int]:
        with self.store.read() as db:
            a=db.execute("SELECT COUNT(*) FROM lab_quotes").fetchone()[0]
            b=db.execute("SELECT COUNT(*) FROM lab_audit").fetchone()[0]
        return int(a),int(b)

    def probe_atomic_rollback(self,*,actor_id:str,correlation:str)->RollbackEvidence:
        from .identifiers import synthetic_id,event_ref
        synthetic_id(actor_id)
        event_ref(correlation)
        before_q,before_a=self._counts()
        error_seen=False
        try:
            with self.store.transaction() as db:
                # Creates an allowed synthetic event before forcing rollback.
                from .crypto import new_reference
                AccessAudit(self.store).append_in_transaction(db,actor=actor_id,
                    kind="quote_created",data={"correlation":correlation,"fault_test":True},
                    event_id=new_reference("audit"))
                # Fail after first write to verify atomicity of the enclosing transaction.
                raise RuntimeError("injected local sandbox crash before commit")
        except RuntimeError as exc:
            if str(exc)!="injected local sandbox crash before commit":
                raise
            error_seen=True
        after_q,after_a=self._counts()
        same=before_q==after_q and before_a==after_a
        return RollbackEvidence(before_q,after_q,before_a,after_a,error_seen,same)

    def assert_rollback(self,*,actor_id:str,correlation:str)->RollbackEvidence:
        report=self.probe_atomic_rollback(actor_id=actor_id,correlation=correlation)
        if not report.injected_error_seen or not report.data_unchanged:
            raise LabError("AUDIT_INTEGRITY")
        return report

    def test_readonly_query_transaction(self)->bool:
        before=self._counts()
        with self.store.read() as db:
            db.execute("SELECT COUNT(*) FROM lab_requests").fetchone()
        return before==self._counts()
