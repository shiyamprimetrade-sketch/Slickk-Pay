"""Idempotent, crash-recoverable expiry for local review records.

This worker cannot perform debit/credit, retry customer money commands or
reconcile a real bank. It expires only stale *unpaid previews* in the lab.
"""
from __future__ import annotations
from dataclasses import dataclass
import sqlite3
from .audit import AccessAudit
from .crypto import new_reference
from .errors import LabError,require
from .identifiers import synthetic_id
from .store import LabStore


@dataclass(frozen=True)
class RecoveryReport:
    run_at:int
    quotes_expired:int
    requests_expired:int
    replay_pruned:int
    stale_sessions_revoked:int
    audit_valid:bool
    simulation:bool=True
    financial_recovery:bool=False

    def public(self)->dict[str,object]:
        return {"run_at":self.run_at,"quotes_expired":self.quotes_expired,
                "requests_expired":self.requests_expired,"replay_pruned":self.replay_pruned,
                "stale_sessions_revoked":self.stale_sessions_revoked,
                "audit_valid":self.audit_valid,"simulation":True,"financial_recovery":False}


class LabRecovery:
    def __init__(self,store:LabStore):
        self.store=store
        self.audit=AccessAudit(store)

    def run_once(self,*,batch_size:int=200)->RecoveryReport:
        require(type(batch_size) is int and 1<=batch_size<=2000,"INVALID_INPUT")
        self.audit.assert_intact()
        now=self.store.clock.now()
        with self.store.transaction() as db:
            qrows=db.execute("SELECT quote_id,owner_id FROM lab_quotes WHERE status='quoted' AND expires_at<=? ORDER BY expires_at,quote_id LIMIT ?",
                             (now,batch_size)).fetchall()
            for row in qrows:
                db.execute("UPDATE lab_quotes SET status='expired' WHERE quote_id=? AND status='quoted'",(row["quote_id"],))
                self.audit.append_in_transaction(db,actor=row["owner_id"],kind="recovery_expired",
                                                 data={"quote":row["quote_id"]},event_id=new_reference("audit"))
            # Reviewed requests never become paid; stale reviews expire only for UI.
            requests=db.execute("SELECT r.request_id,r.owner_id,r.revision,r.quote_id FROM lab_requests r JOIN lab_quotes q ON q.quote_id=r.quote_id WHERE r.status='reviewed' AND q.expires_at<=? ORDER BY r.updated_at,r.request_id LIMIT ?",
                                (now,batch_size)).fetchall()
            for row in requests:
                db.execute("UPDATE lab_requests SET status='expired',revision=revision+1,updated_at=? WHERE request_id=? AND status='reviewed'",
                           (now,row["request_id"]))
                self.audit.append_in_transaction(db,actor=row["owner_id"],kind="recovery_expired",
                                                 data={"request":row["request_id"]},event_id=new_reference("audit"))
            deleted=db.execute("DELETE FROM lab_replay WHERE expires_at<?",(now,)).rowcount
            revoked=db.execute("UPDATE lab_sessions SET state='expired' WHERE state='active' AND (expires_at<=? OR last_used_at<?)",
                               (now,now-3600)).rowcount
        verified=self.audit.verify()
        return RecoveryReport(now,len(qrows),len(requests),deleted,revoked,verified.valid)

    def dry_run(self)->dict[str,object]:
        now=self.store.clock.now()
        with self.store.read() as db:
            candidates={
                "quotes":db.execute("SELECT COUNT(*) FROM lab_quotes WHERE status='quoted' AND expires_at<=?",(now,)).fetchone()[0],
                "requests":db.execute("SELECT COUNT(*) FROM lab_requests r JOIN lab_quotes q ON q.quote_id=r.quote_id WHERE r.status='reviewed' AND q.expires_at<=?",(now,)).fetchone()[0],
                "replay":db.execute("SELECT COUNT(*) FROM lab_replay WHERE expires_at<?",(now,)).fetchone()[0],
            }
        return {"simulation":True,"would_post_financial_entries":False,"candidates":candidates}

    def assert_no_financial_posting(self)->bool:
        with self.store.read() as db:
            wrong=db.execute("SELECT COUNT(*) FROM lab_requests WHERE no_financial_posting!=1").fetchone()[0]
            if wrong:
                raise LabError("AUDIT_INTEGRITY")
            db_tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            forbidden={"ledger_postings","real_wallets","customer_deposits","bank_settlements"}
            if db_tables & forbidden:
                raise LabError("AUDIT_INTEGRITY")
        return True
