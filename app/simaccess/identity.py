"""Synthetic persona enrollment, state and device lifecycle management.

No real phone numbers, NID data, KYC assertions, biometric captures or funds.
Only tests or an explicitly opted-in local fixture script may enroll personas.
"""
from __future__ import annotations
from dataclasses import dataclass
import sqlite3
from .audit import AccessAudit
from .crypto import derive_pin, check_pin, new_reference
from .errors import LabError, require
from .identifiers import synthetic_id, device_ref, sanitized_label, digest
from .store import LabStore

ROLES = frozenset({"customer", "agent", "merchant", "operator"})
ACTOR_STATES = frozenset({"active", "frozen", "closed"})


@dataclass(frozen=True)
class Persona:
    id: str
    role: str
    label: str
    state: str
    revision: int
    simulation: bool = True

    def public(self) -> dict[str, object]:
        return {"id": self.id, "role": self.role, "label": self.label,
                "state": self.state, "revision": self.revision, "simulation": True}


@dataclass(frozen=True)
class Device:
    actor_id: str
    device_digest: str
    label: str
    state: str
    enrolled_at: int
    last_seen_at: int
    simulation: bool = True


class IdentityRegistry:
    def __init__(self, store: LabStore):
        self.store = store
        self.audit = AccessAudit(store)

    @staticmethod
    def _row_to_persona(row: sqlite3.Row) -> Persona:
        return Persona(row["actor_id"], row["role"], row["label"],row["state"],row["revision"])

    def enroll_fixture(self, *, actor_id: str, role: str, label: str, demo_pin: str,
                       sample_balance_poisha: int = 0) -> Persona:
        synthetic_id(actor_id)
        require(role in ROLES, "INVALID_INPUT")
        clean = sanitized_label(label)
        from .identifiers import minor_units
        minor_units(sample_balance_poisha, zero_ok=True)
        salt, hash_value = derive_pin(demo_pin)
        now = self.store.clock.now()
        with self.store.transaction() as db:
            existing = db.execute("SELECT actor_id FROM lab_actors WHERE actor_id=?", (actor_id,)).fetchone()
            if existing is not None:
                raise LabError("CONFLICT")
            db.execute("INSERT INTO lab_actors(actor_id,role,label,salt,pin_hash,state,created_at) VALUES(?,?,?,?,?,'active',?)",
                       (actor_id,role,clean,salt,hash_value,now))
            if role != "operator":
                db.execute("INSERT INTO lab_snapshots(actor_id,sample_account_id,sample_balance_poisha,updated_at) VALUES(?,?,?,?)",
                           (actor_id,actor_id.replace("sim_", "sim_account_", 1),sample_balance_poisha,now))
            self.audit.append_in_transaction(db,actor=actor_id,kind="fixture_enrolled",
                                             data={"role":role,"state":"active"},event_id=new_reference("audit"))
        return Persona(actor_id, role, clean, "active", 1)

    def get(self, actor_id: str) -> Persona:
        synthetic_id(actor_id)
        with self.store.read() as db:
            row = db.execute("SELECT * FROM lab_actors WHERE actor_id=?", (actor_id,)).fetchone()
        if row is None:
            raise LabError("NOT_FOUND")
        return self._row_to_persona(row)

    def get_in_transaction(self, db: sqlite3.Connection, actor_id: str) -> Persona:
        row = db.execute("SELECT * FROM lab_actors WHERE actor_id=?", (actor_id,)).fetchone()
        if row is None:
            raise LabError("NOT_FOUND")
        return self._row_to_persona(row)

    def require_active(self, db: sqlite3.Connection, actor_id: str) -> Persona:
        user = self.get_in_transaction(db, actor_id)
        if user.state != "active":
            raise LabError("ROLE_FORBIDDEN")
        return user

    def change_state(self, actor_id: str, *, state: str) -> Persona:
        synthetic_id(actor_id)
        require(state in ACTOR_STATES, "INVALID_INPUT")
        with self.store.transaction() as db:
            actor = self.get_in_transaction(db, actor_id)
            if actor.state == "closed" or (actor.state == "frozen" and state == "active"):
                raise LabError("CONFLICT")
            if actor.state == state:
                return actor
            db.execute("UPDATE lab_actors SET state=?,revision=revision+1 WHERE actor_id=?", (state,actor_id))
            db.execute("UPDATE lab_sessions SET state='revoked' WHERE actor_id=? AND state='active'", (actor_id,))
            self.audit.append_in_transaction(db,actor=actor_id,kind="actor_state",
                                             data={"previous":actor.state,"next":state},event_id=new_reference("audit"))
            return Persona(actor_id,actor.role,actor.label,state,actor.revision+1)

    def enroll_device(self, *, actor_id: str, device_id: str, label: str) -> Device:
        synthetic_id(actor_id)
        device_ref(device_id)
        clean = sanitized_label(label)
        now = self.store.clock.now()
        hashed = digest(device_id)
        with self.store.transaction() as db:
            self.require_active(db,actor_id)
            existing = db.execute("SELECT state FROM lab_devices WHERE actor_id=? AND device_digest=?",
                                  (actor_id,hashed)).fetchone()
            if existing:
                raise LabError("CONFLICT")
            db.execute("INSERT INTO lab_devices(actor_id,device_digest,label,state,enrolled_at,last_seen_at) VALUES(?,?,?,'trusted',?,?)",
                       (actor_id,hashed,clean,now,now))
            self.audit.append_in_transaction(db,actor=actor_id,kind="device_registered",
                                            data={"device_digest":hashed},event_id=new_reference("audit"))
        return Device(actor_id,hashed,clean,"trusted",now,now)

    def trusted_device_in_transaction(self, db: sqlite3.Connection, *, actor_id: str,
                                      device_id: str) -> Device:
        synthetic_id(actor_id)
        device_ref(device_id)
        hashed = digest(device_id)
        row = db.execute("SELECT * FROM lab_devices WHERE actor_id=? AND device_digest=?",
                         (actor_id,hashed)).fetchone()
        if row is None or row["state"] != "trusted":
            raise LabError("DEVICE_MISMATCH")
        return Device(row["actor_id"],row["device_digest"],row["label"],row["state"],
                      row["enrolled_at"],row["last_seen_at"])

    def list_devices(self, actor_id: str) -> list[Device]:
        synthetic_id(actor_id)
        with self.store.read() as db:
            rows = db.execute("SELECT * FROM lab_devices WHERE actor_id=? ORDER BY enrolled_at DESC",
                              (actor_id,)).fetchall()
        return [Device(x["actor_id"],x["device_digest"],x["label"],x["state"],x["enrolled_at"],x["last_seen_at"]) for x in rows]

    def revoke_device(self, *, actor_id: str, device_id: str) -> bool:
        synthetic_id(actor_id)
        device_ref(device_id)
        hashed = digest(device_id)
        with self.store.transaction() as db:
            row = db.execute("SELECT state FROM lab_devices WHERE actor_id=? AND device_digest=?",
                             (actor_id,hashed)).fetchone()
            if row is None:
                raise LabError("NOT_FOUND")
            if row["state"] == "revoked":
                return False
            db.execute("UPDATE lab_devices SET state='revoked' WHERE actor_id=? AND device_digest=?",(actor_id,hashed))
            db.execute("UPDATE lab_sessions SET state='revoked' WHERE actor_id=? AND device_digest=?",(actor_id,hashed))
            self.audit.append_in_transaction(db,actor=actor_id,kind="device_revoked",
                                             data={"device_digest":hashed},event_id=new_reference("audit"))
            return True

    def verify_demo_pin(self, *, actor_id: str, pin: str, device_id: str) -> Persona:
        synthetic_id(actor_id)
        device_ref(device_id)
        with self.store.transaction() as db:
            actor = self.require_active(db,actor_id)
            self.trusted_device_in_transaction(db,actor_id=actor_id,device_id=device_id)
            row = db.execute("SELECT salt,pin_hash,locked_until,bad_attempts FROM lab_actors WHERE actor_id=?",
                             (actor_id,)).fetchone()
            now = self.store.clock.now()
            if row["locked_until"] > now:
                raise LabError("RATE_LIMIT")
            if not check_pin(pin,row["salt"],row["pin_hash"]):
                attempts = int(row["bad_attempts"]) + 1
                lock_until = now + 90 if attempts >= 5 else 0
                db.execute("UPDATE lab_actors SET bad_attempts=?,locked_until=? WHERE actor_id=?",
                           (0 if lock_until else attempts,lock_until,actor_id))
                self.audit.append_in_transaction(db,actor=actor_id,kind="login_failed",
                                                 data={"failed":True,"locked":bool(lock_until)},event_id=new_reference("audit"))
                return_failure = True
            else:
                db.execute("UPDATE lab_actors SET bad_attempts=0,locked_until=0 WHERE actor_id=?", (actor_id,))
                return_failure = False
        if return_failure:
            raise LabError("UNAUTHORIZED")
        return actor

    def add_sample_activity(self, actor_id: str, *, direction: str, amount_poisha: int,
                            description: str, status: str = "sample_pending") -> str:
        from .identifiers import minor_units, safe_note
        synthetic_id(actor_id)
        minor_units(amount_poisha)
        require(direction in ("in", "out") and status in ("sample_paid","sample_cancelled","sample_pending"),"INVALID_INPUT")
        clean = safe_note(description,max_length=120)
        activity_id = new_reference("receipt")
        now = self.store.clock.now()
        with self.store.transaction() as db:
            self.require_active(db,actor_id)
            db.execute("INSERT INTO lab_activity(activity_id,actor_id,sample_direction,amount_poisha,status,description,occurred_at) VALUES(?,?,?,?,?,?,?)",
                       (activity_id,actor_id,direction,amount_poisha,status,clean,now))
        return activity_id

    def sample_statement(self, actor_id: str, limit: int = 40) -> list[dict[str, object]]:
        synthetic_id(actor_id)
        require(type(limit) is int and 1 <= limit <= 100,"INVALID_INPUT")
        with self.store.read() as db:
            self.require_active(db,actor_id)
            rows = db.execute("SELECT activity_id,sample_direction,amount_poisha,status,description,occurred_at FROM lab_activity WHERE actor_id=? ORDER BY occurred_at DESC,activity_id DESC LIMIT ?",
                              (actor_id,limit)).fetchall()
        return [{"id":x["activity_id"],"direction":x["sample_direction"],
                 "amount_poisha":x["amount_poisha"],"status":x["status"],
                 "description":x["description"],"time":x["occurred_at"],
                 "simulation":True,"payment_proof":False} for x in rows]

    def sample_balances(self, actor_id: str) -> list[dict[str, object]]:
        synthetic_id(actor_id)
        with self.store.read() as db:
            self.require_active(db,actor_id)
            rows = db.execute("SELECT sample_account_id,sample_balance_poisha,updated_at FROM lab_snapshots WHERE actor_id=? ORDER BY sample_account_id",(actor_id,)).fetchall()
        return [{"account_id":x["sample_account_id"],"sample_balance_poisha":x["sample_balance_poisha"],
                 "currency":"BDT","as_of":x["updated_at"],"authoritative":False,
                 "simulation":True} for x in rows]
