"""Private synthetic customer-support drafts, not external complaints handling."""
from __future__ import annotations
from dataclasses import dataclass
import re
from .audit import AccessAudit
from .crypto import new_reference
from .errors import LabError,require
from .identifiers import safe_note,synthetic_id
from .policy import AccessPolicy
from .rate_limits import RateLimiter
from .sessions import SessionContext
from .store import LabStore

CATEGORIES=frozenset({"question","privacy","incorrect_quote","suspected_fraud"})
SENSITIVE_PATTERNS=(
    re.compile(r"\b\d{10,19}\b"),
    re.compile(r"[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\b(?:bearer|secret|pass(?:word)?|token)\s*[:=]\s*\S+",re.I),
    re.compile(r"\b(?:\+?880|0)1[3-9]\d{8}\b"),
)


def redact_support(message:str)->str:
    clean=safe_note(message,max_length=500)
    if not clean or len(clean)<10:
        raise LabError("INVALID_INPUT")
    for pattern in SENSITIVE_PATTERNS:
        clean=pattern.sub("[REDACTED]",clean)
    return clean[:500]


@dataclass(frozen=True)
class SupportDraft:
    id:str
    owner_id:str
    category:str
    description:str
    status:str
    created_at:int
    simulation:bool=True
    submitted_to_provider:bool=False

    def public(self)->dict[str,object]:
        return {"case_id":self.id,"category":self.category,"description":self.description,
                "status":self.status,"created_at":self.created_at,"simulation":True,
                "submitted_to_provider":False}


class SupportService:
    def __init__(self,store:LabStore):
        self.store=store
        self.audit=AccessAudit(store)
        self.limits=RateLimiter(store)

    def create_draft(self,context:SessionContext,*,category:str,description:str)->SupportDraft:
        AccessPolicy.require(context,"support:create",resource_owner=context.actor_id)
        require(category in CATEGORIES,"INVALID_INPUT")
        clean=redact_support(description)
        now=self.store.clock.now()
        case_id=new_reference("support")
        with self.store.transaction() as db:
            self.limits.consume_in_transaction(db,context.actor_id,"support")
            db.execute("INSERT INTO lab_support(case_id,actor_id,category,safe_description,status,created_at,updated_at) VALUES(?,?,?,?,'draft',?,?)",
                       (case_id,context.actor_id,category,clean,now,now))
            self.audit.append_in_transaction(db,actor=context.actor_id,kind="support_draft",
                                             data={"case":case_id,"category":category},event_id=new_reference("audit"))
        return SupportDraft(case_id,context.actor_id,category,clean,"draft",now)

    def list(self,context:SessionContext,limit:int=30)->list[SupportDraft]:
        AccessPolicy.require(context,"support:read",resource_owner=context.actor_id)
        require(type(limit) is int and 1<=limit<=100,"INVALID_INPUT")
        with self.store.read() as db:
            rows=db.execute("SELECT * FROM lab_support WHERE actor_id=? ORDER BY created_at DESC,case_id DESC LIMIT ?",
                            (context.actor_id,limit)).fetchall()
        return [SupportDraft(x["case_id"],x["actor_id"],x["category"],x["safe_description"],
                             x["status"],x["created_at"]) for x in rows]

    def close(self,context:SessionContext,case_id:str)->SupportDraft:
        AccessPolicy.require(context,"support:read",resource_owner=context.actor_id)
        synthetic_id(case_id)
        with self.store.transaction() as db:
            row=db.execute("SELECT * FROM lab_support WHERE case_id=? AND actor_id=?",(case_id,context.actor_id)).fetchone()
            if row is None:
                raise LabError("NOT_FOUND")
            if row["status"]!="closed":
                db.execute("UPDATE lab_support SET status='closed',updated_at=? WHERE case_id=?",
                           (self.store.clock.now(),case_id))
                self.audit.append_in_transaction(db,actor=context.actor_id,kind="support_closed",
                                                 data={"case":case_id},event_id=new_reference("audit"))
            return SupportDraft(case_id,context.actor_id,row["category"],row["safe_description"],"closed",row["created_at"])

    def submit_external(self,*_:object,**__:object)->None:
        raise LabError("PROVIDER_ABSENT")
