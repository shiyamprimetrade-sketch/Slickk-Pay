"""Structured redaction before writing synthetic security or diagnostic evidence.

This is defense in depth, not a substitute for keeping secrets out of logs.
Only bounded diagnostic metadata should be logged; raw gateway IPNs, PINs and
credentials must never be collected in the first place.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from collections.abc import Mapping, Sequence
from .errors import InvalidValue

SENSITIVE_KEYS=frozenset({"password","passwd","store_passwd","store_password","authorization",
    "cookie","set-cookie","pin","otp","token","api_key","secret","client_secret",
    "database_url","card_no","card_number","pan","cvv","cvc","cus_phone",
    "cus_email","customer_phone","customer_email","private_key","bearer"})

_PATTERNS=(
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),"[REDACTED_EMAIL]"),
    (re.compile(r"\b(?:\+?8801|01)[3-9][0-9]{8}\b"),"[REDACTED_PHONE]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_\-+.=/]+"),"Bearer [REDACTED_TOKEN]"),
    (re.compile(r"(?i)(?:postgresql|postgres|redis)://[^\s]+"),"[REDACTED_CONNECTION_STRING]"),
    (re.compile(r"(?i)\b(?:store_passwd|client_secret|api_key|password)\s*[:=]\s*[^\s&,]+"),"[REDACTED_CREDENTIAL]"),
)


@dataclass(frozen=True)
class RedactionSummary:
    processed_keys: int
    replaced_values: int
    depth_limited: bool
    sanitized_digest: str
    simulation: bool = True


def _sensitive_name(raw: str) -> bool:
    return raw.lower().replace("-","_") in SENSITIVE_KEYS


def _redact_text(raw: str) -> tuple[str,bool]:
    value=raw
    for pattern,replacement in _PATTERNS:
        value=pattern.sub(replacement,value)
    if len(value)>2048:
        value=value[:2048]+"[TRUNCATED]"
    return value,value!=raw


def redact_structured(value: object, *, depth_limit: int=6,
                      max_nodes: int=1000) -> tuple[object,RedactionSummary]:
    if not 1<=depth_limit<=12 or not 1<=max_nodes<=10000:
        raise InvalidValue("Redaction bounds are invalid")
    counted=0
    replaced=0
    limited=False

    def walk(value: object,depth: int) -> object:
        nonlocal counted,replaced,limited
        counted+=1
        if counted>max_nodes or depth>depth_limit:
            limited=True
            replaced+=1
            return "[REDACTED_COMPLEX_DATA]"
        if isinstance(value,Mapping):
            result: dict[str,object]={}
            for key,item in value.items():
                if not isinstance(key,str):
                    replaced+=1
                    continue
                if _sensitive_name(key):
                    result[key]="[REDACTED_SECRET]"
                    replaced+=1
                    continue
                result[key]=walk(item,depth+1)
            return result
        if isinstance(value,(list,tuple)):
            return [walk(item,depth+1) for item in value[:max_nodes]]
        if isinstance(value,str):
            redacted,changed=_redact_text(value)
            if changed: replaced+=1
            return redacted
        if value is None or isinstance(value,(bool,int)):
            return value
        if isinstance(value,float):
            # Financial amounts are never rendered from floating point logs.
            replaced+=1
            return "[UNSAFE_FLOAT]"
        replaced+=1
        return "[REDACTED_UNKNOWN_TYPE]"

    output=walk(value,0)
    canonical=json.dumps(output,sort_keys=True,separators=(",",":"),ensure_ascii=True)
    if len(canonical)>512000:
        raise InvalidValue("Redacted diagnostic exceeds safe size")
    proof=sha256(canonical.encode()).hexdigest()
    return output,RedactionSummary(counted,replaced,limited,proof)


def safe_diagnostic(event: str,fields: Mapping[str,object]) -> dict[str,object]:
    if not re.fullmatch(r"[a-z][a-z_]{2,63}",event):
        raise InvalidValue("Invalid diagnostic event name")
    normalized,report=redact_structured(fields)
    return {"event":event,"fields":normalized,
            "redacted_values":report.replaced_values,
            "digest":report.sanitized_digest,"simulation":True}
