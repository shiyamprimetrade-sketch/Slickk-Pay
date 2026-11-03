"""Slickk Pay original *internal* merchant gateway prototype for fictional funds.

Not an external card/MFS gateway and not a way to bypass licensed payment rails.
Intents, capture, refund, audit events and balanced wallet postings are written
transactionally in the same local database. Only synthetic parties can interact.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
import sqlite3
from typing import Mapping

from .identity import SyntheticRegistry, IdentityError
from .ledger import SandboxLedger, Posting, LedgerError, InsufficientFunds
from .pricing import PilotPricing, initial_pilot


class GatewayError(ValueError):
    pass


class GatewayAuthError(GatewayError):
    pass


class GatewayStateError(GatewayError):
    pass


@dataclass(frozen=True)
class MerchantIntent:
    intent_id: str
    merchant_id: str
    customer_id: str
    invoice_ref: str
    principal_poisha: int
    processing_fee_poisha: int
    status: str
    created_at: str
    expires_at: str
    capture_event_id: str | None = None
    refund_event_id: str | None = None
    simulation: bool = True


@dataclass(frozen=True)
class NewIntent:
    intent: MerchantIntent
    customer_approval_token: str
    qr_payload: str
    warning: str = "Fictional payment request only; not a real payment QR"


SCHEMA = """
CREATE TABLE IF NOT EXISTS sim_merchants(
 merchant_id TEXT PRIMARY KEY,
 key_salt TEXT NOT NULL,
 key_digest TEXT NOT NULL,
 active INTEGER NOT NULL CHECK(active IN (0,1)),
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sim_gateway_intents(
 intent_id TEXT PRIMARY KEY, merchant_id TEXT NOT NULL REFERENCES sim_merchants(merchant_id),
 customer_id TEXT NOT NULL, invoice_ref TEXT NOT NULL,
 principal_poisha INTEGER NOT NULL CHECK(principal_poisha>0),
 processing_fee_poisha INTEGER NOT NULL CHECK(processing_fee_poisha>=0),
 customer_token_digest TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('created','captured','cancelled','refunded','expired')),
 created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
 capture_event_id TEXT, refund_event_id TEXT,
 UNIQUE(merchant_id,invoice_ref)
);
CREATE TABLE IF NOT EXISTS sim_gateway_events(
 event_id INTEGER PRIMARY KEY AUTOINCREMENT,
 intent_id TEXT NOT NULL REFERENCES sim_gateway_intents(intent_id),
 previous_status TEXT, next_status TEXT NOT NULL,
 actor_id TEXT NOT NULL, reason TEXT NOT NULL, occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sim_gateway_merchant_status ON sim_gateway_intents(merchant_id,status);
CREATE TRIGGER IF NOT EXISTS sim_gateway_events_update_block BEFORE UPDATE ON sim_gateway_events
 BEGIN SELECT RAISE(ABORT,'gateway audit immutable'); END;
CREATE TRIGGER IF NOT EXISTS sim_gateway_events_delete_block BEFORE DELETE ON sim_gateway_events
 BEGIN SELECT RAISE(ABORT,'gateway audit immutable'); END;
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(moment: datetime) -> str:
    return moment.isoformat(timespec="microseconds")


def _credential_digest(key: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256",key.encode(),bytes.fromhex(salt),400_000).hex()


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _intent_from_row(row: sqlite3.Row) -> MerchantIntent:
    return MerchantIntent(row["intent_id"],row["merchant_id"],row["customer_id"],
                          row["invoice_ref"],row["principal_poisha"],row["processing_fee_poisha"],
                          row["status"],row["created_at"],row["expires_at"],
                          row["capture_event_id"],row["refund_event_id"])


class InternalMerchantGateway:
    """Fictional local gateway with explicit customer authorization and no third-party calls."""

    def __init__(self, ledger: SandboxLedger, registry: SyntheticRegistry,
                 pricing: PilotPricing | None = None):
        self.ledger=ledger
        self.registry=registry
        self.pricing=pricing or initial_pilot()
        with ledger._lock,ledger._connect() as db:
            db.executescript(SCHEMA)

    def _party(self, party_id: str,role: str):
        party=self.registry.lookup(party_id,required_role=role)
        if party.status!="sandbox_verified":
            raise GatewayAuthError("Only approved synthetic parties can transact")
        return party

    def register_merchant(self,merchant_id: str,api_key: str)->None:
        self._party(merchant_id,"merchant")
        if not isinstance(api_key,str) or len(api_key)<32:
            raise GatewayAuthError("Require a unique locally generated sandbox merchant key")
        salt=secrets.token_hex(16)
        digest=_credential_digest(api_key,salt)
        with self.ledger._lock,self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                existing=db.execute("SELECT merchant_id FROM sim_merchants WHERE merchant_id=?",
                                    (merchant_id,)).fetchone()
                if existing:
                    raise GatewayError("Merchant already enrolled in sandbox")
                db.execute("INSERT INTO sim_merchants VALUES (?,?,?,?,?)",
                           (merchant_id,salt,digest,1,_stamp(_now())))
                db.commit()
            except Exception:
                db.rollback()
                raise

    def authenticate_merchant(self, merchant_id: str, key: str) -> None:
        if not isinstance(key,str) or len(key)>1024:
            raise GatewayAuthError("Missing merchant sandbox credentials")
        with self.ledger._connect() as db:
            merchant=db.execute("SELECT * FROM sim_merchants WHERE merchant_id=?",(merchant_id,)).fetchone()
        if not merchant or not merchant["active"]:
            raise GatewayAuthError("Unknown or disabled merchant")
        digest=_credential_digest(key,merchant["key_salt"])
        if not hmac.compare_digest(digest,merchant["key_digest"]):
            raise GatewayAuthError("Invalid sandbox merchant credentials")

    def disable_merchant(self,merchant_id: str,*,merchant_key: str)->None:
        self.authenticate_merchant(merchant_id,merchant_key)
        with self.ledger._lock,self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE sim_merchants SET active=0 WHERE merchant_id=?",(merchant_id,))
            db.commit()

    def _append(self,db:sqlite3.Connection,intent_id:str,old:str|None,new:str,
                actor_id:str,reason:str)->None:
        db.execute("INSERT INTO sim_gateway_events(intent_id,previous_status,next_status,actor_id,reason,occurred_at) "
                   "VALUES(?,?,?,?,?,?)",(intent_id,old,new,actor_id,reason,_stamp(_now())))

    def create_intent(self,*,merchant_id:str,merchant_key:str,customer_id:str,
                      invoice_ref:str,principal_poisha:int,expires_seconds:int=600)->NewIntent:
        self.authenticate_merchant(merchant_id,merchant_key)
        self._party(customer_id,"customer")
        if not isinstance(invoice_ref,str) or not 4<=len(invoice_ref)<=80:
            raise GatewayError("Invoice reference must be bounded")
        if not isinstance(expires_seconds,int) or not 60<=expires_seconds<=1800:
            raise GatewayError("Unreasonable sandbox expiry")
        quote=self.pricing.quote("merchant_payment",principal_poisha)
        token=secrets.token_urlsafe(24)
        intent_id="sim_intent_"+secrets.token_hex(12)
        current=_now()
        expiry=current+timedelta(seconds=expires_seconds)
        with self.ledger._lock,self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                duplicate=db.execute("SELECT * FROM sim_gateway_intents WHERE merchant_id=? AND invoice_ref=?",
                                     (merchant_id,invoice_ref)).fetchone()
                if duplicate:
                    raise GatewayStateError("Invoice already has a payment intent")
                db.execute("INSERT INTO sim_gateway_intents VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                           (intent_id,merchant_id,customer_id,invoice_ref,principal_poisha,
                            quote.merchant_fee,_token_digest(token),"created",
                            _stamp(current),_stamp(expiry),None,None))
                self._append(db,intent_id,None,"created",merchant_id,"sandbox_payment_requested")
                db.commit()
            except Exception:
                db.rollback()
                raise
        row=self.get_intent(intent_id)
        # Non-payable URI scheme prevents a simulated QR from impersonating a real QR rail.
        qr="slickkpay-sandbox://intent/"+intent_id
        return NewIntent(row,token,qr)

    def get_intent(self,intent_id:str)->MerchantIntent:
        with self.ledger._connect() as db:
            row=db.execute("SELECT * FROM sim_gateway_intents WHERE intent_id=?",(intent_id,)).fetchone()
        if not row:
            raise GatewayError("Intent not found")
        return _intent_from_row(row)

    def capture(self,intent_id:str,*,customer_id:str,customer_approval_token:str)->MerchantIntent:
        """Simulated internal wallet payment; no card network or third-party funds."""
        self._party(customer_id,"customer")
        if not isinstance(customer_approval_token,str) or len(customer_approval_token)>256:
            raise GatewayAuthError("Invalid test confirmation token")
        with self.ledger._lock,self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row=db.execute("SELECT * FROM sim_gateway_intents WHERE intent_id=?",(intent_id,)).fetchone()
                if row is None:
                    raise GatewayError("Intent not found")
                if row["customer_id"]!=customer_id:
                    raise GatewayAuthError("Customer does not own this intent")
                if row["status"]!="created":
                    raise GatewayStateError("Only new intents may be captured")
                if _now()>datetime.fromisoformat(row["expires_at"]):
                    raise GatewayStateError("Intent expired")
                if not hmac.compare_digest(row["customer_token_digest"],
                                           _token_digest(customer_approval_token)):
                    raise GatewayAuthError("Customer consent was not presented")
                principal=row["principal_poisha"]
                fee=row["processing_fee_poisha"]
                net=principal-fee
                if net<=0:
                    raise GatewayError("Merchant fee must be smaller than principal")
                lines=[Posting("sim_wallet_"+customer_id[4:],"debit",principal),
                       Posting("sim_merchant_"+row["merchant_id"][4:],"credit",net)]
                if fee:
                    lines.append(Posting("sim_platform_revenue","credit",fee))
                receipt=self.ledger.post_in_transaction(
                    db,operation="sandbox_merchant_capture",idempotency_key=intent_id+":capture",
                    postings=lines)
                db.execute("UPDATE sim_gateway_intents SET status='captured',capture_event_id=? "
                           "WHERE intent_id=? AND status='created'",(receipt.event_id,intent_id))
                self._append(db,intent_id,"created","captured",customer_id,"synthetic_wallet_capture")
                db.commit()
            except Exception:
                db.rollback()
                raise
        return self.get_intent(intent_id)

    def cancel(self,intent_id:str,*,merchant_id:str,merchant_key:str)->MerchantIntent:
        self.authenticate_merchant(merchant_id,merchant_key)
        with self.ledger._lock,self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row=db.execute("SELECT * FROM sim_gateway_intents WHERE intent_id=?",(intent_id,)).fetchone()
                if not row or row["merchant_id"]!=merchant_id:
                    raise GatewayAuthError("Merchant cannot access intent")
                if row["status"]!="created":
                    raise GatewayStateError("Captured or terminal intent is immutable")
                db.execute("UPDATE sim_gateway_intents SET status='cancelled' WHERE intent_id=?",(intent_id,))
                self._append(db,intent_id,"created","cancelled",merchant_id,"merchant_cancelled")
                db.commit()
            except Exception:
                db.rollback()
                raise
        return self.get_intent(intent_id)

    def refund_full(self,intent_id:str,*,merchant_id:str,merchant_key:str,
                    reason:str)->MerchantIntent:
        """Full atomic sandbox refund; fee reversal included, no external provider refund."""
        self.authenticate_merchant(merchant_id,merchant_key)
        if not isinstance(reason,str) or not 4<=len(reason)<=100:
            raise GatewayError("Require reviewable refund reason")
        with self.ledger._lock,self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row=db.execute("SELECT * FROM sim_gateway_intents WHERE intent_id=?",(intent_id,)).fetchone()
                if not row or row["merchant_id"]!=merchant_id:
                    raise GatewayAuthError("Merchant cannot access intent")
                if row["status"]!="captured":
                    raise GatewayStateError("Only captured payment may be refunded")
                principal=row["principal_poisha"]
                fee=row["processing_fee_poisha"]
                lines=[Posting("sim_merchant_"+merchant_id[4:],"debit",principal-fee),
                       Posting("sim_wallet_"+row["customer_id"][4:],"credit",principal)]
                if fee:
                    lines.append(Posting("sim_platform_revenue","debit",fee))
                receipt=self.ledger.post_in_transaction(
                    db,operation="sandbox_full_refund",idempotency_key=intent_id+":refund",
                    postings=lines)
                db.execute("UPDATE sim_gateway_intents SET status='refunded',refund_event_id=? "
                           "WHERE intent_id=?",(receipt.event_id,intent_id))
                self._append(db,intent_id,"captured","refunded",merchant_id,reason)
                db.commit()
            except Exception:
                db.rollback()
                raise
        return self.get_intent(intent_id)

    def event_history(self,intent_id:str)->tuple[dict,...]:
        self.get_intent(intent_id)
        with self.ledger._connect() as db:
            return tuple(dict(row) for row in db.execute(
                "SELECT previous_status,next_status,actor_id,reason,occurred_at FROM sim_gateway_events "
                "WHERE intent_id=? ORDER BY event_id",(intent_id,)).fetchall())

    def merchant_summary(self,merchant_id:str,*,merchant_key:str)->dict:
        self.authenticate_merchant(merchant_id,merchant_key)
        with self.ledger._connect() as db:
            stats=db.execute("SELECT status,COUNT(*) AS n,COALESCE(SUM(principal_poisha),0) AS principal "
                             "FROM sim_gateway_intents WHERE merchant_id=? GROUP BY status",
                             (merchant_id,)).fetchall()
        return {"simulation":True,"merchant_id":merchant_id,
                "states":{r["status"]:{"count":r["n"],"principal_poisha":r["principal"]}
                          for r in stats},"bank_settlement_confirmed":False}
