"""Bangla/English disclosures for quote and agent commission previews.

No tariff here represents an approved rate. The absence of verified taxes is
explicit, and the final payable amount is NOT presented as legally final.
"""
from __future__ import annotations
from dataclasses import dataclass
from .errors import LabError,require
from .identifiers import display_bdt,minor_units
from .pricing import PricingEngine,QuoteDisclosure

LANGUAGE={
 "en": {
  "title":"Slickk Pay fictional transaction preview",
  "not_live":"Simulation only — no money will move",
  "not_approved":"Pilot fee assumptions, not approved charges",
  "tax_unknown":"Applicable taxes and final payable total are NOT verified",
  "principal":"Principal","customer_fee":"Illustrative customer fee",
  "total":"Illustrative total before unverified taxes",
  "agent_commission":"Illustrative agent commission, not income earned",
  "merchant_fee":"Illustrative merchant processing fee",
  "handover":"No agent cash handover or settlement authorized",
 },
 "bn": {
  "title":"স্লিক পে কাল্পনিক লেনদেনের নমুনা",
  "not_live":"শুধু সিমুলেশন — কোনো অর্থ স্থানান্তর হবে না",
  "not_approved":"প্রস্তাবিত ফি, অনুমোদিত চার্জ নয়",
  "tax_unknown":"প্রযোজ্য কর ও চূড়ান্ত পরিশোধযোগ্য টাকা যাচাই করা হয়নি",
  "principal":"মূল টাকা","customer_fee":"গ্রাহকের নমুনা ফি",
  "total":"কর যাচাই ছাড়া নমুনা মোট",
  "agent_commission":"এজেন্টের নমুনা কমিশন, অর্জিত আয় নয়",
  "merchant_fee":"মার্চেন্টের নমুনা প্রসেসিং ফি",
  "handover":"নগদ হস্তান্তর বা নিষ্পত্তির অনুমতি নেই",
 },
}


@dataclass(frozen=True)
class DisclosurePage:
    language:str
    headline:str
    notices:tuple[str,...]
    breakdown:tuple[tuple[str,str],...]
    amount_is_final:bool=False
    tariff_approved:bool=False
    tax_verified:bool=False
    simulation:bool=True

    def public(self)->dict[str,object]:
        return {"locale":self.language,"title":self.headline,
                "notices":list(self.notices),
                "breakdown":[{"label":a,"value":b} for a,b in self.breakdown],
                "amount_is_final":False,"tariff_approved":False,
                "tax_verified":False,"simulation":True}


class DisclosureService:
    def __init__(self,pricing:PricingEngine|None=None):
        self.pricing=pricing or PricingEngine()

    def for_quote(self,quote:QuoteDisclosure,locale:str="en")->DisclosurePage:
        require(isinstance(quote,QuoteDisclosure),"INVALID_INPUT")
        lang="bn" if locale=="bn" else "en"
        d=LANGUAGE[lang]
        breakdown=((d["principal"],"৳"+display_bdt(quote.principal_poisha)),
                   (d["customer_fee"],"৳"+display_bdt(quote.customer_fee_poisha)),
                   (d["total"],"৳"+display_bdt(quote.customer_total_poisha)),
                   (d["agent_commission"],"৳"+display_bdt(quote.agent_commission_preview_poisha)),
                   (d["merchant_fee"],"৳"+display_bdt(quote.merchant_processing_fee_poisha)))
        notices=(d["not_live"],d["not_approved"],d["tax_unknown"],d["handover"])
        return DisclosurePage(lang,d["title"],notices,breakdown)

    def for_amount(self,operation:str,principal_poisha:int,locale:str="en")->DisclosurePage:
        minor_units(principal_poisha)
        return self.for_quote(self.pricing.quote(operation,principal_poisha),locale)

    def explain_english(self,operation:str,principal_poisha:int)->str:
        page=self.for_amount(operation,principal_poisha,"en")
        return "\n".join((page.headline,)+page.notices+tuple(f"{k}: {v}" for k,v in page.breakdown))

    def explain_bangla(self,operation:str,principal_poisha:int)->str:
        page=self.for_amount(operation,principal_poisha,"bn")
        return "\n".join((page.headline,)+page.notices+tuple(f"{k}: {v}" for k,v in page.breakdown))
