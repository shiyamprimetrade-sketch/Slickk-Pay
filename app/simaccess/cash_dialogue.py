"""Durable two-person synthetic review acknowledgments for agent cash requests.

Each party reviews the *fictional request*. Even after both acknowledgements,
there is NO transition to paid, released, handed-over, settled, or ledger-posted.
All real-money confirmation must be implemented by an authorized future system.
"""
from __future__ import annotations
from dataclasses import dataclass
import sqlite3
from .audit import AccessAudit
from .crypto import new_reference
from .errors import LabError,require,deny_posting
from .identifiers import synthetic_id,event_ref,digest
from .policy import AccessPolicy
from .rate_limits import RateLimiter,ReplayGuard
from .sessions import SessionContext
from .store import LabStore


@dataclass(frozen=True)
class TwoPartyPreview:
    request_id:str
    customer_id:str
    agent_id:str
    customer_reviewed:bool
    agent_reviewed:bool
    state:str
    created_at:int
    updated_at:int
    simulation:bool=True
    both_reviews_not_payment:bool=True
    cash_handover_authorized:bool=False

    def public(self)->dict[str,object]:
        return {"request_id":self.request_id,"customer_id":self.customer_id,
                "agent_id":self.agent_id,"customer_reviewed":self.customer_reviewed,
                "agent_reviewed":self.agent_reviewed,"state":self.state,
                "created_at":self.created_at,"updated_at":self.updated_at,
                "simulation":True,"both_reviews_not_payment":True,
                "cash_handover_authorized":False,"ledger_posting":False}


