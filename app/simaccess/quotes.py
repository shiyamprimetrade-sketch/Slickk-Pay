"""Durable fee quotes with fingerprinted idempotency and strict role scope.

A reviewed quote is a saved preview, never a posted payment. Transactions are
always server-authoritative; this service intentionally lacks a ledger adapter.
"""
from __future__ import annotations
from dataclasses import asdict,dataclass
import json
import sqlite3
from .audit import AccessAudit
from .crypto import new_reference
from .errors import LabError,require
from .identifiers import canonical,digest,event_ref,minor_units,synthetic_id
from .policy import AccessPolicy
from .pricing import PricingEngine,QuoteDisclosure
from .sessions import SessionContext
from .store import LabStore
from .rate_limits import RateLimiter


@dataclass(frozen=True)
class StoredQuote:
    id:str
    owner_id:str
    operation:str
    counterpart_id:str
    principal_poisha:int
    fee_poisha:int
    total_poisha:int
    rate_version:str
    created_at:int
    expires_at:int
    fingerprint:str
    status:str
    source_ref:str
    simulation:bool=True
    can_execute:bool=False

    def public(self)->dict[str,object]:
        return {"quote_id":self.id,"owner_id":self.owner_id,"operation":self.operation,
                "counterpart_id":self.counterpart_id,"principal_poisha":self.principal_poisha,
                "fee_poisha":self.fee_poisha,"total_poisha":self.total_poisha,
                "version":self.rate_version,"status":self.status,"expires_at":self.expires_at,
                "simulation":True,"can_execute":False,"real_money":False,
                "tax_unverified":True}


