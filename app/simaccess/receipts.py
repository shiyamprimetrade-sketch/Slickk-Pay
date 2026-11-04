"""Bilingual preview receipts with persistent state verification.

These documents are NOT payment receipts, settlement confirmations or a claim
that a physical agent handed cash to a customer.
"""
from __future__ import annotations
from dataclasses import dataclass
from .errors import LabError,require
from .identifiers import display_bdt,synthetic_id
from .policy import AccessPolicy
from .quotes import QuoteService
from .requests import RequestService
from .sessions import SessionContext
from .store import LabStore

TEXT={
    "en": {"title":"Slickk Pay simulation receipt","watermark":"SAMPLE ONLY — NOT PROOF OF PAYMENT",
           "total":"Preview total", "fee":"Illustrative customer fee", "principal":"Principal", 
           "status":"Review state", "tax":"Taxes are not verified", "customer":"Synthetic customer",
           "handover":"No cash handover authorized"},
    "bn": {"title":"স্লিক পে সিমুলেশন রসিদ","watermark":"শুধু নমুনা — পেমেন্টের প্রমাণ নয়",
           "total":"নমুনা মোট মূল্য", "fee":"প্রস্তাবিত গ্রাহক ফি", "principal":"মূল অর্থ",
           "status":"পর্যালোচনার অবস্থা", "tax":"কর যাচাই করা হয়নি", "customer":"কাল্পনিক গ্রাহক",
           "handover":"নগদ হস্তান্তর অনুমোদিত নয়"},
}


@dataclass(frozen=True)
class SampleReceipt:
    request_id:str
    actor_id:str
    language:str
    lines:tuple[tuple[str,str],...]
    watermarked:bool=True
    payment_proof:bool=False
    settlement_proof:bool=False
    simulation:bool=True

    def public(self)->dict[str,object]:
        return {"request_id":self.request_id,"locale":self.language,
                "lines":[{"label":k,"value":v} for k,v in self.lines],
                "watermark":TEXT[self.language]["watermark"],
                "payment_proof":False,"bank_settlement_proof":False,"simulation":True}


class ReceiptService:
    def __init__(self,store:LabStore):
        self.store=store
        self.requests=RequestService(store)
        self.quotes=QuoteService(store)

    def for_request(self,context:SessionContext,request_id:str,locale:str="en")->SampleReceipt:
        AccessPolicy.require(context,"receipt:read",resource_owner=context.actor_id)
        synthetic_id(request_id)
        lang="bn" if locale=="bn" else "en"
        request=self.requests.get(context,request_id)
        quote=self.quotes.get(context,request.quote_id)
        t=TEXT[lang]
        lines=(("",t["title"]),(t["customer"],context.actor_id),
               (t["principal"],"৳"+display_bdt(quote.principal_poisha)),
               (t["fee"],"৳"+display_bdt(quote.fee_poisha)),
               (t["total"],"৳"+display_bdt(quote.total_poisha)),
               (t["status"],request.status),("",t["tax"]),("",t["handover"]))
        return SampleReceipt(request_id,context.actor_id,lang,lines)

    def plaintext(self,context:SessionContext,request_id:str,locale:str="en")->str:
        item=self.for_request(context,request_id,locale)
        return "\n".join([TEXT[item.language]["watermark"]] + [f"{k}: {v}" if k else v for k,v in item.lines])

    def verify_customer_safe(self,receipt:SampleReceipt)->bool:
        require(isinstance(receipt,SampleReceipt),"INVALID_INPUT")
        if not receipt.watermarked or receipt.payment_proof or receipt.settlement_proof or not receipt.simulation:
            raise LabError("AUDIT_INTEGRITY")
        return True
