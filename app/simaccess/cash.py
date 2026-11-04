"""Agent cash availability and handover *checklist*, not cash authorization.

Physical handover has no implementation. Checklist completion cannot change
ledger balances or make a request paid; every response declares it prohibited.
"""
from __future__ import annotations
from dataclasses import dataclass
import sqlite3
from .audit import AccessAudit
from .crypto import new_reference
from .errors import LabError,require,deny_posting
from .identifiers import synthetic_id
from .policy import AccessPolicy
from .rate_limits import RateLimiter
from .sessions import SessionContext
from .store import LabStore


@dataclass(frozen=True)
class CashChecklist:
    request_id:str
    agent_id:str
    cash_available:bool
    customer_present:bool
    warnings_acknowledged:bool
    updated_at:int
    simulation:bool=True
    handover_authorized:bool=False

    def public(self)->dict[str,object]:
        return {"request_id":self.request_id,"agent_id":self.agent_id,
                "cash_available":self.cash_available,"customer_present":self.customer_present,
                "warnings_acknowledged":self.warnings_acknowledged,"updated_at":self.updated_at,
                "handover_authorized":False,"ledger_posted":False,"simulation":True,
                "next_action":"AUTHENTICATED_SERVER_CASH_PROTOCOL_REQUIRED"}


class AgentCashChecklist:
    def __init__(self,store:LabStore):
        self.store=store
        self.audit=AccessAudit(store)
        self.limits=RateLimiter(store)

    @staticmethod
    def _to_result(row:sqlite3.Row)->CashChecklist:
        return CashChecklist(row["request_id"],row["agent_id"],bool(row["cash_available"]),
                             bool(row["customer_present"]),bool(row["warnings_acknowledged"]),row["updated_at"])

    def inspect(self,context:SessionContext,request_id:str)->CashChecklist:
        AccessPolicy.require(context,"cash:checklist",resource_owner=context.actor_id)
        synthetic_id(request_id)
        with self.store.read() as db:
            row=db.execute("SELECT * FROM lab_cash_checklists WHERE request_id=? AND agent_id=?",
                           (request_id,context.actor_id)).fetchone()
        if row is None:
            raise LabError("NOT_FOUND")
        return self._to_result(row)

    def create(self,context:SessionContext,*,request_id:str)->CashChecklist:
        AccessPolicy.require(context,"cash:checklist",resource_owner=context.actor_id)
        synthetic_id(request_id)
        now=self.store.clock.now()
        with self.store.transaction() as db:
            self.limits.consume_in_transaction(db,context.actor_id,"checklist")
            request=db.execute("SELECT r.*,q.counterpart_id,q.operation FROM lab_requests r JOIN lab_quotes q ON q.quote_id=r.quote_id WHERE r.request_id=?",
                               (request_id,)).fetchone()
            if request is None or request["operation"] not in ("cash_out","cash_in"):
                raise LabError("NOT_FOUND")
            if request["operation"]=="cash_out":
                agent_id=request["counterpart_id"]
            else:
                agent_id=request["owner_id"]
            if agent_id!=context.actor_id:
                raise LabError("ROLE_FORBIDDEN")
            if request["status"]!="reviewed":
                raise LabError("REQUEST_FINAL")
            row=db.execute("SELECT * FROM lab_cash_checklists WHERE request_id=?",(request_id,)).fetchone()
            if row:
                return self._to_result(row)
            db.execute("INSERT INTO lab_cash_checklists(request_id,agent_id,cash_available,customer_present,warnings_acknowledged,updated_at) VALUES(?,?,0,0,0,?)",
                       (request_id,context.actor_id,now))
            self.audit.append_in_transaction(db,actor=context.actor_id,kind="cash_checklist",
                                             data={"request":request_id,"created":True},event_id=new_reference("audit"))
        return CashChecklist(request_id,context.actor_id,False,False,False,now)

    def update(self,context:SessionContext,*,request_id:str,cash_available:bool|None=None,
               customer_present:bool|None=None,warnings_acknowledged:bool|None=None)->CashChecklist:
        AccessPolicy.require(context,"cash:checklist",resource_owner=context.actor_id)
        synthetic_id(request_id)
        for flag in (cash_available,customer_present,warnings_acknowledged):
            if flag is not None and type(flag) is not bool:
                raise LabError("INVALID_INPUT")
        now=self.store.clock.now()
        with self.store.transaction() as db:
            self.limits.consume_in_transaction(db,context.actor_id,"checklist")
            row=db.execute("SELECT * FROM lab_cash_checklists WHERE request_id=? AND agent_id=?",
                           (request_id,context.actor_id)).fetchone()
            if row is None:
                raise LabError("NOT_FOUND")
            status=db.execute("SELECT status FROM lab_requests WHERE request_id=?",(request_id,)).fetchone()
            if status is None or status["status"]!="reviewed":
                raise LabError("REQUEST_FINAL")
            chosen={"cash_available":row["cash_available"] if cash_available is None else int(cash_available),
                    "customer_present":row["customer_present"] if customer_present is None else int(customer_present),
                    "warnings_acknowledged":row["warnings_acknowledged"] if warnings_acknowledged is None else int(warnings_acknowledged)}
            db.execute("UPDATE lab_cash_checklists SET cash_available=?,customer_present=?,warnings_acknowledged=?,updated_at=? WHERE request_id=?",
                       (*chosen.values(),now,request_id))
            self.audit.append_in_transaction(db,actor=context.actor_id,kind="cash_checklist",
                                             data={"request":request_id,"flags":chosen},event_id=new_reference("audit"))
            return CashChecklist(request_id,context.actor_id,bool(chosen["cash_available"]),
                                 bool(chosen["customer_present"]),bool(chosen["warnings_acknowledged"]),now)

    def handover(self,context:SessionContext,request_id:str)->None:
        self.inspect(context,request_id)
        deny_posting()

    def simulated_float_alert(self,*,cash_poisha:int,requested_poisha:int,limit_poisha:int)->dict[str,object]:
        from .identifiers import minor_units
        for n in (cash_poisha,requested_poisha,limit_poisha):
            minor_units(n,zero_ok=True)
        shortfall=max(0,requested_poisha-cash_poisha)
        return {"cash_available_poisha":cash_poisha,"requested_poisha":requested_poisha,
                "cash_shortfall_poisha":shortfall,"float_capacity_poisha":limit_poisha,
                "needs_human_review":bool(shortfall) or requested_poisha>limit_poisha,
                "simulation":True,"authoritative":False,"can_handover":False}