class CashDialogue:
    def __init__(self,store:LabStore):
        self.store=store
        self.audit=AccessAudit(store)
        self.limits=RateLimiter(store)
        self.replay=ReplayGuard(store)

    @staticmethod
    def from_row(row:sqlite3.Row)->TwoPartyPreview:
        return TwoPartyPreview(row["request_id"],row["customer_id"],row["agent_id"],
                               row["customer_ref_digest"] is not None,row["agent_ref_digest"] is not None,
                               row["status"],row["created_at"],row["updated_at"])

    @staticmethod
    def _participants(db:sqlite3.Connection,request_id:str)->tuple[str,str,int]:
        request=db.execute("SELECT r.owner_id,r.status,q.operation,q.counterpart_id,q.expires_at "
                           "FROM lab_requests r JOIN lab_quotes q ON q.quote_id=r.quote_id "
                           "WHERE r.request_id=?",(request_id,)).fetchone()
        if request is None or request["operation"] not in ("cash_out","cash_in"):
            raise LabError("NOT_FOUND")
        if request["operation"]=="cash_out":
            customer,agent=request["owner_id"],request["counterpart_id"]
        else:
            customer,agent=request["counterpart_id"],request["owner_id"]
        if request["status"]!="reviewed":
            raise LabError("REQUEST_FINAL")
        return customer,agent,request["expires_at"]

    def get(self,context:SessionContext,request_id:str)->TwoPartyPreview:
        synthetic_id(request_id)
        with self.store.read() as db:
            row=db.execute("SELECT * FROM lab_cash_ack WHERE request_id=?",(request_id,)).fetchone()
        if row is None:
            raise LabError("NOT_FOUND")
        if context.actor_id not in (row["customer_id"],row["agent_id"]):
            raise LabError("ROLE_FORBIDDEN")
        return self.from_row(row)

    def start(self,context:SessionContext,request_id:str)->TwoPartyPreview:
        synthetic_id(request_id)
        require(context.role in ("customer","agent"),"ROLE_FORBIDDEN")
        now=self.store.clock.now()
        with self.store.transaction() as db:
            customer,agent,expires=self._participants(db,request_id)
            if context.actor_id not in (customer,agent):
                raise LabError("ROLE_FORBIDDEN")
            if now>=expires:
                raise LabError("QUOTE_EXPIRED")
            for participant,expected in ((customer,"customer"),(agent,"agent")):
                row=db.execute("SELECT role,state FROM lab_actors WHERE actor_id=?",(participant,)).fetchone()
                if row is None or row["role"]!=expected or row["state"]!="active":
                    raise LabError("ROLE_FORBIDDEN")
            row=db.execute("SELECT * FROM lab_cash_ack WHERE request_id=?",(request_id,)).fetchone()
            if row:
                return self.from_row(row)
            db.execute("INSERT INTO lab_cash_ack(request_id,customer_id,agent_id,status,created_at,updated_at) VALUES(?,?,?,'waiting',?,?)",
                       (request_id,customer,agent,now,now))
            row=db.execute("SELECT * FROM lab_cash_ack WHERE request_id=?",(request_id,)).fetchone()
            return self.from_row(row)

    def acknowledge(self,context:SessionContext,request_id:str,*,review_reference:str)->TwoPartyPreview:
        synthetic_id(request_id)
        event_ref(review_reference)
        require(context.role in ("customer","agent"),"ROLE_FORBIDDEN")
        now=self.store.clock.now()
        hashed=digest(review_reference)
        with self.store.transaction() as db:
            self.limits.consume_in_transaction(db,context.actor_id,"checklist")
            customer,agent,expires=self._participants(db,request_id)
            if now>=expires:
                raise LabError("QUOTE_EXPIRED")
            if context.actor_id not in (customer,agent):
                raise LabError("ROLE_FORBIDDEN")
            actor=db.execute("SELECT role,state FROM lab_actors WHERE actor_id=?",(context.actor_id,)).fetchone()
            if actor is None or actor["state"]!="active" or actor["role"]!=context.role:
                raise LabError("ROLE_FORBIDDEN")
            row=db.execute("SELECT * FROM lab_cash_ack WHERE request_id=?",(request_id,)).fetchone()
            if row is None:
                db.execute("INSERT INTO lab_cash_ack(request_id,customer_id,agent_id,status,created_at,updated_at) VALUES(?,?,?,'waiting',?,?)",
                           (request_id,customer,agent,now,now))
                row=db.execute("SELECT * FROM lab_cash_ack WHERE request_id=?",(request_id,)).fetchone()
            if row["status"]=="cancelled":
                raise LabError("REQUEST_FINAL")
            own_field="customer_ref_digest" if context.actor_id==customer else "agent_ref_digest"
            other_field="agent_ref_digest" if own_field=="customer_ref_digest" else "customer_ref_digest"
            existing=row[own_field]
            if existing is not None:
                if existing!=hashed:
                    raise LabError("REPLAY_BLOCKED")
                return self.from_row(row)
            if row[other_field] is not None and row[other_field]==hashed:
                raise LabError("REPLAY_BLOCKED")
            self.replay.claim_in_transaction(db,actor_id=context.actor_id,purpose="cash_checklist",
                                              nonce=review_reference,expires_at=expires,now=now)
            next_status="both_reviewed" if row[other_field] else "waiting"
            db.execute(f"UPDATE lab_cash_ack SET {own_field}=?,status=?,updated_at=? WHERE request_id=?",
                       (hashed,next_status,now,request_id))
            self.audit.append_in_transaction(db,actor=context.actor_id,kind="cash_acknowledged",
                                             data={"request":request_id,"reviewer_role":context.role},
                                             event_id=new_reference("audit"))
            next_row=db.execute("SELECT * FROM lab_cash_ack WHERE request_id=?",(request_id,)).fetchone()
            return self.from_row(next_row)

    def cancel(self,context:SessionContext,request_id:str)->TwoPartyPreview:
        synthetic_id(request_id)
        with self.store.transaction() as db:
            row=db.execute("SELECT * FROM lab_cash_ack WHERE request_id=?",(request_id,)).fetchone()
            if row is None:
                raise LabError("NOT_FOUND")
            if context.actor_id not in (row["customer_id"],row["agent_id"]):
                raise LabError("ROLE_FORBIDDEN")
            if row["status"]!="cancelled":
                db.execute("UPDATE lab_cash_ack SET status='cancelled',updated_at=? WHERE request_id=?",
                           (self.store.clock.now(),request_id))
                self.audit.append_in_transaction(db,actor=context.actor_id,kind="cash_ack_cancelled",
                                                 data={"request":request_id},event_id=new_reference("audit"))
            result=db.execute("SELECT * FROM lab_cash_ack WHERE request_id=?",(request_id,)).fetchone()
            return self.from_row(result)

    def real_handover(self,context:SessionContext,request_id:str)->None:
        self.get(context,request_id)
        deny_posting()
