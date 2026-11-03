"""Privacy-minimized local operational reporting for fictitious-money trials.

Reports are generated from local journal evidence; they cannot be interpreted as
real deposits, bank credits, Bangladesh Bank filings or audited statements.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime,timezone,timedelta
from collections import defaultdict
import csv
import io
import json
import sqlite3
from typing import Iterable

from .ledger import SandboxLedger, InvariantViolation
from .pricing import poisha_to_bdt, initial_pilot


class ReportingError(ValueError):
    pass


@dataclass(frozen=True)
class AccountDistribution:
    kind: str
    count: int
    positive_balance_poisha: int
    frozen_count: int
    simulation: bool=True


@dataclass(frozen=True)
class OperationSummary:
    operation: str
    event_count: int
    debit_total_poisha: int
    credit_total_poisha: int
    distinct_account_count: int
    simulation: bool=True


@dataclass(frozen=True)
class BalanceFinding:
    code: str
    severity: str
    evidence: str
    human_review: bool
    simulation: bool=True


class SandboxReports:
    """Pure read-only queries; never mutate customer or merchant balances."""

    def __init__(self,ledger:SandboxLedger):
        self.ledger=ledger

    def account_distribution(self)->tuple[AccountDistribution,...]:
        with self.ledger._connect() as db:
            rows=db.execute("SELECT kind,COUNT(*) AS total,"
                            "COALESCE(SUM(CASE WHEN balance_poisha>0 THEN balance_poisha ELSE 0 END),0) AS pos,"
                            "COALESCE(SUM(frozen),0) AS frozen_count "
                            "FROM sim_accounts GROUP BY kind ORDER BY kind").fetchall()
        return tuple(AccountDistribution(r["kind"],r["total"],r["pos"],r["frozen_count"])
                     for r in rows)

    def operation_summary(self,*,since_utc:datetime|None=None)->tuple[OperationSummary,...]:
        if since_utc is not None and (since_utc.tzinfo is None or since_utc.utcoffset() is None):
            raise ReportingError("Report timestamp must be timezone-aware")
        predicate=" WHERE e.created_at>=?" if since_utc else ""
        args=(since_utc.astimezone(timezone.utc).isoformat(),) if since_utc else ()
        sql=("SELECT e.operation AS op,COUNT(DISTINCT e.event_id) AS n,"
             "COALESCE(SUM(CASE WHEN p.direction='debit' THEN p.amount_poisha ELSE 0 END),0) AS d,"
             "COALESCE(SUM(CASE WHEN p.direction='credit' THEN p.amount_poisha ELSE 0 END),0) AS c,"
             "COUNT(DISTINCT p.account_id) AS ac FROM sim_events e JOIN sim_postings p "
             "ON p.event_id=e.event_id"+predicate+" GROUP BY e.operation ORDER BY e.operation")
        with self.ledger._connect() as db:
            rows=db.execute(sql,args).fetchall()
        return tuple(OperationSummary(r["op"],r["n"],r["d"],r["c"],r["ac"]) for r in rows)

    def daily_operations(self,*,days:int=7)->tuple[dict,...]:
        if not isinstance(days,int) or not 1<=days<=90:
            raise ReportingError("Invalid reporting window")
        now=datetime.now(timezone.utc)
        threshold=(now-timedelta(days=days)).isoformat()
        with self.ledger._connect() as db:
            rows=db.execute(
                "SELECT substr(created_at,1,10) AS d,operation,COUNT(*) AS count "
                "FROM sim_events WHERE created_at>=? GROUP BY d,operation ORDER BY d,operation",
                (threshold,)).fetchall()
        return tuple({"date_utc":r["d"],"operation":r["operation"],
                      "count":r["count"],"synthetic_events":True} for r in rows)

    def platform_position(self)->dict[str,int|bool]:
        named={"treasury":"sim_platform_treasury","revenue":"sim_platform_revenue",
               "issuer":"sim_issuer"}
        positions={k:self.ledger.account(a).balance_poisha for k,a in named.items()}
        return {"simulation":True,"treasury_poisha":positions["treasury"],
                "revenue_poisha":positions["revenue"],
                "synthetic_issuance_liability_poisha":positions["issuer"],
                "funds_in_real_bank_poisha":0,
                "customer_deposits_insured":False}

    def integrity_findings(self)->tuple[BalanceFinding,...]:
        findings=[]
        try:
            verified=self.ledger.verify()
            findings.append(BalanceFinding("BALANCED_JOURNAL","info",
                                           f"{verified['events']} synthetic journal events verified",False))
        except InvariantViolation:
            findings.append(BalanceFinding("JOURNAL_INVARIANT_FAILED","critical",
                                           "A journal or balance invariant failed",True))
        with self.ledger._connect() as db:
            pending=db.execute("SELECT COUNT(*) FROM sim_gateway_intents WHERE status='created'").fetchone()[0] if (
                db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sim_gateway_intents'").fetchone()) else 0
            risk=db.execute("SELECT COUNT(*) FROM sim_cash_requests WHERE state='disputed'").fetchone()[0] if (
                db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sim_cash_requests'").fetchone()) else 0
            closed_frozen=db.execute("SELECT COUNT(*) FROM sim_accounts WHERE frozen=1").fetchone()[0]
        if pending:
            findings.append(BalanceFinding("PENDING_MERCHANT_INTENTS","notice",
                                           f"{pending} synthetic intents uncompleted",True))
        if risk:
            findings.append(BalanceFinding("SIMULATED_CASH_DISPUTES","warning",
                                           f"{risk} synthetic disputes for human review",True))
        if closed_frozen:
            findings.append(BalanceFinding("FROZEN_ACCOUNTS","notice",
                                           f"{closed_frozen} synthetic accounts frozen",False))
        return tuple(findings)

    def compact_snapshot(self)->dict:
        validation=self.ledger.verify()
        return {"product":"Slickk Pay synthetic finance lab","simulation":True,
                "financial_reports_official":False,"bank_settlements_confirmed":False,
                "verified_journal":validation,
                "accounts":[a.__dict__ for a in self.account_distribution()],
                "operations":[o.__dict__ for o in self.operation_summary()],
                "platform":self.platform_position(),
                "findings":[f.__dict__ for f in self.integrity_findings()]}

    def export_operation_csv(self,*,max_rows:int=500)->str:
        """Export safe aggregate metadata; never expose phone, keys, names or raw PII."""
        if not isinstance(max_rows,int) or not 1<=max_rows<=500:
            raise ReportingError("Invalid export limit")
        values=self.operation_summary()[:max_rows]
        buffer=io.StringIO()
        writer=csv.writer(buffer,lineterminator="\n")
        writer.writerow(["simulation","operation","event_count","debit_bdt","credit_bdt"])
        for row in values:
            writer.writerow(["true",row.operation,row.event_count,
                             poisha_to_bdt(row.debit_total_poisha),
                             poisha_to_bdt(row.credit_total_poisha)])
        return buffer.getvalue()

    def stress_scenario(self,*,cashout_volume:int,average_cashout_poisha:int,
                        cashin_volume:int,average_cashin_poisha:int,
                        monthly_technical_cost_poisha:int=0,
                        expected_loss_poisha:int=0)->dict:
        vals=(cashout_volume,average_cashout_poisha,cashin_volume,average_cashin_poisha,
              monthly_technical_cost_poisha,expected_loss_poisha)
        if any(isinstance(v,bool) or not isinstance(v,int) or v<0 for v in vals):
            raise ReportingError("Stress assumptions must be nonnegative integers")
        pilot=initial_pilot()
        result=pilot.earnings_scenario(cashin_count=cashin_volume,cashout_count=cashout_volume,
             mean_cashin_poisha=average_cashin_poisha,
             mean_cashout_poisha=average_cashout_poisha,
             overhead_poisha=monthly_technical_cost_poisha+expected_loss_poisha)
        return {**result,"independent_bank_fees_modelled":False,"tax_policy_verified":False,
                "cash_transport_costs_modelled":False,"commercially_viable_proven":False,
                "loss_assumption_poisha":expected_loss_poisha,"simulation":True}

    def agent_commissions(self)->tuple[dict,...]:
        with self.ledger._connect() as db:
            rows=db.execute("SELECT owner_id,balance_poisha FROM sim_accounts "
                            "WHERE kind='agent_commission' ORDER BY owner_id").fetchall()
        return tuple({"synthetic_agent_id":r["owner_id"],"commission_poisha":r["balance_poisha"],
                      "money_paid_out":False} for r in rows)

    def transaction_distribution(self)->dict[str,int]:
        result={"customer_transfers":0,"cashin_finalizations":0,"cashout_finalizations":0,
                "synthetic_loan_disbursements":0,"merchant_captures":0}
        names={"customer_transfer":"customer_transfers","cash_in_finalize":"cashin_finalizations",
               "cash_out_finalize":"cashout_finalizations",
               "synthetic_loan_disbursement":"synthetic_loan_disbursements",
               "sandbox_merchant_capture":"merchant_captures"}
        for entry in self.operation_summary():
            if entry.operation in names:
                result[names[entry.operation]]=entry.event_count
        return result
