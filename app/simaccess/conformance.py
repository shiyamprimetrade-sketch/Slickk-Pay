"""Machine-checkable invariant probes and release-gate contracts.

An invariant being true is only evidence for the isolated fixture lab, not a
banking approval or permission to enable production payment activity.
"""
from __future__ import annotations
from dataclasses import dataclass
from .audit import AccessAudit
from .errors import LabError,require
from .identifiers import canonical
from .policy import POLICY,FORBIDDEN_CAPABILITIES
from .privacy import PrivacyInspector
from .service import AccessLab


@dataclass(frozen=True)
class Invariant:
    name:str
    passed:bool
    evidence:str


@dataclass(frozen=True)
class ConformanceReport:
    checks:tuple[Invariant,...]
    passed:bool
    simulation:bool=True
    production_ready:bool=False

    def public(self)->dict[str,object]:
        return {"checks":[{"name":x.name,"passed":x.passed,"evidence":x.evidence} for x in self.checks],
                "passed":self.passed,"simulation":True,"production_ready":False}


class ConformanceSuite:
    def __init__(self,lab:AccessLab):
        self.lab=lab

    def run(self)->ConformanceReport:
        checks=[]
        def append(name:str,condition:bool,evidence:str)->None:
            checks.append(Invariant(name,bool(condition),evidence))
        health=self.lab.store.health()
        append("isolated_storage",health["database"]=="isolated_sqlite_local_test_only","local simulator")
        append("sqlite_integrity",health["sqlite_integrity"] is True,"SQLite integrity_check")
        append("foreign_keys",health["foreign_key_violations"]==0,"PRAGMA foreign_key_check")
        audit=self.lab.audit.verify()
        append("audit_chain",audit.valid,f"{audit.checked} append-only records")
        append("policy_no_posting",all(not (allowed & FORBIDDEN_CAPABILITIES) for allowed in POLICY.values()),"RBAC matrix")
        append("provider_absent",not self.lab.capabilities.bank_connected and not self.lab.capabilities.checkout_provider_connected,"no gateway client")
        append("no_credit",not self.lab.capabilities.can_issue_loans,"credit disabled")
        append("no_cash_handover",not self.lab.capabilities.allows_cash_handover,"no handover API")
        append("no_deposits",not self.lab.capabilities.accepts_deposits,"deposit disabled")
        append("no_money",not self.lab.capabilities.can_move_money,"posting disabled")
        append("requests_no_posting",self.lab.recovery.assert_no_financial_posting(),"request check constraint")
        with self.lab.store.read() as db:
            statuses=db.execute("SELECT DISTINCT status FROM lab_requests").fetchall()
            append("request_state_space",all(x["status"] in ("reviewed","cancelled","expired") for x in statuses),"no paid state")
            count=db.execute("SELECT COUNT(*) FROM lab_cash_checklists WHERE handover_status!='not_authorized'").fetchone()[0]
            append("cash_not_authorized",count==0,"cash table CHECK constraint")
        append("public_capabilities",PrivacyInspector().inspect(self.lab.capabilities.public()).safe,"privacy contract")
        return ConformanceReport(tuple(checks),all(c.passed for c in checks))

    def assert_release_safe(self)->ConformanceReport:
        report=self.run()
        if not report.passed:
            raise LabError("AUDIT_INTEGRITY")
        return report
