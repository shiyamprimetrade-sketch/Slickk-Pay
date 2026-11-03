"""Transparent BDT unit-economics scenarios for *unapproved* Slickk Pay pilot fees.

Outputs are hypotheses, not competitor research or tariff approval. All costs,
agent rewards, and amounts are integer poisha, with explicit assumptions.
"""
from __future__ import annotations
from dataclasses import dataclass
from .money import Rate, minor, minor_to_bdt, ppm
from .errors import InvalidValue


@dataclass(frozen=True)
class UnitEconomicsAssumptions:
    cashout_fee_ppm: int = 10_990
    cashout_commission_ppm: int = 5_500
    cashin_commission_ppm: int = 1_500
    merchant_fee_ppm: int = 4_500
    gateway_expense_ppm: int = 0
    fraud_loss_ppm: int = 0
    cash_transport_ppm: int = 0
    infrastructure_cost_poisha_per_transaction: int = 0
    distributor_cost_poisha_per_transaction: int = 0
    tax_on_fee_ppm: int = 0
    fixed_monthly_cost_poisha: int = 0
    agent_bonus_budget_poisha: int = 0
    version: str = "pilot-2026-11-03-business-hypothesis"

    def __post_init__(self):
        for field in ("cashout_fee_ppm", "cashout_commission_ppm", "cashin_commission_ppm",
                      "merchant_fee_ppm", "gateway_expense_ppm", "fraud_loss_ppm",
                      "cash_transport_ppm", "tax_on_fee_ppm"):
            value=getattr(self,field)
            if type(value) is not int or not 0<=value<=1_000_000:
                raise InvalidValue("Invalid basis-points scenario assumption")
        for field in ("infrastructure_cost_poisha_per_transaction",
                      "distributor_cost_poisha_per_transaction",
                      "fixed_monthly_cost_poisha", "agent_bonus_budget_poisha"):
            value=getattr(self,field)
            minor(value)
            if value<0:
                raise InvalidValue("Negative operating expenses are invalid")


@dataclass(frozen=True)
class ActivityMix:
    cashin_count: int
    cashout_count: int
    merchant_count: int
    transfer_count: int
    average_cashin_poisha: int
    average_cashout_poisha: int
    average_merchant_poisha: int
    average_transfer_poisha: int

    def __post_init__(self):
        for field in ("cashin_count","cashout_count","merchant_count","transfer_count"):
            value=getattr(self,field)
            if type(value) is not int or not 0 <= value <= 10_000_000:
                raise InvalidValue("Transaction counts must be bounded nonnegative integers")
        for field in ("average_cashin_poisha", "average_cashout_poisha",
                      "average_merchant_poisha", "average_transfer_poisha"):
            minor(getattr(self,field))
        for count, amount in ((self.cashin_count,self.average_cashin_poisha),
                              (self.cashout_count,self.average_cashout_poisha),
                              (self.merchant_count,self.average_merchant_poisha),
                              (self.transfer_count,self.average_transfer_poisha)):
            if count and not amount:
                raise InvalidValue("Nonempty activity needs a nonzero average")

    @property
    def number_of_transactions(self) -> int:
        return self.cashin_count+self.cashout_count+self.merchant_count+self.transfer_count


@dataclass(frozen=True)
class PilotMarginReport:
    total_volume_poisha: int
    number_of_transactions: int
    cashout_customer_fee_poisha: int
    merchant_fee_revenue_poisha: int
    cashin_commission_poisha: int
    cashout_commission_poisha: int
    gateway_cost_poisha: int
    fraud_loss_poisha: int
    cash_transport_cost_poisha: int
    tax_poisha: int
    infrastructure_cost_poisha: int
    distributor_cost_poisha: int
    agent_bonus_poisha: int
    fixed_cost_poisha: int
    contribution_poisha: int
    profit_after_fixed_costs_poisha: int
    simulation: bool = True
    approved_tariffs: bool = False

    def public(self) -> dict[str, str | bool | int]:
        return {"number_of_transactions":self.number_of_transactions,
                "volume_bdt":minor_to_bdt(self.total_volume_poisha),
                "cashout_revenue_bdt":minor_to_bdt(self.cashout_customer_fee_poisha),
                "merchant_fee_revenue_bdt":minor_to_bdt(self.merchant_fee_revenue_poisha),
                "agent_commissions_bdt":minor_to_bdt(self.cashin_commission_poisha + self.cashout_commission_poisha),
                "estimated_fraud_bdt":minor_to_bdt(self.fraud_loss_poisha),
                "contribution_bdt":minor_to_bdt(self.contribution_poisha),
                "profit_after_fixed_costs_bdt":minor_to_bdt(self.profit_after_fixed_costs_poisha),
                "break_even":self.profit_after_fixed_costs_poisha >= 0,
                "simulation":True,"approved_tariffs":False}


