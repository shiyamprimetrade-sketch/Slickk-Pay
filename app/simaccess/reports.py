"""Read-only simulated operations metrics and contribution economics.

Metrics are aggregates over fictional records, explicitly disclaimed and not
business traction, audited revenue, actual bank settlement or live fraud data.
"""
from __future__ import annotations
from dataclasses import dataclass
from .audit import AccessAudit
from .errors import LabError,require
from .identifiers import minor_units
from .policy import AccessPolicy
from .pricing import PricingEngine
from .sessions import SessionContext
from .store import LabStore


@dataclass(frozen=True)
class Coverage:
    customers:int
    agents:int
    merchants:int
    operators:int
    quotes:int
    reviews:int
    synthetic_activity:int
    audit_events:int
    simulation:bool=True
    observed_users:int=0
    settled_value_poisha:int=0

    def public(self)->dict[str,object]:
        return dict(self.__dict__)


class LabReports:
    def __init__(self,store:LabStore):
        self.store=store
        self.audit=AccessAudit(store)
        self.pricing=PricingEngine()

    def coverage(self,context:SessionContext)->Coverage:
        AccessPolicy.require(context,"audit:read",resource_owner=context.actor_id)
        if context.role!="operator":
            raise LabError("ROLE_FORBIDDEN")
        with self.store.read() as db:
            roles={row["role"]:row["n"] for row in db.execute("SELECT role,COUNT(*) AS n FROM lab_actors GROUP BY role")}
            quotes=db.execute("SELECT COUNT(*) FROM lab_quotes").fetchone()[0]
            reviews=db.execute("SELECT COUNT(*) FROM lab_requests").fetchone()[0]
            activity=db.execute("SELECT COUNT(*) FROM lab_activity").fetchone()[0]
            audits=db.execute("SELECT COUNT(*) FROM lab_audit").fetchone()[0]
        return Coverage(roles.get("customer",0),roles.get("agent",0),roles.get("merchant",0),
                        roles.get("operator",0),quotes,reviews,activity,audits)

    def quote_stats(self,context:SessionContext)->dict[str,object]:
        AccessPolicy.require(context,"audit:read",resource_owner=context.actor_id)
        if context.role!="operator":
            raise LabError("ROLE_FORBIDDEN")
        with self.store.read() as db:
            rows=db.execute("SELECT operation,status,COUNT(*) AS n,SUM(principal_poisha) AS amount FROM lab_quotes GROUP BY operation,status ORDER BY operation,status").fetchall()
        return {"sample_quote_rows":[{"operation":x["operation"],"status":x["status"],
                                      "count":x["n"],"sample_poisha":x["amount"] or 0} for x in rows],
                "real_payment_volume_poisha":0,"simulation":True}

    def explain_pricing(self,principal:int,*,provider_cost:int=0,operator_cost:int=0,
                        expected_fraud_loss:int=0)->dict[str,object]:
        for value in (principal,):
            minor_units(value)
        for value in (provider_cost,operator_cost,expected_fraud_loss):
            minor_units(value,zero_ok=True)
        lines=[]
        for kind in ("cash_in","cash_out"):
            row=self.pricing.project_agent_margin(principal,kind,provider_fee=provider_cost,
                                                   operations_cost=operator_cost,fraud_loss=expected_fraud_loss)
            lines.append(row)
        return {"rows":lines,"production_rates_verified":False,"profit_guaranteed":False,
                "fees_exclude_unverified_tax":True,"simulation":True}

    def synthetic_kpi(self,context:SessionContext)->dict[str,object]:
        coverage=self.coverage(context)
        quote_stats=self.quote_stats(context)
        return {"sample_personas":coverage.customers+coverage.agents+coverage.merchants,
                "sample_review_requests":coverage.reviews,"sample_activities":coverage.synthetic_activity,
                "sample_quotes":coverage.quotes,"sample_quote_by_category":quote_stats["sample_quote_rows"],
                "real_daily_active_customers":0,"real_revenue_poisha":0,
                "real_bank_settlements":0,"real_chargebacks":0,
                "synthetic_only":True,"simulation":True}
