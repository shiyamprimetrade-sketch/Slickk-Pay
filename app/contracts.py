"""Financial capability discovery, strict form decoder, merchant order signatures."""
from __future__ import annotations
import hashlib, hmac, json, re, time
from urllib.parse import parse_qsl

class InvalidProviderForm(ValueError):
    """Provider form is malformed or ambiguous."""

_BAD_PERCENT = re.compile(r"%(?![a-fA-F0-9]{2})")

def parse_provider_form(raw: bytes) -> dict[str,str]:
    if not raw or len(raw)>16384:
        raise InvalidProviderForm("Invalid callback body")
    try:
        encoded=raw.decode("utf-8","strict")
        if _BAD_PERCENT.search(encoded):
            raise InvalidProviderForm("Malformed callback encoding")
        pairs=parse_qsl(encoded, keep_blank_values=True, strict_parsing=True,
                        encoding="utf-8", errors="strict", max_num_fields=128)
    except (ValueError,UnicodeError) as exc:
        raise InvalidProviderForm("Malformed callback form") from exc
    if not pairs:
        raise InvalidProviderForm("Empty callback")
    fields={}
    for key,value in pairs:
        if not key or len(key)>80 or key in fields or any(ord(ch)<32 for ch in key):
            raise InvalidProviderForm("Ambiguous callback fields")
        if "\x00" in value:
            raise InvalidProviderForm("Malformed callback field")
        fields[key]=value
    return fields

def financial_capabilities(*,configured:bool,environment:str)->dict:
    if environment not in ("staging","production"):
        raise ValueError("Unsupported environment")
    return {
        "schema_version":"1.0","environment":environment,"currency":"BDT",
        "merchant_checkout":{"implemented":True,"enabled":bool(configured),
            "provider":"SSLCOMMERZ","model":"hosted_redirect",
            "payment_methods":"provider_and_merchant_account_dependent",
            "verified_provider_callback_required":True},
        "wallet_stored_value":{"enabled":False},
        "microcredit":{"enabled":False},
        "cross_border_remittance":{"enabled":False},
        "currency_exchange":{"enabled":False},
        "bank_settlement_reporting":{"verified":False,
            "note":"Gateway validation and reported net are not bank settlement"}
    }

def sign_merchant_order(secret:str,*,timestamp:str,order_ref:str,
                        amount_poisha:int,product_name:str,product_category:str)->str:
    data=json.dumps(["slickk-order-v1",timestamp,order_ref,amount_poisha,
                     product_name,product_category],ensure_ascii=False,
                    separators=(",",":")).encode("utf-8")
    return "v1="+hmac.new(secret.encode("utf-8"),data,hashlib.sha256).hexdigest()

def merchant_order_signature_valid(secret:str,*,timestamp:str|None,
    signature:str|None,order_ref:str,amount_poisha:int,
    product_name:str,product_category:str,now:int|None=None)->bool:
    if not timestamp or not signature or not re.fullmatch(r"[0-9]{10,12}",timestamp):
        return False
    if not re.fullmatch(r"v1=[0-9a-f]{64}",signature):
        return False
    current=int(time.time()) if now is None else int(now)
    if abs(current-int(timestamp))>300:
        return False
    correct=sign_merchant_order(secret,timestamp=timestamp,order_ref=order_ref,
        amount_poisha=amount_poisha,product_name=product_name,product_category=product_category)
    return hmac.compare_digest(signature,correct)
