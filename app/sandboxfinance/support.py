"""Agent/customer helpdesk and suspicious-activity queue for synthetic accounts.

Support investigators cannot edit posted financial events, change a cash handover
state, or issue a refund. This module records only minimal evidence digests and
reason codes. Every decision is reviewable; it is not a real support desk.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime,timezone,timedelta
import hashlib
import json
import secrets
import sqlite3
from typing import Iterable

from .identity import SyntheticRegistry
from .ledger import SandboxLedger


class SupportError(ValueError):
    pass


class SupportPermissionError(SupportError):
    pass


class SupportStateError(SupportError):
    pass


CATEGORIES=frozenset({"cash_handover","agent_conduct","suspicious_activity",
                      "account_access","merchant_payment","loan_experiment","other"})
PRIORITIES=frozenset({"low","normal","high","critical"})
STATES=frozenset({"open","triage","awaiting_operator","awaiting_evidence",
                  "resolved","rejected","closed"})
TRANSITIONS={
    "open":frozenset({"triage","awaiting_operator","rejected"}),
    "triage":frozenset({"awaiting_operator","awaiting_evidence","resolved","rejected"}),
    "awaiting_operator":frozenset({"triage","awaiting_evidence","resolved","rejected"}),
    "awaiting_evidence":frozenset({"triage","awaiting_operator","rejected"}),
    "resolved":frozenset({"closed"}),
    "rejected":frozenset({"closed"}),
    "closed":frozenset(),
}


@dataclass(frozen=True)
class SupportTicket:
    ticket_id:str
    reporter_id:str
    category:str
    priority:str
    status:str
    reference_digest:str
    description_code:str
    assigned_operator:str|None
    opened_at:str
    due_at:str
    resolution_digest:str|None=None
    simulation:bool=True


SCHEMA="""
CREATE TABLE IF NOT EXISTS sim_support_tickets(
 ticket_id TEXT PRIMARY KEY,reporter_id TEXT NOT NULL,
 category TEXT NOT NULL,priority TEXT NOT NULL,status TEXT NOT NULL,
 reference_digest TEXT NOT NULL,description_code TEXT NOT NULL,
 assigned_operator TEXT,opened_at TEXT NOT NULL,due_at TEXT NOT NULL,
 resolution_digest TEXT
);
CREATE TABLE IF NOT EXISTS sim_support_evidence(
 evidence_id TEXT PRIMARY KEY,ticket_id TEXT NOT NULL REFERENCES sim_support_tickets(ticket_id),
 document_digest TEXT NOT NULL,evidence_type TEXT NOT NULL,
 submitted_by TEXT NOT NULL,created_at TEXT NOT NULL,
 UNIQUE(ticket_id,document_digest)
);
CREATE TABLE IF NOT EXISTS sim_support_audit(
 audit_id INTEGER PRIMARY KEY AUTOINCREMENT,ticket_id TEXT NOT NULL,
 from_state TEXT,to_state TEXT NOT NULL,actor_id TEXT NOT NULL,
 reason_code TEXT NOT NULL,recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sim_support_priority_status ON sim_support_tickets(priority,status);
CREATE TRIGGER IF NOT EXISTS sim_support_audit_immutable_update BEFORE UPDATE ON sim_support_audit
 BEGIN SELECT RAISE(ABORT,'support audit immutable'); END;
CREATE TRIGGER IF NOT EXISTS sim_support_audit_immutable_delete BEFORE DELETE ON sim_support_audit
 BEGIN SELECT RAISE(ABORT,'support audit immutable'); END;
"""


def _utc()->datetime:
    return datetime.now(timezone.utc)


def _iso(t:datetime)->str:
    return t.isoformat(timespec="microseconds")


def _digest(text:str)->str:
    return hashlib.sha256(text.encode()).hexdigest()


def _view(row:sqlite3.Row)->SupportTicket:
    return SupportTicket(row["ticket_id"],row["reporter_id"],row["category"],
                         row["priority"],row["status"],row["reference_digest"],
                         row["description_code"],row["assigned_operator"],row["opened_at"],
                         row["due_at"],row["resolution_digest"])


class SyntheticSupportDesk:
    def __init__(self,ledger:SandboxLedger,registry:SyntheticRegistry):
        self.ledger=ledger
        self.registry=registry
        with ledger._lock,ledger._connect() as db:
            db.executescript(SCHEMA)

    def _party(self,subject_id:str,*,operator:bool=False):
        party=self.registry.lookup(subject_id)
        if party.status!="sandbox_verified":
            raise SupportPermissionError("Synthetic actor is not enabled")
        if operator and party.role!="operator":
            raise SupportPermissionError("Only a synthetic reviewer may decide")
        return party

    def _load(self,db:sqlite3.Connection,ticket_id:str):
        row=db.execute("SELECT * FROM sim_support_tickets WHERE ticket_id=?",(ticket_id,)).fetchone()
        if row is None:
            raise SupportError("Support case not found")
        return row

    def _audit(self,db:sqlite3.Connection,ticket_id:str,old:str|None,new:str,
               actor:str,reason:str):
        db.execute("INSERT INTO sim_support_audit(ticket_id,from_state,to_state,actor_id,reason_code,recorded_at) "
                   "VALUES(?,?,?,?,?,?)",(ticket_id,old,new,actor,reason,_iso(_utc())))

    def open(self,*,reporter_id:str,category:str,priority:str,
             related_reference:str,description_code:str)->SupportTicket:
        self._party(reporter_id)
        if category not in CATEGORIES or priority not in PRIORITIES:
            raise SupportError("Unknown synthetic support category or priority")
        if not isinstance(related_reference,str) or not 3<=len(related_reference)<=180:
            raise SupportError("Invalid related reference")
        if not isinstance(description_code,str) or not 4<=len(description_code)<=80:
            raise SupportError("Use a short non-PII issue code")
        ticket_id="sim_ticket_"+secrets.token_hex(12)
        now=_utc()
        due=now+timedelta(hours=2 if priority=="critical" else
                          12 if priority=="high" else 48 if priority=="normal" else 96)
        with self.ledger._lock,self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute("INSERT INTO sim_support_tickets VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                           (ticket_id,reporter_id,category,priority,"open",
                            _digest(related_reference),description_code,None,
                            _iso(now),_iso(due),None))
                self._audit(db,ticket_id,None,"open",reporter_id,"synthetic_report_created")
                db.commit()
            except Exception:
                db.rollback()
                raise
        return self.ticket(ticket_id)

    def ticket(self,ticket_id:str)->SupportTicket:
        with self.ledger._connect() as db:
            return _view(self._load(db,ticket_id))

    def assign(self,ticket_id:str,*,operator_id:str)->SupportTicket:
        self._party(operator_id,operator=True)
        with self.ledger._lock,self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row=self._load(db,ticket_id)
                if row["status"] in ("closed","rejected"):
                    raise SupportStateError("Closed or rejected synthetic ticket cannot be assigned")
                db.execute("UPDATE sim_support_tickets SET assigned_operator=? WHERE ticket_id=?",
                           (operator_id,ticket_id))
                self._audit(db,ticket_id,row["status"],row["status"],operator_id,"reviewer_assigned")
                db.commit()
            except Exception:
                db.rollback()
                raise
        return self.ticket(ticket_id)

    def add_evidence(self,ticket_id:str,*,actor_id:str,evidence_digest:str,
                     evidence_type:str)->str:
        self._party(actor_id)
        if not isinstance(evidence_digest,str) or len(evidence_digest)!=64 or (
            any(c not in "0123456789abcdef" for c in evidence_digest)):
            raise SupportError("Only a SHA-256 digest may be submitted")
        if evidence_type not in ("simulation_log","review_note_digest","transaction_digest"):
            raise SupportError("Unrecognized non-PII evidence type")
        eid="sim_evidence_"+secrets.token_hex(12)
        with self.ledger._lock,self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row=self._load(db,ticket_id)
                if actor_id not in (row["reporter_id"],row["assigned_operator"]):
                    raise SupportPermissionError("Reporter or assigned reviewer must submit evidence")
                if row["status"]=="closed":
                    raise SupportStateError("Closed case cannot accept evidence")
                db.execute("INSERT INTO sim_support_evidence VALUES(?,?,?,?,?,?)",
                           (eid,ticket_id,evidence_digest,evidence_type,actor_id,_iso(_utc())))
                self._audit(db,ticket_id,row["status"],row["status"],actor_id,"evidence_digest_added")
                db.commit()
            except sqlite3.IntegrityError as exc:
                db.rollback()
                raise SupportError("Duplicate evidence digest") from exc
            except Exception:
                db.rollback()
                raise
        return eid

    def transition(self,ticket_id:str,*,operator_id:str,to_state:str,
                   reason_code:str,resolution_digest:str|None=None)->SupportTicket:
        self._party(operator_id,operator=True)
        if not isinstance(reason_code,str) or not 4<=len(reason_code)<=120:
            raise SupportError("Require non-PII transition reason")
        if to_state not in STATES:
            raise SupportError("Unknown case status")
        if resolution_digest is not None and (len(resolution_digest)!=64 or
            any(c not in "0123456789abcdef" for c in resolution_digest)):
            raise SupportError("Resolution must be SHA-256 digest")
        if to_state in ("resolved","rejected") and not resolution_digest:
            raise SupportError("Final decision requires evidence digest")
        with self.ledger._lock,self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row=self._load(db,ticket_id)
                if to_state not in TRANSITIONS[row["status"]]:
                    raise SupportStateError("Illegal or replayed case transition")
                if row["assigned_operator"]!=operator_id:
                    raise SupportPermissionError("Reviewer not assigned to this case")
                db.execute("UPDATE sim_support_tickets SET status=?,resolution_digest=COALESCE(?,resolution_digest) "
                           "WHERE ticket_id=?",(to_state,resolution_digest,ticket_id))
                self._audit(db,ticket_id,row["status"],to_state,operator_id,reason_code)
                db.commit()
            except Exception:
                db.rollback()
                raise
        return self.ticket(ticket_id)

    def audit(self,ticket_id:str)->tuple[dict,...]:
        with self.ledger._connect() as db:
            self._load(db,ticket_id)
            return tuple(dict(row) for row in db.execute(
                "SELECT from_state,to_state,actor_id,reason_code,recorded_at FROM sim_support_audit "
                "WHERE ticket_id=? ORDER BY audit_id",(ticket_id,)).fetchall())

    def backlog(self,*,as_of:datetime|None=None)->dict:
        point=as_of or _utc()
        if point.tzinfo is None:
            raise SupportError("Timezone-aware clock required")
        with self.ledger._connect() as db:
            open_rows=db.execute("SELECT priority,status,due_at FROM sim_support_tickets "
                                 "WHERE status NOT IN ('closed','rejected','resolved')").fetchall()
        priorities={p:0 for p in PRIORITIES}
        overdue=0
        for row in open_rows:
            priorities[row["priority"]]+=1
            overdue+=int(datetime.fromisoformat(row["due_at"])<point)
        return {"simulation":True,"cases_open":len(open_rows),"by_priority":priorities,
                "past_due_count":overdue,"customer_funds_affected_real":0}

    def evidence_digests(self,ticket_id:str)->tuple[str,...]:
        with self.ledger._connect() as db:
            self._load(db,ticket_id)
            return tuple(row[0] for row in db.execute(
                "SELECT document_digest FROM sim_support_evidence WHERE ticket_id=? ORDER BY evidence_id",
                (ticket_id,)).fetchall())
