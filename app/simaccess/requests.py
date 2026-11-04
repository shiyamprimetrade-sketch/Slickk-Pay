"""Server-side review/cancel lifecycle with no financial posting capability."""
from __future__ import annotations
from dataclasses import dataclass
import sqlite3
from .audit import AccessAudit
from .crypto import new_reference
from .errors import LabError,require,deny_posting
from .identifiers import canonical,digest,synthetic_id
from .policy import AccessPolicy
from .quotes import QuoteService
from .sessions import SessionContext
from .store import LabStore
from .rate_limits import RateLimiter


@dataclass(frozen=True)
class ReviewRequest:
    id:str
    owner_id:str
    quote_id:str
    operation:str
    status:str
    accepted_at:int
    updated_at:int
    revision:int
    simulation:bool=True
    financial_posting:bool=False
    handover_authorized:bool=False

    def public(self)->dict[str,object]:
        return {"request_id":self.id,"owner_id":self.owner_id,"quote_id":self.quote_id,
                "operation":self.operation,"status":self.status,"revision":self.revision,
                "accepted_at":self.accepted_at,"updated_at":self.updated_at,
                "simulation":True,"financial_posting":False,"handover_authorized":False}


class RequestService:
    def __init__(self,store:LabStore):
        self.store=store
        self.quotes=QuoteService(store)
        self.audit=AccessAudit(store)
        self.limiter=RateLimiter(store)

    @staticmethod
    def _from_row(row:sqlite3.Row)->ReviewRequest:
        return ReviewRequest(row["request_id"],row["owner_id"],row["quote_id"],
                             row["kind"],row["status"],row["accepted_at"],
                             row["updated_at"],row["revision"])

    def _event(self,db:sqlite3.Connection,request:ReviewRequest,kind:str)->None:
        now=self.store.clock.now()
        event=new_reference("audit")
        evidence=digest(canonical({"request":request.id,"kind":kind,"revision":request.revision}).decode())
        db.execute("INSERT INTO lab_request_events(event_id,request_id,event_type,happened_at,event_digest,summary) VALUES(?,?,?,?,?,?)",
                   (event,request.id,kind,now,evidence,"synthetic review only"))

    def review(self,context:SessionContext,quote_id:str,*,explicit_preview_consent:bool)->ReviewRequest:
        AccessPolicy.require(context,"quote:review",resource_owner=context.actor_id)
        synthetic_id(quote_id)
        require(type(explicit_preview_consent) is bool and explicit_preview_consent,"INVALID_INPUT")
        with self.store.transaction() as db:
            row=db.execute("SELECT * FROM lab_requests WHERE quote_id=? AND owner_id=?",(quote_id,context.actor_id)).fetchone()
            if row:
                return self._from_row(row)
            q=self.quotes.fresh_in_transaction(db,context,quote_id)
            self.limiter.consume_in_transaction(db,context.actor_id,"review")
            now=self.store.clock.now()
            request_id=new_reference("request")
            db.execute("INSERT INTO lab_requests(request_id,owner_id,quote_id,kind,status,accepted_at,updated_at,no_financial_posting,revision) VALUES(?,?,?,?,?,?,?,1,1)",
                       (request_id,context.actor_id,quote_id,q.operation,"reviewed",now,now))
            db.execute("UPDATE lab_quotes SET status='reviewed' WHERE quote_id=? AND status='quoted'",(quote_id,))
            result=ReviewRequest(request_id,context.actor_id,quote_id,q.operation,"reviewed",now,now,1)
            self._event(db,result,"preview_reviewed")
            self.audit.append_in_transaction(db,actor=context.actor_id,kind="quote_reviewed",
                                             data={"request":request_id,"quote":quote_id},event_id=new_reference("audit"))
            return result

    def get(self,context:SessionContext,request_id:str)->ReviewRequest:
        AccessPolicy.require(context,"request:read",resource_owner=context.actor_id)
        synthetic_id(request_id)
        with self.store.read() as db:
            row=db.execute("SELECT * FROM lab_requests WHERE request_id=? AND owner_id=?",
                           (request_id,context.actor_id)).fetchone()
        if not row:
            raise LabError("NOT_FOUND")
        return self._from_row(row)

    def list(self,context:SessionContext,limit:int=50)->list[ReviewRequest]:
        AccessPolicy.require(context,"request:read",resource_owner=context.actor_id)
        require(type(limit) is int and 1<=limit<=100,"INVALID_INPUT")
        with self.store.read() as db:
            rows=db.execute("SELECT * FROM lab_requests WHERE owner_id=? ORDER BY accepted_at DESC,request_id DESC LIMIT ?",
                            (context.actor_id,limit)).fetchall()
        return [self._from_row(row) for row in rows]

    def cancel(self,context:SessionContext,request_id:str)->ReviewRequest:
        AccessPolicy.require(context,"request:cancel",resource_owner=context.actor_id)
        synthetic_id(request_id)
        with self.store.transaction() as db:
            row=db.execute("SELECT * FROM lab_requests WHERE request_id=? AND owner_id=?",(request_id,context.actor_id)).fetchone()
            if row is None:
                raise LabError("NOT_FOUND")
            previous=self._from_row(row)
            if previous.status=="cancelled":
                return previous
            if previous.status!="reviewed":
                raise LabError("REQUEST_FINAL")
            now=self.store.clock.now()
            db.execute("UPDATE lab_requests SET status='cancelled',revision=revision+1,updated_at=? WHERE request_id=? AND status='reviewed'",
                       (now,request_id))
            result=ReviewRequest(previous.id,previous.owner_id,previous.quote_id,previous.operation,"cancelled",
                                 previous.accepted_at,now,previous.revision+1)
            self._event(db,result,"preview_cancelled")
            self.audit.append_in_transaction(db,actor=context.actor_id,kind="request_cancelled",
                                             data={"request":request_id},event_id=new_reference("audit"))
            return result

    def event_history(self,context:SessionContext,request_id:str)->list[dict[str,object]]:
        self.get(context,request_id)
        with self.store.read() as db:
            rows=db.execute("SELECT event_id,event_type,happened_at,event_digest,summary FROM lab_request_events WHERE request_id=? ORDER BY happened_at,event_id",
                            (request_id,)).fetchall()
        return [{"id":r["event_id"],"kind":r["event_type"],"at":r["happened_at"],
                 "digest":r["event_digest"],"summary":r["summary"],"simulation":True} for r in rows]

    def attempt_execution(self,context:SessionContext,request_id:str)->None:
        self.get(context,request_id)
        deny_posting()

    def authorize_cash_handover(self,context:SessionContext,request_id:str)->None:
        self.get(context,request_id)
        deny_posting()

    def reconcile_bank(self,context:SessionContext,request_id:str)->None:
        self.get(context,request_id)
        deny_posting()
