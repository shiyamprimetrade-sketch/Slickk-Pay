"""Synthetic signed authorizations with durable nonce replay suppression.

This laboratory keyring is NOT production MFA, device attestation, customer KYC,
OTP, or real transaction authorization. Use established HMAC-SHA256 primitives;
no novel cryptography or external identity provider is implemented.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import base64
import hmac
import json
import re
import secrets
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Connection
from .schema import auth_nonces
from .guard import sim_id
from .store import SandboxStore, utc_now
from .posting import canonical
from .errors import (InvalidValue, AuthorizationError, Conflict, StateError)


_ALLOWED_SCOPES = frozenset({"sim_inspect", "sim_customer_approve", "sim_agent_attest",
                             "sim_operator_review", "sim_receipt_view"})
_MAX_TOKEN_LENGTH = 4096


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(data: str) -> bytes:
    if not isinstance(data,str) or not re.fullmatch(r"[A-Za-z0-9_-]+",data):
        raise AuthorizationError("Malformed synthetic authorization")
    try:
        return base64.urlsafe_b64decode(data + "=" * (-len(data)%4))
    except Exception as exc:
        raise AuthorizationError("Invalid synthetic encoding") from exc


@dataclass(frozen=True)
class KeyVersion:
    key_id: str
    secret: bytes
    enabled: bool = True

    def __post_init__(self):
        if not re.fullmatch(r"sim_[A-Za-z0-9_-]{4,24}",self.key_id):
            raise InvalidValue("Invalid sandbox key identifier")
        if not isinstance(self.secret,bytes) or len(self.secret)<32:
            raise InvalidValue("Test key must be 256-bit or longer")


@dataclass(frozen=True)
class SyntheticGrant:
    actor_id: str
    scope: str
    key_id: str
    device_digest: str
    nonce_digest: str
    issued_at: str
    expires_at: str
    simulation: bool = True


class SyntheticTokenService:
    def __init__(self, store: SandboxStore, keyring: tuple[KeyVersion, ...],
                 primary_key_id: str):
        if not keyring:
            raise InvalidValue("Empty sandbox keyring")
        self.store=store
        self.keyring={key.key_id:key for key in keyring}
        if len(self.keyring)!=len(keyring) or primary_key_id not in self.keyring:
            raise InvalidValue("Duplicate or missing key identifiers")
        if not self.keyring[primary_key_id].enabled:
            raise InvalidValue("Primary key cannot be disabled")
        self.primary=primary_key_id

    def issue(self, *, actor_id: str, scope: str, device_id: str,
              lifetime_seconds: int = 120, now: datetime | None = None) -> str:
        sim_id(actor_id,"actor")
        sim_id(device_id,"fictional device")
        if scope not in _ALLOWED_SCOPES:
            raise InvalidValue("Unrecognized scope")
        if not 30 <= lifetime_seconds <= 600:
            raise InvalidValue("Invalid pilot lifetime")
        current=now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise InvalidValue("Naive token issue time")
        stamp=current.astimezone(timezone.utc)
        nonce=secrets.token_urlsafe(24)
        data={"v":1,"sandbox":True,"actor":actor_id,"scope":scope,
              "device":sha256(device_id.encode()).hexdigest(),"kid":self.primary,
              "nonce":nonce,"iat":int(stamp.timestamp()),
              "exp":int((stamp+timedelta(seconds=lifetime_seconds)).timestamp())}
        payload=_encode(canonical(data).encode())
        signature=_encode(hmac.digest(self.keyring[self.primary].secret,
                                      payload.encode(),"sha256"))
        return payload+"."+signature

    def validate_in_transaction(self, db: Connection, *, token: str, scope: str,
                                actor_id: str, device_id: str,
                                now: datetime | None = None) -> SyntheticGrant:
        sim_id(actor_id,"actor")
        sim_id(device_id,"device")
        if scope not in _ALLOWED_SCOPES:
            raise AuthorizationError("Unavailable permission")
        if not isinstance(token,str) or not 20 <= len(token) <= _MAX_TOKEN_LENGTH:
            raise AuthorizationError("Invalid authorization payload")
        if token.count(".")!=1:
            raise AuthorizationError("Invalid authorization envelope")
        payload,signature=token.split(".",1)
        try:
            data=json.loads(_decode(payload))
        except (ValueError,TypeError) as exc:
            raise AuthorizationError("Malformed synthetic grant") from exc
        if not isinstance(data,dict) or set(data) != {
            "v","sandbox","actor","scope","device","kid","nonce","iat","exp"}:
            raise AuthorizationError("Unknown or omitted grant fields")
        if data["v"]!=1 or data["sandbox"] is not True:
            raise AuthorizationError("Grant is not a sandbox token")
        key=self.keyring.get(data["kid"])
        if key is None or not key.enabled:
            raise AuthorizationError("Signing key was rotated or disabled")
        expected=_encode(hmac.digest(key.secret,payload.encode(),"sha256"))
        if not hmac.compare_digest(expected,signature):
            raise AuthorizationError("Invalid grant signature")
        if data["actor"]!=actor_id or data["scope"]!=scope:
            raise AuthorizationError("Synthetic permission mismatch")
        expected_device=sha256(device_id.encode()).hexdigest()
        if not hmac.compare_digest(data["device"],expected_device):
            raise AuthorizationError("Incorrect synthetic device binding")
        at=now or datetime.now(timezone.utc)
        if at.tzinfo is None:
            raise AuthorizationError("Invalid validation clock")
        timestamp=int(at.astimezone(timezone.utc).timestamp())
        if not isinstance(data["iat"],int) or isinstance(data["iat"],bool) or \
           not isinstance(data["exp"],int) or isinstance(data["exp"],bool):
            raise AuthorizationError("Invalid token timestamps")
        if data["iat"]>timestamp+30 or data["exp"]<=timestamp or \
           not 30 <= data["exp"]-data["iat"] <= 600:
            raise AuthorizationError("Grant outside validity window")
        nonce=data["nonce"]
        if not isinstance(nonce,str) or not 24<=len(nonce)<=128:
            raise AuthorizationError("Invalid replay reference")
        nonce_digest=sha256(nonce.encode()).hexdigest()
        existing=db.execute(select(auth_nonces.c.nonce_digest)
                            .where(auth_nonces.c.nonce_digest==nonce_digest)).first()
        if existing:
            raise AuthorizationError("Grant nonce already consumed")
        db.execute(insert(auth_nonces).values(nonce_digest=nonce_digest,
                   actor_id=actor_id,scope=scope,key_id=key.key_id,
                   expires_at=datetime.fromtimestamp(data["exp"],timezone.utc)
                       .isoformat(timespec="microseconds"),accepted_at=utc_now()))
        return SyntheticGrant(actor_id,scope,key.key_id,expected_device,nonce_digest,
                              datetime.fromtimestamp(data["iat"],timezone.utc).isoformat(),
                              datetime.fromtimestamp(data["exp"],timezone.utc).isoformat())

    def validate(self, *, token: str, scope: str, actor_id: str,
                 device_id: str) -> SyntheticGrant:
        with self.store.transaction() as db:
            return self.validate_in_transaction(db,token=token,scope=scope,
                                                 actor_id=actor_id,device_id=device_id)

    def disable_key(self, key_id: str) -> "SyntheticTokenService":
        if key_id==self.primary:
            raise AuthorizationError("Cannot disable primary key without rotating first")
        if key_id not in self.keyring:
            raise InvalidValue("Unknown sandbox key")
        revised=tuple(KeyVersion(k.key_id,k.secret,False if k.key_id==key_id else k.enabled)
                      for k in self.keyring.values())
        return SyntheticTokenService(self.store,revised,self.primary)

    def with_new_primary(self, replacement: KeyVersion) -> "SyntheticTokenService":
        if replacement.key_id in self.keyring:
            raise Conflict("Key identifier already used")
        return SyntheticTokenService(self.store,
                  tuple(self.keyring.values())+(replacement,),replacement.key_id)
