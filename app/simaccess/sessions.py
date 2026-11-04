"""Opaque, database-backed sandbox sessions with device binding and revocation.

Never put the operator inspection key on mobile; these sessions are scoped to
synthetic persona views, not access to the financial ledger or real money.
"""
from __future__ import annotations
from dataclasses import dataclass
import hmac
import sqlite3
from .audit import AccessAudit
from .clock import Clock
from .crypto import new_opaque_token, token_digest, new_reference
from .errors import LabError, require
from .identifiers import digest, device_ref, synthetic_id
from .identity import IdentityRegistry, Persona
from .store import LabStore
from .rate_limits import RateLimiter


@dataclass(frozen=True)
class SessionContext:
    actor_id: str
    role: str
    device_digest: str
    issued_at: int
    expires_at: int
    simulation: bool = True
    may_post_money: bool = False
    may_grant_credit: bool = False

    def public(self) -> dict[str, object]:
        return {"actor_id":self.actor_id,"role":self.role,"expires_at":self.expires_at,
                "simulation":True,"can_move_money":False,"can_issue_credit":False}


@dataclass(frozen=True)
class NewSession:
    bearer: str
    actor_id: str
    role: str
    expires_at: int
    simulation: bool = True


class SessionManager:
    def __init__(self, store: LabStore, *, max_seconds: int = 900,
                 idle_seconds: int = 300, max_parallel: int = 3):
        require(type(max_seconds) is int and 120 <= max_seconds <= 3600,"INVALID_INPUT")
        require(type(idle_seconds) is int and 30 <= idle_seconds <= max_seconds,"INVALID_INPUT")
        require(type(max_parallel) is int and 1 <= max_parallel <= 10,"INVALID_INPUT")
        self.store=store
        self.identity=IdentityRegistry(store)
        self.audit=AccessAudit(store)
        self.max_seconds=max_seconds
        self.idle_seconds=idle_seconds
        self.max_parallel=max_parallel
        self.login_limiter=RateLimiter(store)

    def login(self, *, actor_id: str, device_id: str, demo_pin: str) -> NewSession:
        # Persist the attempt before PIN validation so failed guesses count too.
        self.login_limiter.consume(actor_id,"login")
        actor=self.identity.verify_demo_pin(actor_id=actor_id,device_id=device_id,pin=demo_pin)
        token=new_opaque_token()
        hashed=token_digest(token)
        now=self.store.clock.now()
        with self.store.transaction() as db:
            self.identity.require_active(db,actor_id)
            device=self.identity.trusted_device_in_transaction(db,actor_id=actor_id,device_id=device_id)
            active=db.execute("SELECT token_digest FROM lab_sessions WHERE actor_id=? AND state='active' AND expires_at>? ORDER BY issued_at ASC",(actor_id,now)).fetchall()
            for row in active[:max(0,len(active)-self.max_parallel+1)]:
                db.execute("UPDATE lab_sessions SET state='revoked' WHERE token_digest=?",(row["token_digest"],))
            db.execute("INSERT INTO lab_sessions(token_digest,actor_id,device_digest,role,issued_at,expires_at,last_used_at,state) VALUES(?,?,?,?,?,?,?,'active')",
                       (hashed,actor_id,device.device_digest,actor.role,now,now+self.max_seconds,now))
            self.audit.append_in_transaction(db,actor=actor_id,kind="login_succeeded",
                                             data={"device":device.device_digest},event_id=new_reference("audit"))
        return NewSession(token,actor_id,actor.role,now+self.max_seconds)

    def _get_context(self, db: sqlite3.Connection, *, bearer: str,
                     device_id: str, touch: bool) -> SessionContext:
        hashed=token_digest(bearer)
        device_ref(device_id)
        now=self.store.clock.now()
        row=db.execute("SELECT * FROM lab_sessions WHERE token_digest=?",(hashed,)).fetchone()
        if row is None:
            raise LabError("UNAUTHORIZED")
        if row["state"] != "active":
            raise LabError("SESSION_REVOKED")
        if row["expires_at"] <= now or now - row["last_used_at"] > self.idle_seconds:
            if touch:
                db.execute("UPDATE lab_sessions SET state='expired' WHERE token_digest=?",(hashed,))
            raise LabError("SESSION_EXPIRED")
        if not hmac.compare_digest(row["device_digest"],digest(device_id)):
            raise LabError("DEVICE_MISMATCH")
        persona=self.identity.require_active(db,row["actor_id"])
        self.identity.trusted_device_in_transaction(db,actor_id=persona.id,device_id=device_id)
        if row["role"]!=persona.role:
            raise LabError("ROLE_FORBIDDEN")
        if touch:
            db.execute("UPDATE lab_sessions SET last_used_at=? WHERE token_digest=?",(now,hashed))
            db.execute("UPDATE lab_devices SET last_seen_at=? WHERE actor_id=? AND device_digest=?",
                       (now,persona.id,row["device_digest"]))
        return SessionContext(persona.id,persona.role,row["device_digest"],row["issued_at"],row["expires_at"])

    def require(self, *, bearer: str, device_id: str, role: str | None = None) -> SessionContext:
        with self.store.transaction() as db:
            result=self._get_context(db,bearer=bearer,device_id=device_id,touch=True)
            if role is not None and result.role!=role:
                raise LabError("ROLE_FORBIDDEN")
            return result

    def require_in_transaction(self, db: sqlite3.Connection, *, bearer: str,
                               device_id: str, role: str | None = None) -> SessionContext:
        result=self._get_context(db,bearer=bearer,device_id=device_id,touch=True)
        if role is not None and result.role!=role:
            raise LabError("ROLE_FORBIDDEN")
        return result

    def logout(self, *, bearer: str, device_id: str) -> bool:
        with self.store.transaction() as db:
            context=self._get_context(db,bearer=bearer,device_id=device_id,touch=False)
            modified=db.execute("UPDATE lab_sessions SET state='revoked' WHERE token_digest=? AND state='active'",
                                (token_digest(bearer),)).rowcount
            if modified:
                self.audit.append_in_transaction(db,actor=context.actor_id,kind="logout",
                                                 data={"session_ended":True},event_id=new_reference("audit"))
            return bool(modified)

    def revoke_all(self, actor_id: str) -> int:
        synthetic_id(actor_id)
        with self.store.transaction() as db:
            actor=self.identity.get_in_transaction(db,actor_id)
            result=db.execute("UPDATE lab_sessions SET state='revoked' WHERE actor_id=? AND state='active'",(actor_id,))
            if result.rowcount:
                self.audit.append_in_transaction(db,actor=actor_id,kind="logout",
                                                 data={"all_sessions":True,"role":actor.role},event_id=new_reference("audit"))
            return result.rowcount

    def active_session_count(self, actor_id: str) -> int:
        synthetic_id(actor_id)
        with self.store.read() as db:
            return int(db.execute("SELECT COUNT(*) FROM lab_sessions WHERE actor_id=? AND state='active' AND expires_at>?",
                                  (actor_id,self.store.clock.now())).fetchone()[0])

    def inspect_without_secret(self, *, bearer: str, device_id: str) -> dict[str, object]:
        context=self.require(bearer=bearer,device_id=device_id)
        return context.public()