def compute_margin(mix: ActivityMix, assumptions: UnitEconomicsAssumptions) -> PilotMarginReport:
    cin=mix.cashin_count*mix.average_cashin_poisha
    cout=mix.cashout_count*mix.average_cashout_poisha
    merchant=mix.merchant_count*mix.average_merchant_poisha
    transfers=mix.transfer_count*mix.average_transfer_poisha
    volume=cin+cout+merchant+transfers
    revenue_cashout=ppm(cout,assumptions.cashout_fee_ppm)
    revenue_merchant=ppm(merchant,assumptions.merchant_fee_ppm)
    commission_in=ppm(cin,assumptions.cashin_commission_ppm)
    commission_out=ppm(cout,assumptions.cashout_commission_ppm)
    gateway=ppm(volume,assumptions.gateway_expense_ppm)
    fraud=ppm(volume,assumptions.fraud_loss_ppm)
    transport=ppm(cin+cout,assumptions.cash_transport_ppm)
    tax=ppm(revenue_cashout+revenue_merchant,assumptions.tax_on_fee_ppm)
    infrastructure=mix.number_of_transactions*assumptions.infrastructure_cost_poisha_per_transaction
    distributor=mix.number_of_transactions*assumptions.distributor_cost_poisha_per_transaction
    contribution=(revenue_cashout+revenue_merchant-commission_in-commission_out-gateway-fraud-
                  transport-tax-infrastructure-distributor-assumptions.agent_bonus_budget_poisha)
    return PilotMarginReport(volume,mix.number_of_transactions,revenue_cashout,revenue_merchant,
                             commission_in,commission_out,gateway,fraud,transport,tax,
                             infrastructure,distributor,assumptions.agent_bonus_budget_poisha,
                             assumptions.fixed_monthly_cost_poisha,contribution,
                             contribution-assumptions.fixed_monthly_cost_poisha)


def break_even_transactions(*, principal_poisha: int, mix: str,
                            assumptions: UnitEconomicsAssumptions,
                            target_fixed_cost_poisha: int) -> int | None:
    minor(principal_poisha,positive=True)
    minor(target_fixed_cost_poisha)
    if target_fixed_cost_poisha<0:
        raise InvalidValue("Fixed cost must be nonnegative")
    if mix not in ("cash_in", "cash_out", "merchant_payment", "transfer"):
        raise InvalidValue("Unknown pilot transaction mix")
    if mix == "cash_in":
        activity=ActivityMix(1,0,0,0,principal_poisha,0,0,0)
    elif mix == "cash_out":
        activity=ActivityMix(0,1,0,0,0,principal_poisha,0,0)
    elif mix == "merchant_payment":
        activity=ActivityMix(0,0,1,0,0,0,principal_poisha,0)
    else:
        activity=ActivityMix(0,0,0,1,0,0,0,principal_poisha)
    sample=compute_margin(activity,assumptions)
    unit_margin=sample.contribution_poisha-assumptions.agent_bonus_budget_poisha*0
    if unit_margin<=0:
        return None
    return (target_fixed_cost_poisha+unit_margin-1)//unit_margin


def agent_earnings(*, cashin_volume_poisha: int, cashout_volume_poisha: int,
                   cashin_commission_ppm: int=1_500,
                   cashout_commission_ppm: int=5_500,
                   explicit_bonus_poisha: int=0) -> dict[str,int|bool]:
    minor(cashin_volume_poisha)
    minor(cashout_volume_poisha)
    minor(explicit_bonus_poisha)
    if min(cashin_volume_poisha,cashout_volume_poisha,explicit_bonus_poisha)<0:
        raise InvalidValue("Volume and bonus must be nonnegative")
    cin=ppm(cashin_volume_poisha,cashin_commission_ppm)
    cout=ppm(cashout_volume_poisha,cashout_commission_ppm)
    return {"cashin_commission_poisha":cin,"cashout_commission_poisha":cout,
            "budgeted_bonus_poisha":explicit_bonus_poisha,
            "total_estimated_poisha":cin+cout+explicit_bonus_poisha,
            "simulation":True}
