"""SQLite-backed fixed-window throttles and replay suppression for the lab."""
from __future__ import annotations
from dataclasses import dataclass
import sqlite3
from .errors import LabError, require
from .identifiers import digest, synthetic_id, safe_note
from .store import LabStore


@dataclass(frozen=True)
class Limit:
    action: str
    window_seconds: int
    requests_per_window: int

    def __post_init__(self) -> None:
        require(2<=len(self.action)<=40 and self.action.replace("_","").isalnum(),"INVALID_INPUT")
        require(type(self.window_seconds) is int and 10<=self.window_seconds<=86400,"INVALID_INPUT")
        require(type(self.requests_per_window) is int and 1<=self.requests_per_window<=10000,"INVALID_INPUT")


DEFAULT_LIMITS = {
    "login": Limit("login",60,10),
    "read": Limit("read",60,150),
    "quote": Limit("quote",60,15),
    "review": Limit("review",60,12),
    "qr": Limit("qr",60,15),
    "support": Limit("support",3600,10),
    "checklist": Limit("checklist",60,25),
}


class RateLimiter:
    def __init__(self,store:LabStore,limits:dict[str,Limit]|None=None):
        self.store=store
        self.limits=limits or DEFAULT_LIMITS

    def consume_in_transaction(self,db:sqlite3.Connection,actor_id:str,action:str,now:int|None=None)->int:
        synthetic_id(actor_id)
        if action not in self.limits:
            raise LabError("INVALID_INPUT")
        limit=self.limits[action]
        moment=now if now is not None else self.store.clock.now()
        window=moment//limit.window_seconds
        row=db.execute("SELECT counter FROM lab_rate_limits WHERE actor_id=? AND action=? AND bucket=?",
                       (actor_id,action,window)).fetchone()
        count=(int(row["counter"]) if row else 0)+1
        if count>limit.requests_per_window:
            raise LabError("RATE_LIMIT")
        if row:
            db.execute("UPDATE lab_rate_limits SET counter=? WHERE actor_id=? AND action=? AND bucket=?",
                       (count,actor_id,action,window))
        else:
            db.execute("INSERT INTO lab_rate_limits(actor_id,action,bucket,counter) VALUES(?,?,?,?)",
                       (actor_id,action,window,count))
        return limit.requests_per_window-count

    def consume(self,actor_id:str,action:str)->int:
        with self.store.transaction() as db:
            return self.consume_in_transaction(db,actor_id,action)

    def remaining(self,actor_id:str,action:str)->int:
        synthetic_id(actor_id)
        require(action in self.limits,"INVALID_INPUT")
        limit=self.limits[action]
        window=self.store.clock.now()//limit.window_seconds
        with self.store.read() as db:
            row=db.execute("SELECT counter FROM lab_rate_limits WHERE actor_id=? AND action=? AND bucket=?",
                           (actor_id,action,window)).fetchone()
        return max(0,limit.requests_per_window-(int(row["counter"]) if row else 0))

    def cleanup_old(self,action:str,*,keep_windows:int=3)->int:
        require(action in self.limits and 1<=keep_windows<=100,"INVALID_INPUT")
        limit=self.limits[action]
        oldest=self.store.clock.now()//limit.window_seconds-keep_windows
        with self.store.transaction() as db:
            return db.execute("DELETE FROM lab_rate_limits WHERE action=? AND bucket<?",(action,oldest)).rowcount


class ReplayGuard:
    def __init__(self,store:LabStore):
        self.store=store

    @staticmethod
    def claim_in_transaction(db:sqlite3.Connection,*,actor_id:str,purpose:str,
                             nonce:str,expires_at:int,now:int)->bool:
        synthetic_id(actor_id)
        require(purpose in ("qr", "quote_review", "cash_checklist", "support"),"INVALID_INPUT")
        require(isinstance(nonce,str) and 12<=len(nonce)<=256,"INVALID_INPUT")
        require(type(expires_at) is int and now<expires_at<=now+86400,"INVALID_INPUT")
        value=digest(nonce)
        existing=db.execute("SELECT nonce_digest FROM lab_replay WHERE purpose=? AND nonce_digest=?",
                            (purpose,value)).fetchone()
        if existing:
            raise LabError("REPLAY_BLOCKED")
        db.execute("INSERT INTO lab_replay(purpose,nonce_digest,actor_id,expires_at,accepted_at) VALUES(?,?,?,?,?)",
                   (purpose,value,actor_id,expires_at,now))
        return True

    def claim(self,*,actor_id:str,purpose:str,nonce:str,expires_at:int)->bool:
        with self.store.transaction() as db:
            return self.claim_in_transaction(db,actor_id=actor_id,purpose=purpose,nonce=nonce,
                                             expires_at=expires_at,now=self.store.clock.now())

    def prune(self,*,before:int|None=None)->int:
        threshold=before if before is not None else self.store.clock.now()
        with self.store.transaction() as db:
            return db.execute("DELETE FROM lab_replay WHERE expires_at<?",(threshold,)).rowcount
