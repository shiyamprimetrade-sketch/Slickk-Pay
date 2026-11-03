"""Versioned Bangladesh-taka pilot tariff calculations for fictitious transactions.

All public figures in this module are business *hypotheses*, not published market
prices, approved financial charges or a promise of future operating margin.  The
module works in integer poisha; no floating-point input or result is accepted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Mapping


class PriceError(ValueError):
    """Raised when a pilot price could not be calculated unambiguously."""


def bdt_to_poisha(raw: str | int | Decimal) -> int:
    """Parse literal decimal BDT, rejecting scientific notation and floats."""
    if isinstance(raw, bool) or isinstance(raw, float):
        raise PriceError("BDT amount must be an exact decimal string")
    text = str(raw).strip()
    if not text or "e" in text.lower() or "," in text:
        raise PriceError("BDT amount must use plain decimal notation")
    try:
        dec = Decimal(text)
    except InvalidOperation as exc:
        raise PriceError("Invalid BDT amount") from exc
    if not dec.is_finite() or dec < 0 or dec.as_tuple().exponent < -2:
        raise PriceError("BDT amounts must be positive with at most two decimals")
    units = dec * 100
    if units != units.to_integral_value():
        raise PriceError("Unsupported sub-poisha amount")
    if units > 10**14:
        raise PriceError("BDT amount exceeds sandbox bounds")
    return int(units)


def poisha_to_bdt(minor: int) -> str:
    if isinstance(minor, bool) or not isinstance(minor, int):
        raise PriceError("Poisha must be an integer")
    sign = "-" if minor < 0 else ""
    magnitude = abs(minor)
    return f"{sign}{magnitude // 100}.{magnitude % 100:02d}"


def _ppm(amount: int, parts_per_million: int) -> int:
    """Half-up rounding in poisha: avoids hidden fractional minor-unit debt."""
    if amount < 0 or parts_per_million < 0:
        raise PriceError("Negative amount or tariff")
    q, rem = divmod(amount * parts_per_million, 1_000_000)
    return q + (1 if rem * 2 >= 1_000_000 else 0)


@dataclass(frozen=True)
class Tariff:
    name: str
    customer_ppm: int = 0
    commission_ppm: int = 0
    merchant_ppm: int = 0
    minimum_fee: int = 0
    maximum_fee: int | None = None
    tax_ppm: int = 0
    min_principal: int = 100
    max_principal: int = 5_000_000
    exemption_threshold: int = 0

    def __post_init__(self) -> None:
        if not self.name or any(ch.isspace() for ch in self.name):
            raise PriceError("Invalid tariff name")
        for key in ("customer_ppm", "commission_ppm", "merchant_ppm", "minimum_fee", "tax_ppm",
                    "min_principal", "max_principal", "exemption_threshold"):
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise PriceError(f"Invalid {key}")
        if self.max_principal < self.min_principal or self.customer_ppm > 1_000_000:
            raise PriceError("Invalid tariff limits")
        if self.maximum_fee is not None and self.maximum_fee < self.minimum_fee:
            raise PriceError("Maximum fee cannot be smaller than minimum")


@dataclass(frozen=True)
class Quote:
    tariff_version: str
    transaction_type: str
    principal: int
    customer_fee: int
    tax: int
    customer_total_debit: int
    merchant_fee: int
    agent_commission: int
    platform_gross_revenue: int
    platform_cost_before_overheads: int

    def public(self) -> dict[str, str]:
        return {
            "tariff_version": self.tariff_version,
            "transaction_type": self.transaction_type,
            "principal_bdt": poisha_to_bdt(self.principal),
            "customer_fee_bdt": poisha_to_bdt(self.customer_fee),
            "tax_bdt": poisha_to_bdt(self.tax),
            "total_customer_debit_bdt": poisha_to_bdt(self.customer_total_debit),
            "agent_commission_bdt": poisha_to_bdt(self.agent_commission),
            "merchant_fee_bdt": poisha_to_bdt(self.merchant_fee),
        }


@dataclass(frozen=True)
class PilotPricing:
    version: str
    tariffs: Mapping[str, Tariff]
    effective_utc: str
    approved_for_production: bool = False
    notes: str = "unapproved financial simulation"
    custom_exemptions: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.version or self.approved_for_production:
            raise PriceError("Sandbox tariff cannot be published as approved")
        datetime.fromisoformat(self.effective_utc.replace("Z", "+00:00"))

    def quote(self, operation: str, amount: int, *, exemption: str | None = None) -> Quote:
        if operation not in self.tariffs:
            raise PriceError("Unknown pilot transaction type")
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise PriceError("Principal must be integer poisha")
        rule = self.tariffs[operation]
        if amount < rule.min_principal or amount > rule.max_principal:
            raise PriceError("Amount outside pilot limit")
        exempt = exemption is not None and exemption in self.custom_exemptions
        fee = _ppm(amount, rule.customer_ppm)
        if exempt or (rule.exemption_threshold and amount <= rule.exemption_threshold):
            fee = 0
        else:
            fee = max(rule.minimum_fee, fee)
            if rule.maximum_fee is not None:
                fee = min(fee, rule.maximum_fee)
        tax = _ppm(fee, rule.tax_ppm)
        commission = _ppm(amount, rule.commission_ppm)
        merchant_fee = _ppm(amount, rule.merchant_ppm)
        revenue = fee + merchant_fee
        return Quote(self.version, operation, amount, fee, tax, amount + fee + tax,
                     merchant_fee, commission, revenue, commission)

    def earnings_scenario(self, *, cashin_count: int, cashout_count: int,
                          mean_cashin_poisha: int, mean_cashout_poisha: int,
                          overhead_poisha: int = 0) -> dict[str, int | str]:
        if min(cashin_count, cashout_count, mean_cashin_poisha, mean_cashout_poisha,
               overhead_poisha) < 0:
            raise PriceError("Scenario inputs must be nonnegative")
        cin = self.quote("cash_in", mean_cashin_poisha) if cashin_count else None
        cout = self.quote("cash_out", mean_cashout_poisha) if cashout_count else None
        income = (cin.agent_commission * cashin_count if cin else 0) + (
            cout.agent_commission * cashout_count if cout else 0)
        revenue = (cin.platform_gross_revenue * cashin_count if cin else 0) + (
            cout.platform_gross_revenue * cashout_count if cout else 0)
        return {
            "tariff_version": self.version,
            "agent_commissions_poisha": income,
            "customer_fees_poisha": revenue,
            "overheads_poisha": overhead_poisha,
            "contribution_after_commission_and_overheads_poisha": revenue - income - overhead_poisha,
            "fictional_scenario": "true",
        }


def initial_pilot() -> PilotPricing:
    """Business hypotheses supplied by project owner, *not* verified competitor fees."""
    rules = {
        "customer_transfer": Tariff("customer_transfer"),
        "cash_in": Tariff("cash_in", commission_ppm=1500),
        "cash_out": Tariff("cash_out", customer_ppm=10990, commission_ppm=5500),
        "merchant_payment": Tariff("merchant_payment", merchant_ppm=4500),
        "balance_inquiry": Tariff("balance_inquiry", min_principal=0),
        "receipt": Tariff("receipt", min_principal=0),
    }
    return PilotPricing("pilot-2026-11-03-v1", rules, "2026-11-03T00:00:00Z")
