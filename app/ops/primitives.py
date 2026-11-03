"""Strict BDT value objects, identity normalization, and auditable result envelopes.

This module handles *evidence about payments* only. It cannot invoke a bank,
change a checkout status, manage stored value, or move any customer funds.
All amounts use exact integer poisha. Untrusted customer text never appears in
reconciliation artifacts unless explicitly whitelisted by the caller.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence


class EvidenceError(ValueError):
    """An untrusted or internally inconsistent item of financial evidence."""


class PolicyError(EvidenceError):
    """An operation is not permitted in this non-settling subsystem."""


class ConflictError(EvidenceError):
    """A supposedly unique external or internal identity has been reused."""


class NotFoundError(EvidenceError):
    """An evidence item or case was not found."""


class InvariantError(RuntimeError):
    """A logical or hash-chain invariant was violated."""


class Currency(str, Enum):
    BDT = "BDT"


REF_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:-]{0,95}\Z")
KEY_PATTERN = re.compile(r"[a-z][a-z0-9_]{1,63}\Z")
SHA256_PATTERN = re.compile(r"[a-f0-9]{64}\Z")


def reference(value: object, *, field_name: str = "reference", max_length: int = 96) -> str:
    """Validate an opaque reference without coercion, Unicode ambiguity, or whitespace."""
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise EvidenceError(f"Invalid {field_name}")
    if not REF_PATTERN.fullmatch(value):
        raise EvidenceError(f"Invalid {field_name}")
    return value


def safe_key(value: object, *, field_name: str = "key") -> str:
    if not isinstance(value, str) or not KEY_PATTERN.fullmatch(value):
        raise EvidenceError(f"Invalid {field_name}")
    return value


def ascii_label(value: object, *, field_name: str = "label", max_length: int = 120) -> str:
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise EvidenceError(f"Invalid {field_name}")
    if value != value.strip() or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise EvidenceError(f"Invalid {field_name}")
    return value


def positive_minor(value: object, *, maximum: int = 9_000_000_000_000) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= maximum:
        raise EvidenceError("Amount must be positive integer poisha within bounds")
    return value


def nonnegative_minor(value: object, *, maximum: int = 9_000_000_000_000) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise EvidenceError("Amount must be nonnegative integer poisha within bounds")
    return value


def minor_from_bdt(value: object, *, allow_zero: bool = False, allow_negative: bool = False) -> int:
    """Read *exactly* two decimals; reject floats, scientific notation, and rounding."""
    if not isinstance(value, (str, Decimal)) or isinstance(value, bool):
        raise EvidenceError("Use a decimal string for BDT, never floating-point")
    text = str(value)
    if not re.fullmatch(r"-?(?:0|[1-9]\d{0,10})(?:\.\d{1,2})?", text):
        raise EvidenceError("BDT must be a fixed decimal with at most two places")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise EvidenceError("Invalid BDT decimal") from exc
    if not amount.is_finite() or (amount < 0 and not allow_negative):
        raise EvidenceError("Negative or non-finite amount")
    result = int(amount * 100)
    if result == 0 and not allow_zero:
        raise EvidenceError("Zero amount is not permitted")
    if abs(result) > 9_000_000_000_000:
        raise EvidenceError("Amount is out of bounds")
    return result


def bdt_from_minor(minor: object) -> str:
    if isinstance(minor, bool) or not isinstance(minor, int) or abs(minor) > 9_000_000_000_000:
        raise EvidenceError("Invalid integer poisha")
    sign = "-" if minor < 0 else ""
    whole, fractional = divmod(abs(minor), 100)
    return f"{sign}{whole}.{fractional:02d}"


def bounded_ratio(numerator: int, denominator: int) -> Decimal:
    nonnegative_minor(numerator)
    positive_minor(denominator)
    if numerator > denominator:
        raise EvidenceError("Ratio exceeds one")
    return Decimal(numerator) / Decimal(denominator)


def timestamp(value: object, *, field_name: str = "timestamp") -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise EvidenceError(f"{field_name} must have a timezone")
    return value.astimezone(timezone.utc)


def parse_utc(value: object, *, field_name: str = "timestamp") -> datetime:
    if not isinstance(value, str) or len(value) > 35:
        raise EvidenceError(f"Invalid {field_name}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError(f"Invalid {field_name}") from exc
    return timestamp(parsed, field_name=field_name)


def utc_iso(value: datetime) -> str:
    return timestamp(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def days_between(earlier: datetime, later: datetime) -> int:
    first, second = timestamp(earlier), timestamp(later)
    if second < first:
        raise EvidenceError("End occurs before start")
    return (second.date() - first.date()).days


def sha256(data: bytes) -> str:
    if not isinstance(data, bytes):
        raise EvidenceError("Hash input must be bytes")
    return hashlib.sha256(data).hexdigest()


def canonical_json(data: Any) -> bytes:
    """Stable, UTF-8, float-free evidence encoding for hashes and signatures."""
    def checked(item: Any, depth: int = 0) -> Any:
        if depth > 15:
            raise EvidenceError("Evidence nesting exceeds limit")
        if item is None or isinstance(item, (str, bool, int)):
            if isinstance(item, str) and len(item) > 10_000:
                raise EvidenceError("Evidence string too large")
            if isinstance(item, int) and item.bit_length() > 128:
                raise EvidenceError("Evidence integer too large")
            return item
        if isinstance(item, (float, Decimal, complex)):
            raise EvidenceError("Non-canonical numeric value")
        if isinstance(item, (tuple, list)):
            if len(item) > 2_000:
                raise EvidenceError("Evidence array too large")
            return [checked(x, depth + 1) for x in item]
        if isinstance(item, dict):
            if len(item) > 1_000 or any(not isinstance(k, str) for k in item):
                raise EvidenceError("Evidence map keys or length invalid")
            return {k: checked(v, depth + 1) for k, v in item.items()}
        raise EvidenceError("Unsupported evidence data type")
    try:
        return json.dumps(checked(data), ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EvidenceError("Unable to canonically encode evidence") from exc


def evidence_hash(data: Any) -> str:
    return sha256(canonical_json(data))


def redacted_reference(value: object, *, show_last: int = 4) -> str:
    """Display a consistent but non-reversible digest prefix, never the original ID."""
    if not isinstance(value, str) or not 0 <= show_last <= 8:
        raise EvidenceError("Invalid reference for redaction")
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()[:16]


def require_keys(row: Mapping[str, Any], expected: Iterable[str]) -> None:
    if not isinstance(row, Mapping):
        raise EvidenceError("Expected evidence mapping")
    missing = sorted(set(expected) - row.keys())
    if missing:
        raise EvidenceError("Missing required fields: " + ", ".join(missing))


def safe_public_text(value: object, *, length: int = 100) -> str:
    """Restrict public case notes to fixed, non-PII status vocabulary."""
    if not isinstance(value, str) or len(value) > length:
        raise EvidenceError("Invalid public status")
    if not re.fullmatch(r"[a-z][a-z0-9_.:-]*", value):
        raise EvidenceError("Public status contains unsupported text")
    return value


@dataclass(frozen=True, slots=True)
class Money:
    minor: int
    currency: Currency = Currency.BDT

    def __post_init__(self) -> None:
        if isinstance(self.minor, bool) or not isinstance(self.minor, int):
            raise EvidenceError("Money requires exact minor units")
        if abs(self.minor) > 9_000_000_000_000 or self.currency != Currency.BDT:
            raise EvidenceError("Unsupported Money value")

    @classmethod
    def from_bdt(cls, value: str, *, allow_negative: bool = False) -> "Money":
        return cls(minor_from_bdt(value, allow_zero=True, allow_negative=allow_negative))

    @property
    def bdt(self) -> str:
        return bdt_from_minor(self.minor)

    def __add__(self, other: "Money") -> "Money":
        if not isinstance(other, Money) or self.currency != other.currency:
            return NotImplemented
        return Money(self.minor + other.minor)

    def __sub__(self, other: "Money") -> "Money":
        if not isinstance(other, Money) or self.currency != other.currency:
            return NotImplemented
        return Money(self.minor - other.minor)

    def __neg__(self) -> "Money":
        return Money(-self.minor)

    def as_dict(self) -> dict[str, str]:
        return {"amount": self.bdt, "currency": self.currency.value}


@dataclass(frozen=True, slots=True)
class EvidenceEnvelope:
    evidence_id: str
    kind: str
    created_at: datetime
    payload: Mapping[str, Any]
    source: str = "offline_review"
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        reference(self.evidence_id, field_name="evidence_id")
        safe_key(self.kind, field_name="kind")
        safe_key(self.source, field_name="source")
        timestamp(self.created_at)
        data = {"id": self.evidence_id, "kind": self.kind, "source": self.source,
                "timestamp": utc_iso(self.created_at), "payload": dict(self.payload)}
        object.__setattr__(self, "digest", evidence_hash(data))

    def verify(self) -> bool:
        data = {"id": self.evidence_id, "kind": self.kind, "source": self.source,
                "timestamp": utc_iso(self.created_at), "payload": dict(self.payload)}
        return self.digest == evidence_hash(data)

    def summary(self) -> dict[str, str]:
        return {"evidence_id": self.evidence_id, "kind": self.kind,
                "created_at": utc_iso(self.created_at), "digest": self.digest}


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    severity: str
    item_ref: str
    note: str = ""

    def __post_init__(self) -> None:
        safe_public_text(self.code)
        if self.severity not in {"info", "warning", "error", "critical"}:
            raise EvidenceError("Invalid finding severity")
        reference(self.item_ref)
        if self.note:
            safe_public_text(self.note)

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "severity": self.severity,
                "reference_digest": redacted_reference(self.item_ref), "note": self.note}


def ensure_unique_references(values: Sequence[str], *, field_name: str) -> None:
    seen: set[str] = set()
    for value in values:
        reference(value, field_name=field_name)
        if value in seen:
            raise ConflictError(f"Duplicate {field_name}")
        seen.add(value)
