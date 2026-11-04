"""Server-authoritative response contract checks for future mobile adapters.

Rejects ambiguous money fields, absent simulation labels and accidental
production-role claims. Reuses typed payloads rather than exposing a mobile
SDK with an embedded shared operator credential.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from .errors import LabError,require
from .identifiers import minor_units,synthetic_id
from .privacy import PrivacyInspector


@dataclass(frozen=True)
class ContractResult:
    valid:bool
    contract:str
    reasons:tuple[str,...]
    simulation:bool=True
    can_move_money:bool=False


class ResponseContract:
    def __init__(self)->None:
        self.privacy=PrivacyInspector()

    def validate(self,kind:str,payload:dict[str,Any])->ContractResult:
        require(isinstance(payload,dict) and isinstance(kind,str),"INVALID_INPUT")
        reasons=[]
        if payload.get("simulation") is not True:
            reasons.append("SIMULATION_LABEL_REQUIRED")
        if payload.get("can_move_money") is True or payload.get("can_pay") is True:
            reasons.append("FORBIDDEN_PAYMENT_CAPABILITY")
        report=self.privacy.inspect(payload)
        if not report.safe:
            reasons.extend(x.reason for x in report.issues)
        if kind=="quote":
            fields=("quote_id","principal_poisha","fee_poisha","total_poisha","status")
            if not all(f in payload for f in fields):
                reasons.append("QUOTE_FIELDS_MISSING")
            else:
                try:
                    synthetic_id(payload["quote_id"])
                    principal=minor_units(payload["principal_poisha"])
                    fee=minor_units(payload["fee_poisha"],zero_ok=True)
                    total=minor_units(payload["total_poisha"])
                    if total!=principal+fee:
                        reasons.append("QUOTE_NOT_BALANCED")
                except LabError:
                    reasons.append("QUOTE_AMOUNTS_INVALID")
                if payload.get("status") not in ("quoted","reviewed","expired","cancelled"):
                    reasons.append("QUOTE_STATE_INVALID")
        elif kind=="request":
            if payload.get("financial_posting") is not False or payload.get("handover_authorized") is not False:
                reasons.append("REQUEST_MONEY_CLAIM")
            if payload.get("status") not in ("reviewed","cancelled","expired"):
                reasons.append("REQUEST_STATE_INVALID")
        elif kind=="receipt":
            if payload.get("payment_proof") is not False or payload.get("bank_settlement_proof") is not False:
                reasons.append("RECEIPT_MISREPRESENTED")
            if not payload.get("watermark"):
                reasons.append("WATERMARK_MISSING")
        elif kind=="capabilities":
            if any(payload.get(x) is True for x in ("accepts_deposits","allows_cash_handover","can_issue_loans","bank_connected")):
                reasons.append("REAL_FEATURE_ASSERTED")
        else:
            reasons.append("UNKNOWN_CONTRACT")
        return ContractResult(not reasons,kind,tuple(sorted(set(reasons))))

    def assert_valid(self,kind:str,payload:dict[str,Any])->ContractResult:
        result=self.validate(kind,payload)
        if not result.valid:
            raise LabError("AUDIT_INTEGRITY")
        return result
