"""Data minimization and provenance checks for synthetic financial responses."""
from __future__ import annotations
from dataclasses import dataclass
import re
from typing import Any
from .errors import LabError,require
from .identifiers import canonical

SECRET_KEYS=frozenset({"pin","salt","pin_hash","bearer","authorization","password","token",
                       "secret","nid","national_id","phone","card_number","bank_account",
                       "otp","private_key","real_email","session_cookie"})
FORBIDDEN_FINANCIAL_KEYS=frozenset({"real_money_authorized","ledger_posted","settled_in_bank",
                                    "is_bank_deposit","credit_disbursed","cash_handed_over"})


@dataclass(frozen=True)
class Exposure:
    field_path:str
    reason:str


@dataclass(frozen=True)
class PrivacyReport:
    safe:bool
    issues:tuple[Exposure,...]
    inspected_fields:int
    simulation:bool=True


class PrivacyInspector:
    def inspect(self,data:Any,*,max_depth:int=10,max_fields:int=4000)->PrivacyReport:
        require(type(max_depth) is int and 1<=max_depth<=20,"INVALID_INPUT")
        require(type(max_fields) is int and 10<=max_fields<=10000,"INVALID_INPUT")
        issues:list[Exposure]=[]
        counter=[0]
        def scan(value:Any,path:str,depth:int)->None:
            if depth>max_depth:
                issues.append(Exposure(path,"DEPTH_EXCEEDED"))
                return
            counter[0]+=1
            if counter[0]>max_fields:
                issues.append(Exposure(path,"TOO_MANY_FIELDS"))
                return
            if isinstance(value,dict):
                for key,item in value.items():
                    if not isinstance(key,str):
                        issues.append(Exposure(path,"NON_STRING_KEY"))
                        continue
                    name=key.lower().replace("-","_")
                    current=f"{path}.{key}" if path else key
                    if name in SECRET_KEYS:
                        issues.append(Exposure(current,"PRIVATE_FIELD"))
                    if name in FORBIDDEN_FINANCIAL_KEYS and item is True:
                        issues.append(Exposure(current,"UNSUPPORTED_MONEY_CLAIM"))
                    scan(item,current,depth+1)
            elif isinstance(value,(list,tuple)):
                for idx,item in enumerate(value):
                    scan(item,f"{path}[{idx}]",depth+1)
            elif type(value) is float:
                issues.append(Exposure(path,"FLOAT_IN_FINANCIAL_CONTRACT"))
            elif isinstance(value,str):
                if len(value)>10000:
                    issues.append(Exposure(path,"EXCESSIVE_TEXT"))
                if re.search(r"\b(?:\+?880|0)1[3-9]\d{8}\b",value):
                    issues.append(Exposure(path,"POSSIBLE_REAL_PHONE"))
        scan(data,"",0)
        return PrivacyReport(not issues,tuple(issues),counter[0])

    def assert_safe(self,data:Any)->None:
        report=self.inspect(data)
        if not report.safe:
            raise LabError("INVALID_INPUT")

    def audit_public_contract(self,data:dict[str,object])->dict[str,object]:
        report=self.inspect(data)
        return {"simulation":True,"safe":report.safe,"inspected_fields":report.inspected_fields,
                "issue_codes":sorted(set(issue.reason for issue in report.issues))}


def safe_public_output(payload:dict[str,object])->dict[str,object]:
    PrivacyInspector().assert_safe(payload)
    return payload
