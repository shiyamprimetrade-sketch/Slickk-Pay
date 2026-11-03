"""Deterministic agent cash/float planning without funding or external rails."""
from __future__ import annotations
from dataclasses import dataclass
from .errors import InvalidValue
from .money import minor, minor_to_bdt


@dataclass(frozen=True)
class DailyFlow:
    date: str
    expected_cashins_poisha: int
    expected_cashouts_poisha: int
    forecast_error_allowance_ppm: int = 0

    def __post_init__(self):
        from datetime import date
        try:
            parsed=date.fromisoformat(self.date)
        except (ValueError,TypeError) as exc:
            raise InvalidValue("Daily agent liquidity row needs ISO date") from exc
        if parsed.isoformat()!=self.date:
            raise InvalidValue("Invalid ISO date")
        minor(self.expected_cashins_poisha)
        minor(self.expected_cashouts_poisha)
        if self.expected_cashins_poisha<0 or self.expected_cashouts_poisha<0:
            raise InvalidValue("Negative cash flow not allowed")
        if type(self.forecast_error_allowance_ppm) is not int or not 0<=self.forecast_error_allowance_ppm<=1_000_000:
            raise InvalidValue("Invalid safety allowance")


@dataclass(frozen=True)
class AgentLiquidityPlan:
    starting_cash_poisha: int
    starting_float_poisha: int
    lowest_projected_cash_poisha: int
    lowest_projected_float_poisha: int
    required_additional_cash_poisha: int
    required_additional_float_poisha: int
    ending_cash_poisha: int
    ending_float_poisha: int
    forecast_days: int
    simulation: bool = True
    approved_credit_facility: bool = False

    def public(self) -> dict[str,str|int|bool]:
        return {"days":self.forecast_days,
                "starting_cash_bdt":minor_to_bdt(self.starting_cash_poisha),
                "starting_float_bdt":minor_to_bdt(self.starting_float_poisha),
                "additional_cash_required_bdt":minor_to_bdt(self.required_additional_cash_poisha),
                "additional_float_required_bdt":minor_to_bdt(self.required_additional_float_poisha),
                "ending_cash_bdt":minor_to_bdt(self.ending_cash_poisha),
                "ending_float_bdt":minor_to_bdt(self.ending_float_poisha),
                "simulation":True,"approved_credit_facility":False}


def forecast_agent_liquidity(*, starting_cash_poisha: int,
                             starting_float_poisha: int,
                             days: tuple[DailyFlow,...],
                             minimum_cash_buffer_poisha: int=0,
                             minimum_float_buffer_poisha: int=0) -> AgentLiquidityPlan:
    for v in (starting_cash_poisha,starting_float_poisha,minimum_cash_buffer_poisha,
              minimum_float_buffer_poisha):
        minor(v)
        if v<0:
            raise InvalidValue("Negative liquidity assumptions are invalid")
    if not 1<=len(days)<=90:
        raise InvalidValue("Bounded 90-day liquidity simulation only")
    if len({x.date for x in days})!=len(days) or tuple(sorted(x.date for x in days))!=tuple(x.date for x in days):
        raise InvalidValue("Liquidity days must be sorted and distinct")
    cash=starting_cash_poisha
    float_balance=starting_float_poisha
    low_cash=cash
    low_float=float_balance
    for day in days:
        cash+=day.expected_cashins_poisha-day.expected_cashouts_poisha
        float_balance+=day.expected_cashouts_poisha-day.expected_cashins_poisha
        low_cash=min(cash,low_cash)
        low_float=min(float_balance,low_float)
    required_cash=max(0,minimum_cash_buffer_poisha-low_cash)
    required_float=max(0,minimum_float_buffer_poisha-low_float)
    return AgentLiquidityPlan(starting_cash_poisha,starting_float_poisha,
                              low_cash,low_float,required_cash,required_float,
                              cash,float_balance,len(days))


def conservative_flow(base: DailyFlow) -> DailyFlow:
    """Apply explicit worst-case error to both directions conservatively."""
    from .money import ppm
    additional_cashout=ppm(base.expected_cashouts_poisha,base.forecast_error_allowance_ppm)
    additional_cashin=ppm(base.expected_cashins_poisha,base.forecast_error_allowance_ppm)
    # Cash-out stress requires more cash; cash-in stress uses more agent float.
    # Both upward adjustments may be impossible together, deliberately exposing
    # *separate* worst-case needs without claiming a true probabilistic model.
    return DailyFlow(base.date,base.expected_cashins_poisha+additional_cashin,
                     base.expected_cashouts_poisha+additional_cashout)


def stress_envelope(*, starting_cash_poisha: int,starting_float_poisha: int,
                    days: tuple[DailyFlow,...],min_cash_buffer: int=0,
                    min_float_buffer: int=0) -> dict[str,AgentLiquidityPlan|bool]:
    baseline=forecast_agent_liquidity(starting_cash_poisha=starting_cash_poisha,
        starting_float_poisha=starting_float_poisha,days=days,
        minimum_cash_buffer_poisha=min_cash_buffer,
        minimum_float_buffer_poisha=min_float_buffer)
    stressed=forecast_agent_liquidity(starting_cash_poisha=starting_cash_poisha,
        starting_float_poisha=starting_float_poisha,days=tuple(conservative_flow(x) for x in days),
        minimum_cash_buffer_poisha=min_cash_buffer,
        minimum_float_buffer_poisha=min_float_buffer)
    return {"baseline":baseline,"stressed_assumptions":stressed,"simulation":True}
