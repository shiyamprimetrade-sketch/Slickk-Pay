"""Sandbox account-security and local-device session experiments.

Uses memory-hard scrypt, hash-only device identifiers, short sessions, attempt
limits, and explicit capability scopes. Real financial authentication requires
external security review, independent identity verification, MFA and hardened
key storage. This module performs no real account enrollment.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
import hashlib
import hmac
import secrets
import sqlite3
from typing import Iterable

from .identity import SyntheticRegistry
from .ledger import SandboxLedger


class SecurityError(ValueError):
    pass


class AuthenticationFailed(SecurityError):
    pass


class AccountLocked(SecurityError):
    pass


@dataclass(frozen=True)
class AuthSession:
    session_ref: str
    subject_id: str
    scopes: frozenset[str]
    device_digest: str
    expires_at: str
    synthetic: bool=True


@dataclass(frozen=True)
class SessionIssue:
    session: AuthSession
    bearer_token: str
    warning: str="Local fictitious sandbox only; not production MFA"


SCOPES=frozenset({"view_account","transfer","cash_request","merchant_invoice","dispute_view"})


SCHEMA="""
CREATE TABLE IF NOT EXISTS sim_auth_credentials(
 subject_id TEXT PRIMARY KEY,
 secret_salt TEXT NOT NULL,
 secret_digest TEXT NOT NULL,
 failures INTEGER NOT NULL DEFAULT 0 CHECK(failures>=0),
 locked_until TEXT,
 created_at TEXT NOT NULL,
 changed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sim_auth_devices(
 subject_id TEXT NOT NULL, device_digest TEXT NOT NULL,
 approved INTEGER NOT NULL DEFAULT 0 CHECK(approved IN (0,1)),
 last_seen_at TEXT, PRIMARY KEY(subject_id,device_digest)
);
CREATE TABLE IF NOT EXISTS sim_auth_sessions(
 session_ref TEXT PRIMARY KEY,
 subject_id TEXT NOT NULL,
 token_digest TEXT NOT NULL UNIQUE,
 device_digest TEXT NOT NULL,
 scopes_json TEXT NOT NULL,
 created_at TEXT NOT NULL,
 expires_at TEXT NOT NULL,
 revoked INTEGER NOT NULL DEFAULT 0 CHECK(revoked IN (0,1))
);
CREATE INDEX IF NOT EXISTS sim_auth_sessions_subject ON sim_auth_sessions(subject_id,expires_at);
CREATE TABLE IF NOT EXISTS sim_auth_audit(
 audit_id INTEGER PRIMARY KEY AUTOINCREMENT, subject_id TEXT NOT NULL,
 event TEXT NOT NULL, reason_code TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS sim_auth_audit_immutable_update BEFORE UPDATE ON sim_auth_audit
 BEGIN SELECT RAISE(ABORT,'authentication audit immutable'); END;
CREATE TRIGGER IF NOT EXISTS sim_auth_audit_immutable_delete BEFORE DELETE ON sim_auth_audit
 BEGIN SELECT RAISE(ABORT,'authentication audit immutable'); END;
"""


def _utc()->datetime:
    return datetime.now(timezone.utc)


def _iso(value:datetime)->str:
    return value.isoformat(timespec="microseconds")


def _digest(value:str)->str:
    return hashlib.sha256(value.encode()).hexdigest()


def _pass_hash(passphrase:str,salt:str)->str:
    # Moderate settings for low-resource sandbox; production parameters need review.
    return hashlib.scrypt(passphrase.encode(),salt=bytes.fromhex(salt),n=2**14,r=8,p=1,dklen=32).hex()


def _scopes_json(scopes:frozenset[str])->str:
    import json
    return json.dumps(sorted(scopes),separators=(",", ":"))


class LocalAuth:
    def __init__(self,ledger:SandboxLedger,registry:SyntheticRegistry,
                 *,max_failures:int=5,lock_minutes:int=15):
        self.ledger=ledger
        self.registry=registry
        if not 2<=max_failures<=20 or not 1<=lock_minutes<=240:
            raise SecurityError("Invalid sandbox lock policy")
        self.max_failures=max_failures
        self.lock_minutes=lock_minutes
        with ledger._lock,ledger._connect() as db:
            db.executescript(SCHEMA)

    def _synthetic(self,subject_id:str)->None:
        party=self.registry.lookup(subject_id)
        if party.status!="sandbox_verified":
            raise AuthenticationFailed("Synthetic account not eligible")

    def _audit(self,db:sqlite3.Connection,subject_id:str,event:str,reason:str)->None:
        db.execute("INSERT INTO sim_auth_audit(subject_id,event,reason_code,created_at) VALUES(?,?,?,?)",
                   (subject_id,event,reason,_iso(_utc())))

    def provision(self,subject_id:str,secret:str,*,device_label:str)->None:
        self._synthetic(subject_id)
        if not isinstance(secret,str) or len(secret)<12 or len(secret)>128:
            raise SecurityError("Require a 12–128 character local test passphrase")
        if not isinstance(device_label,str) or len(device_label)<6:
            raise SecurityError("Invalid synthetic device label")
        salt=secrets.token_hex(16)
        digest=_pass_hash(secret,salt)
        with self.ledger._lock,self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                if db.execute("SELECT 1 FROM sim_auth_credentials WHERE subject_id=?",
                              (subject_id,)).fetchone():
                    raise SecurityError("Credentials already provisioned")
                now=_iso(_utc())
                db.execute("INSERT INTO sim_auth_credentials VALUES(?,?,?,?,?,?,?)",
                           (subject_id,salt,digest,0,None,now,now))
                db.execute("INSERT INTO sim_auth_devices VALUES(?,?,?,?)",
                           (subject_id,_digest(device_label),1,now))
                self._audit(db,subject_id,"provisioned","fictional_test_identity")
                db.commit()
            except Exception:
                db.rollback()
                raise

    def authenticate(self,subject_id:str,secret:str,*,device_label:str,
                     scopes:Iterable[str],ttl_seconds:int=600)->SessionIssue:
        self._synthetic(subject_id)
        if not isinstance(secret,str) or len(secret)>256 or not isinstance(device_label,str):
            raise AuthenticationFailed("Invalid sandbox credentials")
        scope_set=frozenset(scopes)
        if not scope_set or not scope_set.issubset(SCOPES) or not 60<=ttl_seconds<=3600:
            raise SecurityError("Invalid session scope/expiry")
        device_digest=_digest(device_label)
        with self.ledger._lock,self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                credentials=db.execute("SELECT * FROM sim_auth_credentials WHERE subject_id=?",
                                       (subject_id,)).fetchone()
                if not credentials:
                    raise AuthenticationFailed("Sandbox credential missing")
                locked_until=credentials["locked_until"]
                if locked_until and _utc()<datetime.fromisoformat(locked_until):
                    raise AccountLocked("Account temporarily blocked after failures")
                expected=_pass_hash(secret,credentials["secret_salt"])
                device=db.execute("SELECT approved FROM sim_auth_devices WHERE subject_id=? AND device_digest=?",
                                  (subject_id,device_digest)).fetchone()
                if not hmac.compare_digest(expected,credentials["secret_digest"]) or not device or not device[0]:
                    failures=credentials["failures"]+1
                    block=_iso(_utc()+timedelta(minutes=self.lock_minutes)) if failures>=self.max_failures else None
                    db.execute("UPDATE sim_auth_credentials SET failures=?,locked_until=? WHERE subject_id=?",
                               (failures,block,subject_id))
                    self._audit(db,subject_id,"authentication_failed","secret_or_device_mismatch")
                    db.commit()
                    raise AuthenticationFailed("Sandbox authentication failed")
                db.execute("UPDATE sim_auth_credentials SET failures=0,locked_until=NULL WHERE subject_id=?",
                           (subject_id,))
                now=_utc()
                expiry=_iso(now+timedelta(seconds=ttl_seconds))
                token=secrets.token_urlsafe(32)
                ref="sim_session_"+secrets.token_hex(12)
                db.execute("INSERT INTO sim_auth_sessions VALUES(?,?,?,?,?,?,?,?)",
                           (ref,subject_id,_digest(token),device_digest,_scopes_json(scope_set),
                            _iso(now),expiry,0))
                db.execute("UPDATE sim_auth_devices SET last_seen_at=? WHERE subject_id=? AND device_digest=?",
                           (_iso(now),subject_id,device_digest))
                self._audit(db,subject_id,"session_issued","synthetic_passphrase")
                db.commit()
            except AuthenticationFailed:
                # Failed login commits its counters and audit before raising.
                raise
            except Exception:
                db.rollback()
                raise
        return SessionIssue(AuthSession(ref,subject_id,scope_set,device_digest,expiry),token)

    def authorize(self,bearer_token:str,*,device_label:str,scope:str)->AuthSession:
        if scope not in SCOPES or not isinstance(bearer_token,str) or len(bearer_token)>256:
            raise AuthenticationFailed("Invalid sandbox session request")
        if not isinstance(device_label,str):
            raise AuthenticationFailed("Invalid device")
        import json
        digest=_digest(bearer_token)
        with self.ledger._connect() as db:
            session=db.execute("SELECT * FROM sim_auth_sessions WHERE token_digest=?",(digest,)).fetchone()
        if (not session or session["revoked"] or
                not hmac.compare_digest(session["device_digest"],_digest(device_label)) or
                _utc()>=datetime.fromisoformat(session["expires_at"])):
            raise AuthenticationFailed("Session missing, expired, revoked or device-mismatched")
        scopes=frozenset(json.loads(session["scopes_json"]))
        if scope not in scopes:
            raise AuthenticationFailed("Sandbox capability not granted")
        self._synthetic(session["subject_id"])
        return AuthSession(session["session_ref"],session["subject_id"],scopes,
                           session["device_digest"],session["expires_at"])

    def revoke(self,session_ref:str,*,subject_id:str)->None:
        with self.ledger._lock,self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT subject_id FROM sim_auth_sessions WHERE session_ref=?",(session_ref,)).fetchone()
            if not row or row[0]!=subject_id:
                raise AuthenticationFailed("Cannot revoke another synthetic account session")
            db.execute("UPDATE sim_auth_sessions SET revoked=1 WHERE session_ref=?",(session_ref,))
            self._audit(db,subject_id,"session_revoked","owner_requested")
            db.commit()

    def revoke_all(self,subject_id:str)->int:
        with self.ledger._lock,self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            count=db.execute("UPDATE sim_auth_sessions SET revoked=1 WHERE subject_id=? AND revoked=0",
                             (subject_id,)).rowcount
            self._audit(db,subject_id,"all_sessions_revoked","owner_security_action")
            db.commit()
            return count

    def approve_device(self,subject_id:str,*,device_label:str,approved:bool=False)->None:
        if not isinstance(approved,bool):
            raise SecurityError("Invalid approval flag")
        with self.ledger._lock,self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO sim_auth_devices(subject_id,device_digest,approved,last_seen_at) "
                       "VALUES(?,?,?,?) ON CONFLICT(subject_id,device_digest) "
                       "DO UPDATE SET approved=excluded.approved",
                       (subject_id,_digest(device_label),int(approved),_iso(_utc())))
            if not approved:
                db.execute("UPDATE sim_auth_sessions SET revoked=1 WHERE subject_id=? AND device_digest=?",
                           (subject_id,_digest(device_label)))
            self._audit(db,subject_id,"device_policy_changed","sandbox_device_approved" if approved else "sandbox_device_blocked")
            db.commit()

    def rotate_secret(self,subject_id:str,*,old_secret:str,new_secret:str,
                      device_label:str)->None:
        if not isinstance(new_secret,str) or len(new_secret)<12 or len(new_secret)>128:
            raise SecurityError("Invalid replacement secret")
        # Existing device and secret must authenticate before rotation.
        proof=self.authenticate(subject_id,old_secret,device_label=device_label,
                                scopes={"view_account"},ttl_seconds=60)
        salt=secrets.token_hex(16)
        with self.ledger._lock,self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE sim_auth_credentials SET secret_salt=?,secret_digest=?,changed_at=? "
                       "WHERE subject_id=?",(salt,_pass_hash(new_secret,salt),_iso(_utc()),subject_id))
            db.execute("UPDATE sim_auth_sessions SET revoked=1 WHERE subject_id=?",(subject_id,))
            self._audit(db,subject_id,"secret_rotated","local_synthetic_proof")
            db.commit()

    def audit(self,subject_id:str)->tuple[dict,...]:
        with self.ledger._connect() as db:
            return tuple(dict(row) for row in db.execute(
                "SELECT event,reason_code,created_at FROM sim_auth_audit WHERE subject_id=? ORDER BY audit_id",
                (subject_id,)).fetchall())
