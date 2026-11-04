"""Cross-record integrity proofs for the non-financial customer/agent lab.

These checks validate read-only snapshots, quote pricing, review transitions
and cash checklist safety, but cannot establish a real monetary ledger balance.
"""
from __future__ import annotations
from dataclasses import dataclass
from .audit import AccessAudit
from .errors import LabError,require
from .identifiers import minor_units
from .pricing import PricingEngine
from .store import LabStore


@dataclass(frozen=True)
class Finding:
    category:str
    reference:str
    severity:str
    reason:str


@dataclass(frozen=True)
class ConsistencyReport:
    checked_quotes:int
    checked_requests:int
    checked_cash_checklists:int
    findings:tuple[Finding,...]
    valid:bool
    simulation:bool=True
    real_bank_verified:bool=False

    def public(self)->dict[str,object]:
        return {"checked_quotes":self.checked_quotes,"checked_requests":self.checked_requests,
                "checked_cash_checklists":self.checked_cash_checklists,
                "findings":[dict(x.__dict__) for x in self.findings],"valid":self.valid,
                "simulation":True,"real_bank_verified":False}


class ConsistencyAuditor:
    def __init__(self,store:LabStore):
        self.store=store
        self.price=PricingEngine()
        self.audit=AccessAudit(store)

    def examine(self)->ConsistencyReport:
        findings:list[Finding]=[]
        with self.store.read() as db:
            quotes=db.execute("SELECT * FROM lab_quotes ORDER BY quote_id").fetchall()
            requests=db.execute("SELECT * FROM lab_requests ORDER BY request_id").fetchall()
            checklists=db.execute("SELECT * FROM lab_cash_checklists ORDER BY request_id").fetchall()
            quote_by_id={row["quote_id"]:row for row in quotes}
            request_by_id={row["request_id"]:row for row in requests}
            for row in quotes:
                try:
                    expected=self.price.quote(row["operation"],row["principal_poisha"])
                except LabError:
                    findings.append(Finding("pricing",row["quote_id"],"critical","Invalid amount or operation"))
                    continue
                if row["total_poisha"]!=row["principal_poisha"]+row["fee_poisha"]:
                    findings.append(Finding("pricing",row["quote_id"],"critical","Total does not match principal plus customer fee"))
                if expected.version!=row["rate_version"] or expected.customer_fee_poisha!=row["fee_poisha"]:
                    findings.append(Finding("pricing",row["quote_id"],"warning","Tariff changed since this quote; do not auto-update existing quote"))
                if row["status"]=="reviewed":
                    count=db.execute("SELECT COUNT(*) FROM lab_requests WHERE quote_id=?",(row["quote_id"],)).fetchone()[0]
                    if count!=1:
                        findings.append(Finding("lifecycle",row["quote_id"],"critical","Reviewed quote must have exactly one request"))
            for row in requests:
                q=quote_by_id.get(row["quote_id"])
                if q is None:
                    findings.append(Finding("lifecycle",row["request_id"],"critical","Orphaned request"))
                    continue
                if row["owner_id"]!=q["owner_id"] or row["kind"]!=q["operation"]:
                    findings.append(Finding("ownership",row["request_id"],"critical","Request does not match quoted owner or operation"))
                if row["no_financial_posting"]!=1:
                    findings.append(Finding("safety",row["request_id"],"critical","Forbidden financial posting flag"))
                if row["status"] not in ("reviewed","cancelled","expired"):
                    findings.append(Finding("safety",row["request_id"],"critical","Unsupported payment state"))
            for row in checklists:
                request=request_by_id.get(row["request_id"])
                if request is None or request["kind"] not in ("cash_in","cash_out"):
                    findings.append(Finding("cash",row["request_id"],"critical","Checklist not linked to cash preview"))
                if row["handover_status"]!="not_authorized":
                    findings.append(Finding("cash",row["request_id"],"critical","Physical cash handover illegally asserted"))
        proof=self.audit.verify()
        if not proof.valid:
            findings.append(Finding("audit","sim_audit_chain","critical","Audit chain mismatch"))
        return ConsistencyReport(len(quotes),len(requests),len(checklists),tuple(findings),not findings)

    def assert_valid(self)->ConsistencyReport:
        result=self.examine()
        if not result.valid:
            raise LabError("AUDIT_INTEGRITY")
        return result
