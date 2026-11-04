"""Strict synthetic identifier, money, clock, and privacy validation.

All identifiers use sim_ namespaces to prevent real customer identifiers from
entering demonstration tables. Financial amounts are always integer poisha.
"""
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import re
import unicodedata
from typing import Any
from .errors import LabError, require

SIM_ID = re.compile(r"sim_[a-z][a-z0-9_:-]{3,80}\Z")
REF = re.compile(r"[a-z][a-z0-9_:-]{7,95}\Z")
DEVICE = re.compile(r"sim_device_[a-z0-9_-]{5,64}\Z")
SAFE_TEXT = re.compile(r"[A-Za-z0-9 .,:'()\-_/]+\Z")
MAX_POISHA = 50_000_000
BDT_QUANT = Decimal("0.01")


def synthetic_id(value: str, *, kind: str = "synthetic identifier") -> str:
    require(isinstance(value, str) and bool(SIM_ID.fullmatch(value)), "INVALID_REFERENCE")
    return value


def event_ref(value: str) -> str:
    require(isinstance(value, str) and bool(REF.fullmatch(value)), "INVALID_REFERENCE")
    return value


def device_ref(value: str) -> str:
    require(isinstance(value, str) and bool(DEVICE.fullmatch(value)), "INVALID_REFERENCE")
    return value


def minor_units(value: int, *, zero_ok: bool = False) -> int:
    require(type(value) is int, "INVALID_AMOUNT")
    require((value >= 0 if zero_ok else value > 0) and value <= MAX_POISHA, "INVALID_AMOUNT")
    return value


def bdt_string(value: str) -> int:
    require(isinstance(value, str) and bool(re.fullmatch(r"(?:0|[1-9][0-9]{0,6})(?:\.[0-9]{1,2})?", value)), "INVALID_AMOUNT")
    try:
        amount = Decimal(value)
        require(amount.is_finite() and amount == amount.quantize(BDT_QUANT), "INVALID_AMOUNT")
        return minor_units(int(amount * 100))
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise LabError("INVALID_AMOUNT") from exc


def display_bdt(amount_poisha: int) -> str:
    minor_units(amount_poisha, zero_ok=True)
    return f"{amount_poisha // 100}.{amount_poisha % 100:02d}"


def round_half_up(numerator: int, denominator: int) -> int:
    require(type(numerator) is int and numerator >= 0 and type(denominator) is int and denominator > 0, "INVALID_AMOUNT")
    return (numerator * 2 + denominator) // (2 * denominator)


def ppm_fee(principal: int, rate_ppm: int) -> int:
    minor_units(principal)
    require(type(rate_ppm) is int and 0 <= rate_ppm <= 1_000_000, "INVALID_AMOUNT")
    return round_half_up(principal * rate_ppm, 1_000_000)


def normalize_locale(value: str | None) -> str:
    return "bn" if value == "bn" else "en"


def safe_note(value: str, *, max_length: int = 120) -> str:
    require(isinstance(value, str) and len(value) <= max_length, "INVALID_INPUT")
    candidate = unicodedata.normalize("NFKC", value).strip()
    require(not any(unicodedata.category(ch).startswith("C") for ch in candidate), "INVALID_INPUT")
    require(not any(x in candidate.lower() for x in ("password", "token", "pin=", "otp=")), "INVALID_INPUT")
    return candidate


def sanitized_label(value: str, *, max_length: int = 60) -> str:
    require(isinstance(value, str) and 1 <= len(value) <= max_length, "INVALID_INPUT")
    candidate = value.strip()
    require(bool(SAFE_TEXT.fullmatch(candidate)), "INVALID_INPUT")
    return candidate


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical(value: Any) -> bytes:
    """Stable JSON for internal integrity proofs; rejects non-deterministic floats."""
    def check(item: Any) -> None:
        if item is None or type(item) in (str, int, bool):
            return
        if isinstance(item, list) or isinstance(item, tuple):
            for child in item:
                check(child)
            return
        if isinstance(item, dict):
            require(all(type(k) is str for k in item), "INVALID_INPUT")
            for child in item.values():
                check(child)
            return
        raise LabError("INVALID_INPUT")
    check(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def utc_timestamp(moment: datetime | None = None) -> int:
    value = moment or datetime.now(timezone.utc)
    require(value.tzinfo is not None, "INVALID_INPUT")
    return int(value.astimezone(timezone.utc).timestamp())


def mask_actor(actor_id: str) -> str:
    synthetic_id(actor_id)
    return actor_id[:7] + "…" + actor_id[-4:]


def mask_text(value: str, *, visible: int = 3) -> str:
    if not isinstance(value, str) or not value:
        return "***"
    return "*" * max(3, len(value) - visible) + value[-visible:]


def forbid_real_identity_fields(input_map: dict[str, object]) -> None:
    blocked = {"nid", "national_id", "passport", "bank_account", "card_number", "real_phone", "dob", "ssn"}
    require(not (set(input_map) & blocked), "INVALID_INPUT")
