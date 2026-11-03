"""Privacy-preserving bilingual receipts for *fictional* internal ledger events.

Printable output is always labelled SIMULATION/সিমুলেশন and cannot be used as
proof that a bank, gateway or cash agent settled an actual payment. Source event
references are checked against the local immutable journal before rendering.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime,timezone
import hashlib
import hmac
import json
from typing import Literal

from .ledger import SandboxLedger,LedgerError,InvariantViolation
from .pricing import poisha_to_bdt


class ReceiptError(ValueError):
    pass


LABELS={
    "en": {
        "title":"SLICKK PAY — FICTIONAL TRANSACTION",
        "reference":"Reference","operation":"Operation","time":"UTC time",
        "amount":"Gross movement","status":"Simulation status",
        "warning":"No real money or bank settlement occurred.",
    },
    "bn": {
        "title":"স্লিক পে — কাল্পনিক লেনদেন",
        "reference":"রেফারেন্স","operation":"লেনদেনের ধরন","time":"ইউটিসি সময়",
        "amount":"মোট স্থানান্তর","status":"সিমুলেশনের অবস্থা",
        "warning":"কোনো প্রকৃত অর্থ বা ব্যাংক নিষ্পত্তি হয়নি।",
    },
}


@dataclass(frozen=True)
class FictionalReceipt:
    receipt_id:str
    event_id:str
    operation:str
    amount_poisha:int
    recorded_at:str
    journal_tip:str
    owner_account:str
    simulated:bool=True
    bank_settlement_confirmed:bool=False

    def to_public(self,language:Literal["en","bn"]="en")->dict:
        if language not in LABELS:
            raise ReceiptError("Unsupported receipt language")
        return {"label":LABELS[language]["title"],"receipt_id":self.receipt_id,
                "event_id":self.event_id,"operation":self.operation,
                "amount_bdt":poisha_to_bdt(self.amount_poisha),
                "recorded_at_utc":self.recorded_at,
                "simulated":True,"bank_settlement_confirmed":False,
                "warning":LABELS[language]["warning"]}


class ReceiptDesk:
    def __init__(self,ledger:SandboxLedger):
        self.ledger=ledger

    def create(self,event_id:str,*,owner_account:str)->FictionalReceipt:
        self.ledger.account(owner_account)
        with self.ledger._connect() as db:
            event=db.execute("SELECT * FROM sim_events WHERE event_id=?",(event_id,)).fetchone()
            if not event:
                raise ReceiptError("Unknown synthetic ledger event")
            lines=db.execute("SELECT direction,amount_poisha FROM sim_postings "
                             "WHERE event_id=? AND account_id=? ORDER BY line_index",
                             (event_id,owner_account)).fetchall()
        if not lines:
            raise ReceiptError("This account did not participate in the event")
        total=sum(row["amount_poisha"] for row in lines if row["direction"]=="debit")
        if not total:
            total=sum(row["amount_poisha"] for row in lines if row["direction"]=="credit")
        receipt_id="sim_receipt_"+hashlib.sha256((event_id+":"+owner_account).encode()).hexdigest()[:24]
        return FictionalReceipt(receipt_id,event_id,event["operation"],total,
                                event["created_at"],event["event_hash"],owner_account)

    def render_text(self,receipt:FictionalReceipt,*,language:str="en")->str:
        if language not in LABELS:
            raise ReceiptError("Unsupported receipt language")
        l=LABELS[language]
        return "\n".join((l["title"],
            f"{l['reference']}: {receipt.receipt_id}",
            f"{l['operation']}: {receipt.operation}",
            f"{l['amount']}: BDT {poisha_to_bdt(receipt.amount_poisha)}",
            f"{l['time']}: {receipt.recorded_at}",
            f"{l['status']}: SIMULATION",l["warning"]))

    def render_notification(self,receipt:FictionalReceipt,*,language:str="en")->str:
        if language not in LABELS:
            raise ReceiptError("Unsupported receipt language")
        if language=="bn":
            return f"সিমুলেশন: {poisha_to_bdt(receipt.amount_poisha)} টাকা; {receipt.receipt_id[-12:]}; প্রকৃত টাকা নয়।"
        return (f"Slickk Pay SIMULATION: BDT {poisha_to_bdt(receipt.amount_poisha)} "
                f"ref {receipt.receipt_id[-12:]}; no real funds moved.")

    def sign_local_copy(self,receipt:FictionalReceipt,*,test_secret:str)->dict:
        if not isinstance(test_secret,str) or len(test_secret)<32:
            raise ReceiptError("Require a separate 32+ character sandbox signing key")
        payload=receipt.to_public("en")
        payload["journal_event_digest"]=receipt.journal_tip
        data=json.dumps(payload,sort_keys=True,separators=(",", ":"))
        signature=hmac.new(test_secret.encode(),data.encode(),hashlib.sha256).hexdigest()
        return {"receipt":payload,"signature":signature,"algorithm":"HMAC-SHA256-SANDBOX"}

    def verify_local_copy(self,signed:dict,*,test_secret:str)->bool:
        try:
            if signed["algorithm"]!="HMAC-SHA256-SANDBOX" or len(test_secret)<32:
                return False
            payload=signed["receipt"]
            if payload.get("simulated") is not True or payload.get("bank_settlement_confirmed") is not False:
                return False
            canonical=json.dumps(payload,sort_keys=True,separators=(",", ":"))
            expected=hmac.new(test_secret.encode(),canonical.encode(),hashlib.sha256).hexdigest()
            return hmac.compare_digest(expected,signed["signature"])
        except (KeyError,TypeError,ValueError):
            return False

    def verify_against_journal(self,receipt:FictionalReceipt)->bool:
        try:
            original=self.create(receipt.event_id,owner_account=receipt.owner_account)
        except (LedgerError,ReceiptError):
            return False
        return hmac.compare_digest(original.receipt_id,receipt.receipt_id) and (
            original.journal_tip==receipt.journal_tip and
            original.amount_poisha==receipt.amount_poisha)
