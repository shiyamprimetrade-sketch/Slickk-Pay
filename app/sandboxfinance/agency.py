"""Synthetic agent electronic-float replenishment and liquidity planning.

This module never buys, transports, or releases physical currency. Each float
replenishment requires a separately approved fictional operator and is funded
from the finite sandbox treasury through balanced journal postings.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3
import secrets

from .ledger import SandboxLedger,Posting,InsufficientFunds
from .identity import SyntheticRegistry
from .pricing import initial_pilot,PilotPricing


class AgencyError(ValueError):
    pass


class AgencyStateError(AgencyError):
    pass


@dataclass(frozen=True)
class FloatRequest:
    request_id:str
    agent_id:str
    amount_poisha:int
    state:str
    reason:str
    submitted_at:str
    approved_by:str|None=None
    event_id:str|None=None
    simulated:bool=True


SCHEMA="""
CREATE TABLE IF NOT EXISTS sim_float_requests (
 request_id TEXT PRIMARY KEY,agent_id TEXT NOT NULL,
 amount_poisha INTEGER NOT NULL CHECK(amount_poisha>0),
 state TEXT NOT NULL CHECK(state IN ('pending','approved','rejected','cancelled')),
 reason TEXT NOT NULL,submitted_at TEXT NOT NULL,
 approved_by TEXT,event_id TEXT
);
CREATE TABLE IF NOT EXISTS sim_float_audit (
 audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
 request_id TEXT NOT NULL,from_state TEXT,to_state TEXT NOT NULL,
 actor_id TEXT NOT NULL,reason TEXT NOT NULL,timestamp_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sim_float_agent_state ON sim_float_requests(agent_id,state);
CREATE TRIGGER IF NOT EXISTS sim_float_audit_lock_update BEFORE UPDATE ON sim_float_audit
 BEGIN SELECT RAISE(ABORT,'immutable float request audit'); END;
CREATE TRIGGER IF NOT EXISTS sim_float_audit_lock_delete BEFORE DELETE ON sim_float_audit
 BEGIN SELECT RAISE(ABORT,'immutable float request audit'); END;
"""


def _time()->str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _view(row:sqlite3.Row)->FloatRequest:
    return FloatRequest(row["request_id"],row["agent_id"],row["amount_poisha"],
                        row["state"],row["reason"],row["submitted_at"],
                        row["approved_by"],row["event_id"])


class AgentLiquidityDesk:
    def __init__(self,ledger:SandboxLedger,registry:SyntheticRegistry):
        self.ledger=ledger
        self.registry=registry
        with ledger._lock,ledger._connect() as db:
            db.executescript(SCHEMA)

    def _party(self,party_id:str,role:str)->None:
        party=self.registry.lookup(party_id,required_role=role)
        if party.status!="sandbox_verified":
            raise AgencyError("Only approved synthetic accounts can act")

    def _audit(self,db:sqlite3.Connection,ref:str,old:str|None,new:str,
               actor:str,reason:str)->None:
        db.execute("INSERT INTO sim_float_audit(request_id,from_state,to_state,actor_id,reason,timestamp_utc) "
                   "VALUES(?,?,?,?,?,?)",(ref,old,new,actor,reason,_time()))

    def request_float(self,agent_id:str,amount_poisha:int,*,reason:str)->FloatRequest:
        self._party(agent_id,"agent")
        if isinstance(amount_poisha,bool) or not isinstance(amount_poisha,int) or not 100<=amount_poisha<=5_000_000:
            raise AgencyError("Requested fictional float outside pilot bounds")
        if not isinstance(reason,str) or not 6<=len(reason)<=160:
            raise AgencyError("Require a clear synthetic liquidity reason")
        request_id="sim_floatreq_"+secrets.token_hex(12)
        with self.ledger._lock,self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                if db.execute("SELECT COUNT(*) FROM sim_float_requests WHERE agent_id=? AND state='pending'",
                              (agent_id,)).fetchone()[0]>=3:
                    raise AgencyError("Agent has too many unreviewed replenishments")
                db.execute("INSERT INTO sim_float_requests VALUES(?,?,?,?,?,?,?,?)",
                           (request_id,agent_id,amount_poisha,"pending",reason,_time(),None,None))
                self._audit(db,request_id,None,"pending",agent_id,"synthetic_agent_request")
                db.commit()
            except Exception:
                db.rollback()
                raise
        return self.request(request_id)

    def request(self,request_id:str)->FloatRequest:
        with self.ledger._connect() as db:
            row=db.execute("SELECT * FROM sim_float_requests WHERE request_id=?",(request_id,)).fetchone()
        if row is None:
            raise AgencyError("Float request not found")
        return _view(row)

    def decide(self,request_id:str,*,operator_id:str,approve:bool,reason:str)->FloatRequest:
        self._party(operator_id,"operator")
        if not isinstance(approve,bool) or not isinstance(reason,str) or len(reason)<6:
            raise AgencyError("An explicit operator decision is required")
        with self.ledger._lock,self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row=db.execute("SELECT * FROM sim_float_requests WHERE request_id=?",(request_id,)).fetchone()
                if row is None or row["state"]!="pending":
                    raise AgencyStateError("Replenishment is terminal or unknown")
                state="approved" if approve else "rejected"
                event_id=None
                if approve:
                    receipt=self.ledger.post_in_transaction(
                        db,operation="synthetic_agent_float_replenishment",
                        idempotency_key=request_id+":float",
                        postings=[Posting("sim_platform_treasury","debit",row["amount_poisha"]),
                                  Posting("sim_float_"+row["agent_id"][4:],"credit",row["amount_poisha"])])
                    event_id=receipt.event_id
                db.execute("UPDATE sim_float_requests SET state=?,approved_by=?,event_id=? WHERE request_id=?",
                           (state,operator_id,event_id,request_id))
                self._audit(db,request_id,"pending",state,operator_id,reason)
                db.commit()
            except Exception:
                db.rollback()
                raise
        return self.request(request_id)

    def cancel(self,request_id:str,*,agent_id:str)->FloatRequest:
        self._party(agent_id,"agent")
        with self.ledger._lock,self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row=db.execute("SELECT * FROM sim_float_requests WHERE request_id=?",(request_id,)).fetchone()
                if not row or row["agent_id"]!=agent_id or row["state"]!="pending":
                    raise AgencyStateError("Cannot cancel this agent float request")
                db.execute("UPDATE sim_float_requests SET state='cancelled' WHERE request_id=?",(request_id,))
                self._audit(db,request_id,"pending","cancelled",agent_id,"synthetic_agent_cancel")
                db.commit()
            except Exception:
                db.rollback()
                raise
        return self.request(request_id)

    def agent_float_position(self,agent_id:str)->dict:
        self._party(agent_id,"agent")
        account=self.ledger.account("sim_float_"+agent_id[4:])
        with self.ledger._connect() as db:
            pending=db.execute("SELECT COALESCE(SUM(amount_poisha),0) FROM sim_float_requests "
                               "WHERE agent_id=? AND state='pending'",(agent_id,)).fetchone()[0]
        return {"simulation":True,"agent_id":agent_id,"electronic_float_poisha":account.balance_poisha,
                "pending_synthetic_replenishment_poisha":pending,
                "real_cash_or_bank_funding_confirmed":False}

    def demand_scenario(self,agent_id:str,*,projected_cash_in_count:int,
                        projected_cash_out_count:int,average_ticket_poisha:int,
                        cash_inventory_poisha:int,pricing:PilotPricing|None=None)->dict:
        self._party(agent_id,"agent")
        for n in (projected_cash_in_count,projected_cash_out_count,average_ticket_poisha,
                  cash_inventory_poisha):
            if isinstance(n,bool) or not isinstance(n,int) or n<0:
                raise AgencyError("Invalid demand scenario")
        engine=pricing or initial_pilot()
        expected_cash_in=projected_cash_in_count*average_ticket_poisha
        expected_cash_out=projected_cash_out_count*average_ticket_poisha
        available_float=self.ledger.account("sim_float_"+agent_id[4:]).balance_poisha
        return {
            "simulation":True,"agent_id":agent_id,
            "projected_cash_in_poisha":expected_cash_in,
            "projected_cash_out_poisha":expected_cash_out,
            "projected_float_after_poisha":available_float-expected_cash_in+expected_cash_out,
            "projected_cash_after_poisha":cash_inventory_poisha+expected_cash_in-expected_cash_out,
            "float_shortfall_poisha":max(0,expected_cash_in-expected_cash_out-available_float),
            "physical_cash_shortfall_poisha":max(0,expected_cash_out-cash_inventory_poisha-expected_cash_in),
            "expected_commission_poisha":(
                engine.quote("cash_in",average_ticket_poisha).agent_commission*projected_cash_in_count
                if projected_cash_in_count else 0)+(
                engine.quote("cash_out",average_ticket_poisha).agent_commission*projected_cash_out_count
                if projected_cash_out_count else 0),
            "liquidity_verified_by_bank":False,
        }

    def audit(self,request_id:str)->tuple[dict,...]:
        self.request(request_id)
        with self.ledger._connect() as db:
            return tuple(dict(row) for row in db.execute(
                "SELECT from_state,to_state,actor_id,reason,timestamp_utc FROM sim_float_audit "
                "WHERE request_id=? ORDER BY audit_id",(request_id,)).fetchall())
