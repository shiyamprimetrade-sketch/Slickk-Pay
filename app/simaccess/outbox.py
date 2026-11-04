"""Durable simulated notifications. No sender or external network adapter exists.

This outbox demonstrates idempotency and retry scheduling without accidentally
broadcasting real customer identifiers or payment-success assertions.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
import sqlite3
from .audit import AccessAudit
from .crypto import new_reference
from .errors import LabError,require
from .identifiers import canonical,synthetic_id
from .policy import AccessPolicy
from .sessions import SessionContext
from .store import LabStore

ALLOWED_EVENTS=frozenset({"quote_ready","preview_reviewed","preview_cancelled",
                          "security_notice","support_draft_created","cash_checklist_updated"})
MAX_RETRIES=5


@dataclass(frozen=True)
class Notification:
    id:str
    actor_id:str
    kind:str
    content:str
    created_at:int
    status:str
    attempts:int
    next_attempt_at:int
    simulation:bool=True
    delivery_enabled:bool=False

    def public(self)->dict[str,object]:
        return {"id":self.id,"kind":self.kind,"content":self.content,
                "created_at":self.created_at,"status":self.status,
                "attempts":self.attempts,"simulation":True,"delivery_enabled":False}


class LabOutbox:
    def __init__(self,store:LabStore):
        self.store=store
        self.audit=AccessAudit(store)

    @staticmethod
    def _from_row(row:sqlite3.Row)->Notification:
        return Notification(row["event_id"],row["actor_id"],row["kind"],row["safe_body"],
                            row["created_at"],row["status"],row["attempts"],row["next_attempt_at"])

    def enqueue(self,*,actor_id:str,kind:str,safe_message:str,event_id:str|None=None)->Notification:
        from .identifiers import safe_note
        synthetic_id(actor_id)
        require(kind in ALLOWED_EVENTS,"INVALID_INPUT")
        clean=safe_note(safe_message,max_length=180)
        require(5<=len(clean)<=180,"INVALID_INPUT")
        ref=event_id or new_reference("delivery")
        synthetic_id(ref)
        now=self.store.clock.now()
        with self.store.transaction() as db:
            row=db.execute("SELECT * FROM lab_outbox WHERE event_id=?",(ref,)).fetchone()
            if row:
                if row["actor_id"]!=actor_id or row["kind"]!=kind or row["safe_body"]!=clean:
                    raise LabError("CONFLICT")
                return self._from_row(row)
            exists=db.execute("SELECT actor_id FROM lab_actors WHERE actor_id=? AND state='active'",(actor_id,)).fetchone()
            if not exists:
                raise LabError("NOT_FOUND")
            db.execute("INSERT INTO lab_outbox(event_id,actor_id,kind,safe_body,created_at,status,attempts,next_attempt_at) VALUES(?,?,?,?,?,'pending',0,?)",
                       (ref,actor_id,kind,clean,now,now))
            self.audit.append_in_transaction(db,actor=actor_id,kind="outbox_enqueued",
                                             data={"notification":ref,"kind":kind},event_id=new_reference("audit"))
        return Notification(ref,actor_id,kind,clean,now,"pending",0,now)

    def list_for(self,context:SessionContext,*,limit:int=40)->list[Notification]:
        AccessPolicy.require(context,"profile:read",resource_owner=context.actor_id)
        require(type(limit) is int and 1<=limit<=100,"INVALID_INPUT")
        with self.store.read() as db:
            rows=db.execute("SELECT * FROM lab_outbox WHERE actor_id=? ORDER BY created_at DESC,event_id DESC LIMIT ?",
                            (context.actor_id,limit)).fetchall()
        return [self._from_row(row) for row in rows]

    def acknowledge_locally(self,context:SessionContext,notification_id:str)->Notification:
        AccessPolicy.require(context,"profile:read",resource_owner=context.actor_id)
        synthetic_id(notification_id)
        with self.store.transaction() as db:
            row=db.execute("SELECT * FROM lab_outbox WHERE event_id=? AND actor_id=?",
                           (notification_id,context.actor_id)).fetchone()
            if row is None:
                raise LabError("NOT_FOUND")
            if row["status"]=="pending":
                db.execute("UPDATE lab_outbox SET status='acknowledged' WHERE event_id=?",(notification_id,))
            updated=db.execute("SELECT * FROM lab_outbox WHERE event_id=?",(notification_id,)).fetchone()
            return self._from_row(updated)

    def simulate_retry(self,notification_id:str,*,worker:str)->Notification:
        synthetic_id(notification_id)
        synthetic_id(worker)
        now=self.store.clock.now()
        with self.store.transaction() as db:
            row=db.execute("SELECT * FROM lab_outbox WHERE event_id=?",(notification_id,)).fetchone()
            if row is None:
                raise LabError("NOT_FOUND")
            if row["status"]!="pending":
                return self._from_row(row)
            if row["next_attempt_at"]>now:
                raise LabError("RECOVERY_BLOCKED")
            next_attempt=row["attempts"]+1
            next_state="suppressed" if next_attempt>=MAX_RETRIES else "pending"
            next_time=now+min(3600,30*2**next_attempt)
            db.execute("UPDATE lab_outbox SET attempts=?,status=?,next_attempt_at=? WHERE event_id=?",
                       (next_attempt,next_state,next_time,notification_id))
            row=db.execute("SELECT * FROM lab_outbox WHERE event_id=?",(notification_id,)).fetchone()
            return self._from_row(row)

    def due_count(self)->int:
        with self.store.read() as db:
            return int(db.execute("SELECT COUNT(*) FROM lab_outbox WHERE status='pending' AND next_attempt_at<=?",
                                  (self.store.clock.now(),)).fetchone()[0])

    def send_to_external_provider(self,*_:object,**__:object)->None:
        raise LabError("PROVIDER_ABSENT")
