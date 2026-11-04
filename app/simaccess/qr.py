"""Signed, non-transferable sample QR references with durable anti-replay.

The URI scheme is intentionally unlike bKash, Nagad, NPSB or any other actual
payment network. Scanning only reveals a sandbox preview, never payment consent.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
import secrets
from urllib.parse import quote,unquote,urlparse
from .audit import AccessAudit
from .crypto import KeyRing,new_reference
from .errors import LabError,require
from .identifiers import synthetic_id,canonical,device_ref
from .policy import AccessPolicy
from .rate_limits import RateLimiter,ReplayGuard
from .sessions import SessionContext
from .store import LabStore

QR_SCHEME="slickkpaylab"
QR_HOST="request"
MAX_QR_BYTES=3000


@dataclass(frozen=True)
class QrPreview:
    issuer_id:str
    recipient_id:str
    operation:str
    amount_poisha:int
    expires_at:int
    nonce:str
    simulation:bool=True
    payment_authorized:bool=False

    def public(self)->dict[str,object]:
        return {"issuer":self.issuer_id,"recipient":self.recipient_id,
                "operation":self.operation,"amount_poisha":self.amount_poisha,
                "expires_at":self.expires_at,"simulation":True,"payment_authorized":False}


class SampleQrService:
    def __init__(self,store:LabStore,keyring:KeyRing):
        self.store=store
        self.keyring=keyring
        self.audit=AccessAudit(store)
        self.limits=RateLimiter(store)
        self.replay=ReplayGuard(store)

    def issue(self,context:SessionContext,*,recipient_id:str,operation:str,
              amount_poisha:int,lifetime:int=120)->str:
        AccessPolicy.require(context,"qr:issue",resource_owner=context.actor_id)
        from .identifiers import minor_units
        synthetic_id(recipient_id)
        minor_units(amount_poisha)
        require(operation in ("transfer","merchant_payment") and type(lifetime) is int and 30<=lifetime<=300,"INVALID_INPUT")
        now=self.store.clock.now()
        nonce=secrets.token_urlsafe(20)
        payload={"v":1,"sandbox":True,"issuer":context.actor_id,"recipient":recipient_id,
                 "operation":operation,"poisha":amount_poisha,"issued":now,"exp":now+lifetime,"nonce":nonce}
        with self.store.transaction() as db:
            self.limits.consume_in_transaction(db,context.actor_id,"qr")
            other=db.execute("SELECT role,state FROM lab_actors WHERE actor_id=?",(recipient_id,)).fetchone()
            role="merchant" if operation=="merchant_payment" else "customer"
            if other is None or other["role"]!=role or other["state"]!="active":
                raise LabError("NOT_FOUND")
            self.audit.append_in_transaction(db,actor=context.actor_id,kind="qr_issued",
                                             data={"recipient":recipient_id,"operation":operation},event_id=new_reference("audit"))
        envelope=self.keyring.sign_message(payload,now)
        # URL-safe fields and standard URI parser; never expose real merchant data.
        encoded=".".join((envelope["kid"],envelope["payload"],envelope["sig"]))
        uri=f"{QR_SCHEME}://{QR_HOST}/{encoded}"
        require(len(uri)<=MAX_QR_BYTES,"INVALID_INPUT")
        return uri

    def _unpack(self,uri:str)->QrPreview:
        require(isinstance(uri,str) and len(uri)<=MAX_QR_BYTES,"INVALID_INPUT")
        parsed=urlparse(uri)
        if parsed.scheme!=QR_SCHEME or parsed.netloc!=QR_HOST or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise LabError("INVALID_INPUT")
        parts=parsed.path.removeprefix("/").split(".")
        if len(parts)!=3 or not all(parts):
            raise LabError("INVALID_INPUT")
        envelope={"kid":parts[0],"payload":parts[1],"sig":parts[2]}
        result=self.keyring.verify_message(envelope,self.store.clock.now())
        if set(result)!={"v","sandbox","issuer","recipient","operation","poisha","issued","exp","nonce"}:
            raise LabError("INVALID_INPUT")
        if result["v"]!=1 or result["sandbox"] is not True:
            raise LabError("INVALID_INPUT")
        issuer=synthetic_id(result["issuer"])
        recipient=synthetic_id(result["recipient"])
        from .identifiers import minor_units
        minor_units(result["poisha"])
        if result["operation"] not in ("transfer","merchant_payment"):
            raise LabError("INVALID_INPUT")
        issued=result["issued"]
        expires=result["exp"]
        now=self.store.clock.now()
        if type(issued) is not int or type(expires) is not int or not 30<=expires-issued<=300 or now<issued-15 or now>=expires:
            raise LabError("QUOTE_EXPIRED")
        nonce=result["nonce"]
        require(isinstance(nonce,str) and 20<=len(nonce)<=100,"INVALID_INPUT")
        return QrPreview(issuer,recipient,result["operation"],result["poisha"],expires,nonce)

    def inspect(self,context:SessionContext,uri:str)->QrPreview:
        AccessPolicy.require(context,"qr:consume",resource_owner=context.actor_id)
        # Inspection is non-mutating and does not claim consent.
        return self._unpack(uri)

    def consume_preview(self,context:SessionContext,uri:str)->QrPreview:
        AccessPolicy.require(context,"qr:consume",resource_owner=context.actor_id)
        preview=self._unpack(uri)
        with self.store.transaction() as db:
            self.limits.consume_in_transaction(db,context.actor_id,"qr")
            self.replay.claim_in_transaction(db,actor_id=context.actor_id,purpose="qr",nonce=preview.nonce,
                                              expires_at=preview.expires_at,now=self.store.clock.now())
            self.audit.append_in_transaction(db,actor=context.actor_id,kind="qr_consumed",
                                             data={"issuer":preview.issuer_id,"recipient":preview.recipient_id},
                                             event_id=new_reference("audit"))
        return preview
