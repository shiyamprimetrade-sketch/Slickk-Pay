"""Exact BDT minor-unit arithmetic; never accept binary floats for money."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from .errors import InvalidValue

_LIMIT = 10**14
_LITERAL = re.compile(r"^(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,2})?$")


def minor(value: int, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or abs(value) > _LIMIT:
        raise InvalidValue("Value must be bounded integer poisha")
    if positive and value <= 0:
        raise InvalidValue("Poisha must be positive")
    return value


def bdt_to_minor(raw: str) -> int:
    if not isinstance(raw, str) or not _LITERAL.fullmatch(raw):
        raise InvalidValue("Use an exact non-negative BDT literal with at most 2 decimals")
    try:
        result = Decimal(raw) * 100
    except InvalidOperation as exc:
        raise InvalidValue("Invalid BDT") from exc
    number = int(result)
    if number > _LIMIT:
        raise InvalidValue("Amount exceeds test limit")
    return number


def minor_to_bdt(value: int) -> str:
    minor(value)
    amount = abs(value)
    return f"{'-' if value < 0 else ''}{amount // 100}.{amount % 100:02d}"


def ppm(amount: int, millionths: int) -> int:
    minor(amount)
    if amount < 0 or not isinstance(millionths, int) or isinstance(millionths, bool) or not 0 <= millionths <= 1_000_000:
        raise InvalidValue("Invalid rate")
    whole, remainder = divmod(amount * millionths, 1_000_000)
    return whole + int(remainder * 2 >= 1_000_000)


@dataclass(frozen=True, slots=True)
class Money:
    poisha: int
    currency: str = "BDT"

    def __post_init__(self) -> None:
        minor(self.poisha)
        if self.currency != "BDT":
            raise InvalidValue("Sandbox is BDT-only")

    @classmethod
    def parse(cls, amount: str) -> "Money":
        return cls(bdt_to_minor(amount))

    def __add__(self, other: "Money") -> "Money":
        self._match(other)
        return Money(minor(self.poisha + other.poisha))

    def __sub__(self, other: "Money") -> "Money":
        self._match(other)
        return Money(minor(self.poisha - other.poisha))

    def __neg__(self) -> "Money":
        return Money(-self.poisha)

    def _match(self, other: "Money") -> None:
        if not isinstance(other, Money) or other.currency != self.currency:
            raise InvalidValue("Currency mismatch")

    def public(self) -> dict[str, str]:
        return {"amount": minor_to_bdt(self.poisha), "currency": self.currency,
                "simulation": "true"}


@dataclass(frozen=True, slots=True)
class Rate:
    name: str
    parts_per_million: int
    minimum_poisha: int = 0
    maximum_poisha: int | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z_]{1,63}", self.name):
            raise InvalidValue("Invalid tariff name")
        if isinstance(self.parts_per_million, bool) or not isinstance(self.parts_per_million, int) or not 0 <= self.parts_per_million <= 1_000_000:
            raise InvalidValue("Invalid tariff")
        minor(self.minimum_poisha)
        if self.minimum_poisha < 0:
            raise InvalidValue("Negative minimum")
        if self.maximum_poisha is not None:
            minor(self.maximum_poisha)
            if self.maximum_poisha < self.minimum_poisha:
                raise InvalidValue("Maximum below minimum")

    def fee(self, amount: int) -> int:
        minor(amount, positive=True)
        value = max(self.minimum_poisha, ppm(amount, self.parts_per_million))
        return min(value, self.maximum_poisha) if self.maximum_poisha is not None else value


def ratio(numerator: int, denominator: int, places: int = 4) -> str:
    minor(numerator)
    minor(denominator, positive=True)
    if not 0 <= places <= 8:
        raise InvalidValue("Invalid precision")
    quantum = Decimal(1).scaleb(-places)
    return str((Decimal(numerator) / Decimal(denominator)).quantize(quantum, rounding=ROUND_HALF_UP))
