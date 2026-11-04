"""Bounded, owner-scoped query helpers for simulated account activity.

These queries never accept dynamic SQL identifiers and never read another
synthetic persona's records. Cursor paging uses stable occurred_at + ID ties.
"""
from __future__ import annotations
from dataclasses import dataclass
from .errors import LabError,require
from .identifiers import synthetic_id
from .policy import AccessPolicy
from .sessions import SessionContext
from .store import LabStore


@dataclass(frozen=True)
class ActivityQuery:
    page_size:int=20
    direction:str|None=None
    status:str|None=None
    before_timestamp:int|None=None
    before_id:str|None=None

    def __post_init__(self)->None:
        require(type(self.page_size) is int and 1<=self.page_size<=100,"INVALID_INPUT")
        require(self.direction is None or self.direction in ("in","out"),"INVALID_INPUT")
        require(self.status is None or self.status in ("sample_paid","sample_cancelled","sample_pending"),"INVALID_INPUT")
        require((self.before_timestamp is None)==(self.before_id is None),"INVALID_INPUT")
        if self.before_timestamp is not None:
            require(type(self.before_timestamp) is int and self.before_timestamp>0,"INVALID_INPUT")
            synthetic_id(self.before_id)


@dataclass(frozen=True)
class ActivityPage:
    rows:tuple[dict[str,object],...]
    next_cursor:tuple[int,str]|None
    total_scanned:int
    simulation:bool=True
    real_transaction_count:int=0

    def public(self)->dict[str,object]:
        return {"rows":list(self.rows),"next_cursor":{"at":self.next_cursor[0],"id":self.next_cursor[1]} if self.next_cursor else None,
                "simulation":True,"real_transaction_count":0}


class ActivitySearch:
    def __init__(self,store:LabStore):
        self.store=store

    def execute(self,context:SessionContext,query:ActivityQuery)->ActivityPage:
        AccessPolicy.require(context,"statement:read",resource_owner=context.actor_id)
        require(isinstance(query,ActivityQuery),"INVALID_INPUT")
        clauses=["actor_id=?"]
        params:list[object]=[context.actor_id]
        if query.direction is not None:
            clauses.append("sample_direction=?")
            params.append(query.direction)
        if query.status is not None:
            clauses.append("status=?")
            params.append(query.status)
        if query.before_timestamp is not None:
            clauses.append("(occurred_at<? OR (occurred_at=? AND activity_id<?))")
            params.extend((query.before_timestamp,query.before_timestamp,query.before_id))
        where=" AND ".join(clauses)
        sql=("SELECT activity_id,sample_direction,amount_poisha,status,description,occurred_at "
             "FROM lab_activity WHERE "+where+" ORDER BY occurred_at DESC,activity_id DESC LIMIT ?")
        params.append(query.page_size+1)
        with self.store.read() as db:
            rows=db.execute(sql,tuple(params)).fetchall()
        has_next=len(rows)>query.page_size
        selected=rows[:query.page_size]
        records=tuple({"id":x["activity_id"],"direction":x["sample_direction"],
                       "poisha":x["amount_poisha"],"status":x["status"],
                       "description":x["description"],"at":x["occurred_at"],
                       "simulation":True,"settlement_proof":False} for x in selected)
        next_cursor=(selected[-1]["occurred_at"],selected[-1]["activity_id"]) if has_next and selected else None
        return ActivityPage(records,next_cursor,len(rows))

    def last_seen(self,context:SessionContext)->int|None:
        AccessPolicy.require(context,"statement:read",resource_owner=context.actor_id)
        with self.store.read() as db:
            last=db.execute("SELECT MAX(occurred_at) FROM lab_activity WHERE actor_id=?",(context.actor_id,)).fetchone()[0]
        return int(last) if last is not None else None

    def summary(self,context:SessionContext)->dict[str,object]:
        AccessPolicy.require(context,"statement:read",resource_owner=context.actor_id)
        with self.store.read() as db:
            rows=db.execute("SELECT sample_direction,status,COUNT(*) AS n,COALESCE(SUM(amount_poisha),0) AS amount FROM lab_activity WHERE actor_id=? GROUP BY sample_direction,status",
                            (context.actor_id,)).fetchall()
        return {"buckets":[{"direction":r["sample_direction"],"status":r["status"],
                            "count":r["n"],"sample_poisha":r["amount"]} for r in rows],
                "live_activity":False,"simulation":True}
