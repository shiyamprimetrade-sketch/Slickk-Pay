"""Explainable synthetic risk triage for preview-only financial requests.

No score automatically freezes a real identity, rejects real credit, moves
funds or initiates a charge. Risk signals are reproducible and human-review only.
"""
from __future__ import annotations
from dataclasses import dataclass
from .errors import LabError,require
from .identifiers import minor_units
from .sessions import SessionContext
from .quotes import StoredQuote


@dataclass(frozen=True)
class RiskSignal:
    code:str
    severity:int
    explanation:str
    review_action:str


@dataclass(frozen=True)
class RiskAssessment:
    actor:str
    quote_id:str
    risk_points:int
    tier:str
    signals:tuple[RiskSignal,...]
    requires_manual_review:bool
    automated_payment_authorization:bool=False
    simulation:bool=True

    def public(self)->dict[str,object]:
        return {"actor":self.actor,"quote":self.quote_id,"risk_points":self.risk_points,
                "tier":self.tier,"signals":[{"code":x.code,"severity":x.severity,
                "explanation":x.explanation,"review_action":x.review_action} for x in self.signals],
                "requires_manual_review":self.requires_manual_review,"payment_authorized":False,
                "simulation":True,"not_a_credit_decision":True}


@dataclass(frozen=True)
class RiskPolicy:
    high_amount_poisha:int=250_000
    urgent_amount_poisha:int=1_000_000
    many_quotes_threshold:int=5
    device_change_threshold:int=2
    policy_revision:str="sim_risk_2026_01"

    def __post_init__(self)->None:
        minor_units(self.high_amount_poisha)
        minor_units(self.urgent_amount_poisha)
        require(self.urgent_amount_poisha>self.high_amount_poisha,"INVALID_INPUT")
        require(type(self.many_quotes_threshold) is int and 2<=self.many_quotes_threshold<=100,"INVALID_INPUT")
        require(type(self.device_change_threshold) is int and 1<=self.device_change_threshold<=10,"INVALID_INPUT")


class SyntheticRiskEngine:
    def __init__(self,policy:RiskPolicy|None=None):
        self.policy=policy or RiskPolicy()

    def assess(self,context:SessionContext,quote:StoredQuote,*,quotes_last_hour:int=0,
               device_changes_last_day:int=0,unresolved_disputes:int=0,
               counterparty_seen_before:bool=True)->RiskAssessment:
        require(context.actor_id==quote.owner_id,"ROLE_FORBIDDEN")
        for value in (quotes_last_hour,device_changes_last_day,unresolved_disputes):
            require(type(value) is int and 0<=value<=10_000,"INVALID_INPUT")
        require(type(counterparty_seen_before) is bool,"INVALID_INPUT")
        signals:list[RiskSignal]=[]
        if quote.principal_poisha>=self.policy.high_amount_poisha:
            signals.append(RiskSignal("LARGE_PREVIEW_AMOUNT",15,"Larger synthetic amount than usual","Check approved pilot limits"))
        if quote.principal_poisha>=self.policy.urgent_amount_poisha:
            signals.append(RiskSignal("VERY_LARGE_PREVIEW_AMOUNT",30,"High-value fictional request","Manual approval for research only"))
        if quotes_last_hour>=self.policy.many_quotes_threshold:
            signals.append(RiskSignal("QUOTE_VELOCITY",25,"Many draft quotes in an hour","Review for automated abuse"))
        if device_changes_last_day>=self.policy.device_change_threshold:
            signals.append(RiskSignal("DEVICE_CHURN",20,"Synthetic device frequently changed","Verify test environment"))
        if unresolved_disputes>0:
            signals.append(RiskSignal("UNRESOLVED_CASE",15,"Synthetic unresolved case exists","Human case investigation"))
        if not counterparty_seen_before:
            signals.append(RiskSignal("FIRST_COUNTERPARTY",10,"First synthetic counterpart interaction","Confirm display label"))
        if quote.operation in ("cash_out","cash_in"):
            signals.append(RiskSignal("PHYSICAL_CASH_BOUNDARY",25,"Offline physical handover is not supported","Keep cash handover disabled"))
        total=sum(x.severity for x in signals)
        tier="elevated" if total>=60 else "review" if total>=30 else "informational"
        return RiskAssessment(context.actor_id,quote.id,total,tier,tuple(signals),
                              total>=30 or quote.operation in ("cash_in","cash_out"))

    def explain_score(self,assessment:RiskAssessment)->dict[str,object]:
        require(isinstance(assessment,RiskAssessment),"INVALID_INPUT")
        checks=[{"reason":x.code,"points":x.severity} for x in assessment.signals]
        return {"risk_points":assessment.risk_points,"components":checks,
                "points_sum_check":sum(x["points"] for x in checks)==assessment.risk_points,
                "model_type":"deterministic_rules","simulation":True,
                "can_make_credit_decision":False}

    def stress(self,context:SessionContext,quote:StoredQuote,*,max_quotes:int=10)->list[RiskAssessment]:
        require(type(max_quotes) is int and 1<=max_quotes<=100,"INVALID_INPUT")
        return [self.assess(context,quote,quotes_last_hour=n,device_changes_last_day=0,
                            unresolved_disputes=0,counterparty_seen_before=n%2==0) for n in range(max_quotes)]