class QuoteService:
    def __init__(self,store:LabStore,pricing:PricingEngine|None=None):
        self.store=store
        self.pricing=pricing or PricingEngine()
        self.audit=AccessAudit(store)
        self.rate=RateLimiter(store)

    @staticmethod
    def _from_row(row:sqlite3.Row)->StoredQuote:
        return StoredQuote(row["quote_id"],row["owner_id"],row["operation"],row["counterpart_id"],
                           row["principal_poisha"],row["fee_poisha"],row["total_poisha"],
                           row["rate_version"],row["created_at"],row["expires_at"],
                           row["fingerprint"],row["status"],row["source_ref"])

    def quote(self,*,context:SessionContext,operation:str,counterpart_id:str,
              principal_poisha:int,source_ref:str,lifetime_seconds:int=180)->StoredQuote:
        AccessPolicy.require(context,"quote:create",resource_owner=context.actor_id)
        synthetic_id(counterpart_id)
        minor_units(principal_poisha)
        event_ref(source_ref)
        require(type(lifetime_seconds) is int and 30<=lifetime_seconds<=600,"INVALID_INPUT")
        if counterpart_id==context.actor_id:
            raise LabError("INVALID_INPUT")
        if operation=="cash_in" and context.role!="agent":
            raise LabError("ROLE_FORBIDDEN")
        if operation=="cash_out" and context.role!="customer":
            raise LabError("ROLE_FORBIDDEN")
        if operation=="merchant_payment" and context.role!="customer":
            raise LabError("ROLE_FORBIDDEN")
        if operation=="transfer" and context.role!="customer":
            raise LabError("ROLE_FORBIDDEN")
        result=self.pricing.quote(operation,principal_poisha)
        now=self.store.clock.now()
        evidence={"actor":context.actor_id,"operation":operation,"counterpart":counterpart_id,
                  "principal":principal_poisha,"fee":result.customer_fee_poisha,
                  "version":result.version,"expires":now+lifetime_seconds}
        # TTL is not part of idempotency fingerprint; a replay retains original TTL.
        fingerprint=digest(canonical({k:v for k,v in evidence.items() if k!="expires"}).decode())
        with self.store.transaction() as db:
            existing=db.execute("SELECT * FROM lab_quotes WHERE owner_id=? AND source_ref=?",
                                (context.actor_id,source_ref)).fetchone()
            if existing:
                if existing["fingerprint"]!=fingerprint:
                    raise LabError("CONFLICT")
                return self._from_row(existing)
            self.rate.consume_in_transaction(db,context.actor_id,"quote")
            other=db.execute("SELECT role,state FROM lab_actors WHERE actor_id=?",(counterpart_id,)).fetchone()
            if other is None or other["state"]!="active":
                raise LabError("NOT_FOUND")
            intended={"transfer":"customer","cash_in":"customer","cash_out":"agent","merchant_payment":"merchant"}[operation]
            if other["role"]!=intended:
                raise LabError("ROLE_FORBIDDEN")
            quote_id=new_reference("quote")
            expires=now+lifetime_seconds
            db.execute("INSERT INTO lab_quotes(quote_id,owner_id,operation,counterpart_id,principal_poisha,fee_poisha,total_poisha,rate_version,created_at,expires_at,fingerprint,status,source_ref) VALUES(?,?,?,?,?,?,?,?,?,?,?,'quoted',?)",
                       (quote_id,context.actor_id,operation,counterpart_id,principal_poisha,
                        result.customer_fee_poisha,result.customer_total_poisha,result.version,
                        now,expires,fingerprint,source_ref))
            self.audit.append_in_transaction(db,actor=context.actor_id,kind="quote_created",
                                             data={"quote":quote_id,"amount":principal_poisha},event_id=new_reference("audit"))
        return StoredQuote(quote_id,context.actor_id,operation,counterpart_id,principal_poisha,
                           result.customer_fee_poisha,result.customer_total_poisha,result.version,
                           now,expires,fingerprint,"quoted",source_ref)

    def get(self,context:SessionContext,quote_id:str)->StoredQuote:
        AccessPolicy.require(context,"request:read",resource_owner=context.actor_id)
        synthetic_id(quote_id)
        with self.store.read() as db:
            row=db.execute("SELECT * FROM lab_quotes WHERE quote_id=? AND owner_id=?",
                           (quote_id,context.actor_id)).fetchone()
        if row is None:
            raise LabError("NOT_FOUND")
        return self._from_row(row)

    def list(self,context:SessionContext,*,limit:int=30)->list[StoredQuote]:
        AccessPolicy.require(context,"request:read",resource_owner=context.actor_id)
        require(type(limit) is int and 1<=limit<=100,"INVALID_INPUT")
        with self.store.read() as db:
            rows=db.execute("SELECT * FROM lab_quotes WHERE owner_id=? ORDER BY created_at DESC,quote_id DESC LIMIT ?",
                            (context.actor_id,limit)).fetchall()
        return [self._from_row(row) for row in rows]

    def cancel(self,context:SessionContext,quote_id:str)->StoredQuote:
        AccessPolicy.require(context,"quote:cancel",resource_owner=context.actor_id)
        synthetic_id(quote_id)
        with self.store.transaction() as db:
            row=db.execute("SELECT * FROM lab_quotes WHERE quote_id=? AND owner_id=?",
                           (quote_id,context.actor_id)).fetchone()
            if row is None:
                raise LabError("NOT_FOUND")
            if row["status"]=="cancelled":
                return self._from_row(row)
            if row["status"]!="quoted":
                raise LabError("REQUEST_FINAL")
            db.execute("UPDATE lab_quotes SET status='cancelled' WHERE quote_id=?",(quote_id,))
            self.audit.append_in_transaction(db,actor=context.actor_id,kind="quote_cancelled",
                                             data={"quote":quote_id},event_id=new_reference("audit"))
            next_row=db.execute("SELECT * FROM lab_quotes WHERE quote_id=?",(quote_id,)).fetchone()
            return self._from_row(next_row)

    def expire_due(self,*,limit:int=100)->int:
        require(type(limit) is int and 1<=limit<=1000,"INVALID_INPUT")
        now=self.store.clock.now()
        expired=0
        with self.store.transaction() as db:
            rows=db.execute("SELECT quote_id,owner_id FROM lab_quotes WHERE status='quoted' AND expires_at<=? ORDER BY expires_at,quote_id LIMIT ?",
                            (now,limit)).fetchall()
            for row in rows:
                db.execute("UPDATE lab_quotes SET status='expired' WHERE quote_id=? AND status='quoted'",(row["quote_id"],))
                self.audit.append_in_transaction(db,actor=row["owner_id"],kind="quote_expired",
                                                 data={"quote":row["quote_id"]},event_id=new_reference("audit"))
                expired+=1
        return expired

    def fresh_in_transaction(self,db:sqlite3.Connection,context:SessionContext,quote_id:str)->StoredQuote:
        row=db.execute("SELECT * FROM lab_quotes WHERE quote_id=? AND owner_id=?",(quote_id,context.actor_id)).fetchone()
        if row is None:
            raise LabError("NOT_FOUND")
        if row["status"]!="quoted":
            raise LabError("REQUEST_FINAL")
        if row["expires_at"]<=self.store.clock.now():
            raise LabError("QUOTE_EXPIRED")
        expected=self.pricing.quote(row["operation"],row["principal_poisha"])
        if expected.version!=row["rate_version"] or expected.customer_fee_poisha!=row["fee_poisha"] or expected.customer_total_poisha!=row["total_poisha"]:
            raise LabError("QUOTE_CHANGED")
        return self._from_row(row)
