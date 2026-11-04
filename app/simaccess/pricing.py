"""Versioned pilot price disclosure for *non-settling* sandbox requests.

The tariffs are hypotheses, not current competitor prices or approved rates.
No tax rate is assumed, and quote totals are explicitly tax-incomplete.
"""
from __future__ import annotations
from dataclasses import dataclass
from .errors import LabError, require
from .identifiers import minor_units, ppm_fee, display_bdt


@dataclass(frozen=True)
class PilotRate:
    operation: str
    ppm: int
    minimum_poisha: int
    maximum_poisha: int
    version: str
    commission_ppm: int = 0

    def __post_init__(self) -> None:
        require(self.operation in ("transfer","cash_in","cash_out","merchant_payment"),"INVALID_INPUT")
        require(type(self.ppm) is int and 0<=self.ppm<=100_000,"INVALID_INPUT")
        require(type(self.minimum_poisha) is int and 0<=self.minimum_poisha<=100_000,"INVALID_INPUT")
        require(type(self.maximum_poisha) is int and self.maximum_poisha>=self.minimum_poisha,"INVALID_INPUT")
        require(type(self.commission_ppm) is int and 0<=self.commission_ppm<=100_000,"INVALID_INPUT")
        require(self.version.startswith("sim_pricing_"),"INVALID_INPUT")

    def charge(self,principal:int)->int:
        minor_units(principal)
        if self.ppm==0:
            return 0
        value=ppm_fee(principal,self.ppm)
        return min(max(value,self.minimum_poisha),self.maximum_poisha)

    def commission_preview(self,principal:int)->int:
        minor_units(principal)
        return ppm_fee(principal,self.commission_ppm)


PILOT_RATES = {
    "transfer":PilotRate("transfer",0,0,0,"sim_pricing_2026_01"),
    "cash_in":PilotRate("cash_in",0,0,0,"sim_pricing_2026_01",commission_ppm=1500),
    "cash_out":PilotRate("cash_out",10990,0,200_000,"sim_pricing_2026_01",commission_ppm=5500),
    "merchant_payment":PilotRate("merchant_payment",0,0,0,"sim_pricing_2026_01"),
}
MERCHANT_RATE = PilotRate("merchant_payment",4500,0,200_000,"sim_pricing_2026_01")


@dataclass(frozen=True)
class QuoteDisclosure:
    operation:str
    principal_poisha:int
    customer_fee_poisha:int
    customer_total_poisha:int
    merchant_processing_fee_poisha:int
    agent_commission_preview_poisha:int
    version:str
    tax_verified:bool=False
    tax_status:str="NOT_ASSESSED"
    approved_tariff:bool=False
    simulation:bool=True
    can_pay:bool=False

    def public(self)->dict[str,object]:
        return {"operation":self.operation,"amount_bdt":display_bdt(self.principal_poisha),
                "principal_poisha":self.principal_poisha,"customer_fee_poisha":self.customer_fee_poisha,
                "customer_total_poisha":self.customer_total_poisha,
                "merchant_fee_poisha":self.merchant_processing_fee_poisha,
                "agent_commission_preview_poisha":self.agent_commission_preview_poisha,
                "version":self.version,"tax_verified":False,"tax_status":self.tax_status,
                "total_includes_legal_tax":False,"approved_tariff":False,
                "simulation":True,"can_pay":False}


class PricingEngine:
    def __init__(self,rates:dict[str,PilotRate]|None=None,merchant_rate:PilotRate|None=None):
        self.rates=rates or PILOT_RATES
        self.merchant_rate=merchant_rate or MERCHANT_RATE
        require(set(self.rates)==set(PILOT_RATES),"INVALID_INPUT")

    def quote(self,operation:str,principal:int)->QuoteDisclosure:
        if operation not in self.rates:
            raise LabError("INVALID_INPUT")
        minor_units(principal)
        rate=self.rates[operation]
        customer_fee=rate.charge(principal)
        customer_total=principal+customer_fee if operation!="cash_in" else principal
        merchant_fee=self.merchant_rate.charge(principal) if operation=="merchant_payment" else 0
        return QuoteDisclosure(operation,principal,customer_fee,customer_total,merchant_fee,
                               rate.commission_preview(principal),rate.version)

    def validate_against_version(self,disclosure:QuoteDisclosure)->bool:
        expected=self.quote(disclosure.operation,disclosure.principal_poisha)
        return expected==disclosure

    def compare_scenarios(self,operation:str,amounts:list[int])->list[dict[str,object]]:
        require(isinstance(amounts,list) and len(amounts)<=40,"INVALID_INPUT")
        return [self.quote(operation,amount).public() for amount in amounts]

    def project_agent_margin(self,principal:int,operation:str,
                             *,provider_fee:int=0,fraud_loss:int=0,operations_cost:int=0)->dict[str,object]:
        require(operation in ("cash_in","cash_out"),"INVALID_INPUT")
        for value in (provider_fee,fraud_loss,operations_cost):
            minor_units(value,zero_ok=True)
        disclosure=self.quote(operation,principal)
        total_cost=disclosure.agent_commission_preview_poisha+provider_fee+fraud_loss+operations_cost
        net=disclosure.customer_fee_poisha-total_cost
        return {"operation":operation,"principal_poisha":principal,
                "customer_fee_poisha":disclosure.customer_fee_poisha,
                "commission_poisha":disclosure.agent_commission_preview_poisha,
                "provider_cost_poisha":provider_fee,"fraud_loss_poisha":fraud_loss,
                "operations_cost_poisha":operations_cost,"contribution_poisha":net,
                "economically_positive":net>0,"simulation":True,
                "tax_verification_required":True}

    def zero_fee_operations(self)->tuple[str,...]:
        return tuple(sorted(x for x,r in self.rates.items() if r.ppm==0))
