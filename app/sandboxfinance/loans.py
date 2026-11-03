"""Synthetic-only microcredit lifecycle with explainable, deterministic loan policy.

All credit histories and eligibility metrics are artificial test inputs. This
software cannot issue real loans, query a credit bureau or judge real people.
Loan value movements must balance in the fictitious ledger and remain separate
from the provider-led merchant checkout.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import secrets
import sqlite3
from typing import Literal

from .identity import SyntheticRegistry
from .ledger import SandboxLedger, Posting, LedgerError


class CreditError(ValueError):
    pass


class CreditPolicyDenied(CreditError):
    pass


class CreditStateError(CreditError):
    pass


LOAN_SIZES = frozenset({100_000,300_000,500_000,1_000_000,2_500_000})


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="microseconds")


def _half_up(num: int, denom: int) -> int:
    if denom <= 0 or num < 0:
        raise CreditError("Invalid interest factor")
    whole,rem=divmod(num,denom)
    return whole+(1 if rem*2>=denom else 0)


@dataclass(frozen=True)
class CreditPolicy:
    version: str
    annual_interest_bps: int
    maximum_debt_to_income_bps: int
    minimum_monthly_net_income_poisha: int
    maximum_existing_debt_poisha: int
    eligible_sizes: frozenset[int]
    allowed_terms_months: frozenset[int]
    origination_fee_poisha: int = 0
    real_lending_enabled: bool = False

    def __post_init__(self):
        if self.real_lending_enabled:
            raise CreditError("Software credit policy must not authorize real lending")
        if not self.version or not 0<=self.annual_interest_bps<=5000:
            raise CreditError("Unsupported synthetic policy")
        if not 0<self.maximum_debt_to_income_bps<=10000:
            raise CreditError("Invalid DTI ceiling")
        if not self.eligible_sizes.issubset(LOAN_SIZES) or not self.allowed_terms_months:
            raise CreditError("Invalid experimental loan product")
        if self.origination_fee_poisha<0:
            raise CreditError("Invalid disclosed fee")


@dataclass(frozen=True)
class BorrowerEvidence:
    customer_id: str
    synthetic_income_poisha: int
    synthetic_living_expenses_poisha: int
    synthetic_existing_monthly_debt_poisha: int
    synthetic_credit_history_score: int
    explicitly_fictional: bool = True

    def __post_init__(self):
        if not self.explicitly_fictional:
            raise CreditError("Real borrower records are not allowed")
        if not all(isinstance(x,int) and not isinstance(x,bool) and x>=0 for x in (
            self.synthetic_income_poisha,self.synthetic_living_expenses_poisha,
            self.synthetic_existing_monthly_debt_poisha)):
            raise CreditError("Invalid synthetic affordability evidence")
        if not 0<=self.synthetic_credit_history_score<=1000:
            raise CreditError("Invalid synthetic credit score")


@dataclass(frozen=True)
class Installment:
    number: int
    principal_poisha: int
    interest_poisha: int
    due_date: str

    @property
    def payable_poisha(self) -> int:
        return self.principal_poisha+self.interest_poisha


@dataclass(frozen=True)
class CreditAssessment:
    eligible: bool
    reason_codes: tuple[str,...]
    policy_version: str
    monthly_obligation_poisha: int
    synthetic_debt_to_income_bps: int
    total_repayment_poisha: int
    total_interest_poisha: int
    simulation: bool = True


@dataclass(frozen=True)
class CreditCase:
    application_id: str
    customer_id: str
    principal_poisha: int
    term_months: int
    status: str
    remaining_principal_poisha: int
    remaining_interest_poisha: int
    policy_version: str
    decision_reasons: tuple[str,...]
    created_at: str
    simulation: bool = True


SCHEMA = """
CREATE TABLE IF NOT EXISTS sim_credit_applications(
 application_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL,
 principal_poisha INTEGER NOT NULL CHECK(principal_poisha>0),
 term_months INTEGER NOT NULL CHECK(term_months>0),
 status TEXT NOT NULL CHECK(status IN ('applied','approved','denied','disbursed','paid_off','default_review')),
 remaining_principal_poisha INTEGER NOT NULL CHECK(remaining_principal_poisha>=0),
 remaining_interest_poisha INTEGER NOT NULL CHECK(remaining_interest_poisha>=0),
 policy_version TEXT NOT NULL, decision_reasons TEXT NOT NULL,
 created_at TEXT NOT NULL, disbursed_at TEXT, disbursement_event_id TEXT
);
CREATE TABLE IF NOT EXISTS sim_credit_installments(
 application_id TEXT NOT NULL REFERENCES sim_credit_applications(application_id),
 installment_number INTEGER NOT NULL,
 due_date TEXT NOT NULL,
 principal_poisha INTEGER NOT NULL CHECK(principal_poisha>0),
 interest_poisha INTEGER NOT NULL CHECK(interest_poisha>=0),
 status TEXT NOT NULL CHECK(status IN ('due','paid','waived')),
 payment_event_id TEXT,
 PRIMARY KEY(application_id,installment_number)
);
CREATE TABLE IF NOT EXISTS sim_credit_audit(
 audit_id INTEGER PRIMARY KEY AUTOINCREMENT,application_id TEXT NOT NULL,
 from_state TEXT,to_state TEXT NOT NULL,actor_id TEXT NOT NULL,
 reason TEXT NOT NULL,created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS sim_credit_audit_update_block BEFORE UPDATE ON sim_credit_audit
 BEGIN SELECT RAISE(ABORT,'credit audit immutable'); END;
CREATE TRIGGER IF NOT EXISTS sim_credit_audit_delete_block BEFORE DELETE ON sim_credit_audit
 BEGIN SELECT RAISE(ABORT,'credit audit immutable'); END;
CREATE INDEX IF NOT EXISTS sim_credit_due ON sim_credit_installments(due_date,status);
"""


def pilot_credit_policy()->CreditPolicy:
    return CreditPolicy("synthetic-loan-v1",1200,3500,80_000,100_000,
                        LOAN_SIZES,frozenset({3,6,9,12}),0)


def amortization_schedule(principal:int,months:int,annual_bps:int,
                          *,start_date:date|None=None)->tuple[Installment,...]:
    if isinstance(principal,bool) or not isinstance(principal,int) or principal<=0:
        raise CreditError("Invalid loan principal")
    if not isinstance(months,int) or not 1<=months<=60 or not 0<=annual_bps<=5000:
        raise CreditError("Invalid synthetic term/rate")
    start=start_date or _utc().date()
    remaining=principal
    rows=[]
    for number in range(1,months+1):
        principal_due=principal//months+(1 if number<=principal%months else 0)
        interest_due=_half_up(remaining*annual_bps,120_000)
        remaining-=principal_due
        # Day-based test schedule avoids pretending to implement bank calendar rules.
        due=start+timedelta(days=30*number)
        rows.append(Installment(number,principal_due,interest_due,due.isoformat()))
    assert remaining==0
    return tuple(rows)


def assess(policy:CreditPolicy,evidence:BorrowerEvidence,principal:int,months:int)->CreditAssessment:
    if principal not in policy.eligible_sizes or months not in policy.allowed_terms_months:
        raise CreditError("Requested size or term not available in sandbox pilot")
    schedule=amortization_schedule(principal,months,policy.annual_interest_bps)
    monthly_payment=max(i.payable_poisha for i in schedule)
    reasons=[]
    net=evidence.synthetic_income_poisha-evidence.synthetic_living_expenses_poisha
    if net<policy.minimum_monthly_net_income_poisha:
        reasons.append("INSUFFICIENT_SYNTHETIC_NET_INCOME")
    if evidence.synthetic_existing_monthly_debt_poisha>policy.maximum_existing_debt_poisha:
        reasons.append("EXISTING_SYNTHETIC_DEBT_HIGH")
    if evidence.synthetic_credit_history_score<350:
        reasons.append("SYNTHETIC_SCORE_BELOW_POLICY")
    dti=_half_up((evidence.synthetic_existing_monthly_debt_poisha+monthly_payment)*10000,
                 max(1,evidence.synthetic_income_poisha))
    if dti>policy.maximum_debt_to_income_bps:
        reasons.append("DTI_ABOVE_PILOT_LIMIT")
    total_interest=sum(i.interest_poisha for i in schedule)
    return CreditAssessment(not reasons,tuple(reasons),policy.version,
                            monthly_payment,dti,principal+total_interest+policy.origination_fee_poisha,
                            total_interest)


class SyntheticLoanBook:
    """Explicit simulation-only application, decision, disbursement and repayments."""

    def __init__(self,ledger:SandboxLedger,registry:SyntheticRegistry,
                 policy:CreditPolicy|None=None):
        self.ledger=ledger
        self.registry=registry
        self.policy=policy or pilot_credit_policy()
        with ledger._lock,ledger._connect() as db:
            db.executescript(SCHEMA)

    def _customer(self,customer_id:str):
        party=self.registry.lookup(customer_id,required_role="customer")
        if party.status!="sandbox_verified":
            raise CreditError("Only verified synthetic customer fixtures are eligible")
        return party

    def _load(self,db:sqlite3.Connection,application_id:str):
        row=db.execute("SELECT * FROM sim_credit_applications WHERE application_id=?",
                       (application_id,)).fetchone()
        if not row:
            raise CreditError("Loan application not found")
        return row

    def _case(self,row:sqlite3.Row)->CreditCase:
        return CreditCase(row["application_id"],row["customer_id"],row["principal_poisha"],
                          row["term_months"],row["status"],row["remaining_principal_poisha"],
                          row["remaining_interest_poisha"],row["policy_version"],
                          tuple(json.loads(row["decision_reasons"])),row["created_at"])

    def case(self,application_id:str)->CreditCase:
        with self.ledger._connect() as db:
            return self._case(self._load(db,application_id))

    def _audit(self,db:sqlite3.Connection,application_id:str,old:str|None,new:str,
               actor:str,reason:str)->None:
        db.execute("INSERT INTO sim_credit_audit(application_id,from_state,to_state,actor_id,reason,created_at) "
                   "VALUES(?,?,?,?,?,?)",(application_id,old,new,actor,reason,_iso(_utc())))

    def apply(self,*,evidence:BorrowerEvidence,principal_poisha:int,term_months:int)->tuple[CreditCase,CreditAssessment]:
        self._customer(evidence.customer_id)
        assessment=assess(self.policy,evidence,principal_poisha,term_months)
        application_id="sim_loan_"+secrets.token_hex(12)
        schedule=amortization_schedule(principal_poisha,term_months,self.policy.annual_interest_bps)
        with self.ledger._lock,self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute("INSERT INTO sim_credit_applications VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                           (application_id,evidence.customer_id,principal_poisha,term_months,
                            "applied",principal_poisha,assessment.total_interest_poisha,
                            self.policy.version,json.dumps(assessment.reason_codes),_iso(_utc()),None,None))
                for item in schedule:
                    db.execute("INSERT INTO sim_credit_installments VALUES(?,?,?,?,?,?,?)",
                               (application_id,item.number,item.due_date,item.principal_poisha,
                                item.interest_poisha,"due",None))
                self._audit(db,application_id,None,"applied",evidence.customer_id,
                            "synthetic_credit_application")
                db.commit()
            except Exception:
                db.rollback()
                raise
        return self.case(application_id),assessment

    def decide(self,application_id:str,*,operator_id:str,approve:bool,assessment:CreditAssessment,
               explanation:str)->CreditCase:
        if not operator_id.startswith("sim_") or not isinstance(approve,bool):
            raise CreditError("Only synthetic operator assertions are permitted")
        if not isinstance(explanation,str) or not 4<=len(explanation)<=160:
            raise CreditError("An explanation must accompany every decision")
        with self.ledger._lock,self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row=self._load(db,application_id)
                if row["status"]!="applied":
                    raise CreditStateError("Application already decided")
                if row["policy_version"]!=assessment.policy_version:
                    raise CreditError("Credit policy changed between assessment and decision")
                if approve and (not assessment.eligible or assessment.reason_codes):
                    raise CreditPolicyDenied("Approval violates synthetic affordability policy")
                state="approved" if approve else "denied"
                db.execute("UPDATE sim_credit_applications SET status=? WHERE application_id=?",
                           (state,application_id))
                self._audit(db,application_id,"applied",state,operator_id,explanation)
                db.commit()
            except Exception:
                db.rollback()
                raise
        return self.case(application_id)

    def disburse(self,application_id:str,*,operator_id:str)->CreditCase:
        """Only treasury-funded fictitious issuance: never actual lender disbursement."""
        if not operator_id.startswith("sim_"):
            raise CreditError("Invalid synthetic operator")
        with self.ledger._lock,self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row=self._load(db,application_id)
                if row["status"]!="approved":
                    raise CreditStateError("Only approved sandbox loans may be disbursed")
                principal=row["principal_poisha"]
                receipt=self.ledger.post_in_transaction(
                    db,operation="synthetic_loan_disbursement",
                    idempotency_key=application_id+":disburse",
                    postings=[Posting("sim_platform_treasury","debit",principal),
                              Posting("sim_wallet_"+row["customer_id"][4:],"credit",principal)])
                db.execute("UPDATE sim_credit_applications SET status='disbursed',disbursed_at=?,"
                           "disbursement_event_id=? WHERE application_id=?",
                           (_iso(_utc()),receipt.event_id,application_id))
                self._audit(db,application_id,"approved","disbursed",operator_id,
                            "fictional_treasury_funded_loan")
                db.commit()
            except Exception:
                db.rollback()
                raise
        return self.case(application_id)

    def installment_plan(self,application_id:str)->tuple[dict,...]:
        with self.ledger._connect() as db:
            self._load(db,application_id)
            return tuple(dict(row) for row in db.execute(
                "SELECT installment_number,due_date,principal_poisha,interest_poisha,status "
                "FROM sim_credit_installments WHERE application_id=? ORDER BY installment_number",
                (application_id,)).fetchall())

    def pay_next(self,application_id:str,*,customer_id:str)->CreditCase:
        self._customer(customer_id)
        with self.ledger._lock,self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                loan=self._load(db,application_id)
                if loan["customer_id"]!=customer_id:
                    raise CreditError("Borrower does not own this synthetic loan")
                if loan["status"]!="disbursed":
                    raise CreditStateError("Loan is not open for repayment")
                installment=db.execute(
                    "SELECT * FROM sim_credit_installments WHERE application_id=? AND status='due' "
                    "ORDER BY installment_number LIMIT 1",(application_id,)).fetchone()
                if installment is None:
                    raise CreditStateError("No installment due")
                principal=installment["principal_poisha"]
                interest=installment["interest_poisha"]
                lines=[Posting("sim_wallet_"+customer_id[4:],"debit",principal+interest),
                       Posting("sim_platform_treasury","credit",principal)]
                if interest:
                    lines.append(Posting("sim_platform_revenue","credit",interest))
                reference=application_id+":pay:"+str(installment["installment_number"])
                receipt=self.ledger.post_in_transaction(
                    db,operation="synthetic_loan_repayment",idempotency_key=reference,postings=lines)
                db.execute("UPDATE sim_credit_installments SET status='paid',payment_event_id=? "
                           "WHERE application_id=? AND installment_number=?",
                           (receipt.event_id,application_id,installment["installment_number"]))
                remaining_principal=loan["remaining_principal_poisha"]-principal
                remaining_interest=loan["remaining_interest_poisha"]-interest
                if min(remaining_principal,remaining_interest)<0:
                    raise CreditError("Repayment schedule exceeds recorded outstanding loan")
                new_state="paid_off" if remaining_principal==0 and remaining_interest==0 else "disbursed"
                db.execute("UPDATE sim_credit_applications SET remaining_principal_poisha=?,"
                           "remaining_interest_poisha=?,status=? WHERE application_id=?",
                           (remaining_principal,remaining_interest,new_state,application_id))
                self._audit(db,application_id,loan["status"],new_state,customer_id,
                            "synthetic_installment_repaid")
                db.commit()
            except Exception:
                db.rollback()
                raise
        return self.case(application_id)

    def overdue(self,as_of:date|None=None)->tuple[dict,...]:
        today=(as_of or _utc().date()).isoformat()
        with self.ledger._connect() as db:
            return tuple(dict(row) for row in db.execute(
                "SELECT a.application_id,a.customer_id,i.installment_number,i.due_date,"
                "i.principal_poisha+i.interest_poisha AS overdue_poisha "
                "FROM sim_credit_installments i JOIN sim_credit_applications a "
                "ON a.application_id=i.application_id WHERE i.status='due' "
                "AND a.status='disbursed' AND i.due_date<? ORDER BY i.due_date",(today,)).fetchall())

    def portfolio(self)->dict[str,int|bool]:
        with self.ledger._connect() as db:
            rows=db.execute("SELECT status,COUNT(*) AS n,COALESCE(SUM(remaining_principal_poisha),0) AS p "
                            "FROM sim_credit_applications GROUP BY status").fetchall()
        result={"simulation":True,"unlicensed_real_loans":0}
        for row in rows:
            result[row["status"]+"_count"]=row["n"]
            result[row["status"]+"_principal_poisha"]=row["p"]
        return result

    def audit(self,application_id:str)->tuple[dict,...]:
        with self.ledger._connect() as db:
            self._load(db,application_id)
            return tuple(dict(row) for row in db.execute(
                "SELECT from_state,to_state,actor_id,reason,created_at FROM sim_credit_audit "
                "WHERE application_id=? ORDER BY audit_id",(application_id,)).fetchall())
