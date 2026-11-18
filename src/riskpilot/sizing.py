"""Position sizing.

Given an account equity, a per-trade risk budget and an entry/stop pair, this
module computes the largest whole number of quantity steps whose *actual* risk
never exceeds the budget. All math is :class:`~decimal.Decimal`; the function is
pure (no I/O, no clock, no randomness).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from fractions import Fraction

from riskpilot._decimal import exact_floor_div, to_decimal
from riskpilot.errors import ValidationError
from riskpilot.instruments import InstrumentSpec

__all__ = ["SizeResult", "SizeStatus", "size_position"]

_MAX_RISK_PCT = Decimal("5")


class SizeStatus(Enum):
    """Outcome category of a sizing request."""

    OK = "OK"
    BELOW_MIN_QTY = "BELOW_MIN_QTY"
    CAPPED_AT_MAX = "CAPPED_AT_MAX"


@dataclass(frozen=True, slots=True)
class SizeResult:
    """Result of :func:`size_position`.

    ``qty`` is always a whole multiple of ``spec.qty_step``. ``risk_actual`` is
    the risk implied by ``qty`` and is guaranteed to be ``<= risk_budget`` for
    every valid input.
    """

    qty: Decimal
    risk_budget: Decimal
    risk_per_unit: Decimal
    risk_actual: Decimal
    status: SizeStatus


def size_position(
    *,
    equity: Decimal,
    risk_pct: Decimal,
    entry: Decimal,
    stop: Decimal,
    spec: InstrumentSpec,
    commission_per_unit: Decimal = Decimal(0),
    slippage_ticks: int = 0,
) -> SizeResult:
    """Size a position so that its realised risk fits the risk budget.

    Parameters
    ----------
    equity:
        Account equity in account currency.
    risk_pct:
        Risk budget as a percentage of ``equity``; ``1`` means one percent.
        Must be in ``(0, 5]``.
    entry, stop:
        Entry and protective-stop prices. ``|entry - stop|`` must be a positive
        whole multiple of ``spec.tick_size``.
    spec:
        Contract mechanics for the symbol.
    commission_per_unit:
        Round-turn commission per unit in account currency.
    slippage_ticks:
        Slippage allowance expressed in whole ticks.

    Returns
    -------
    SizeResult
        The sized quantity and the associated risk figures.
    """
    equity_d = to_decimal(equity, "equity")
    risk_pct_d = to_decimal(risk_pct, "risk_pct")
    entry_d = to_decimal(entry, "entry")
    stop_d = to_decimal(stop, "stop")
    commission_d = to_decimal(commission_per_unit, "commission_per_unit")
    slippage = to_decimal(slippage_ticks, "slippage_ticks")

    if not isinstance(spec, InstrumentSpec):
        raise TypeError("spec must be an InstrumentSpec")

    if equity_d <= 0:
        raise ValidationError(f"equity must be positive, got {equity_d}")
    if risk_pct_d <= 0 or risk_pct_d > _MAX_RISK_PCT:
        raise ValidationError(f"risk_pct must be in (0, {_MAX_RISK_PCT}], got {risk_pct_d}")
    if commission_d < 0:
        raise ValidationError(f"commission_per_unit must be >= 0, got {commission_d}")
    if slippage < 0:
        raise ValidationError(f"slippage_ticks must be >= 0, got {slippage}")
    if slippage != slippage.to_integral_value():
        raise ValidationError(f"slippage_ticks must be a whole number, got {slippage}")

    distance = abs(entry_d - stop_d)
    if distance <= 0:
        raise ValidationError("entry and stop must differ")
    tick_ratio = Fraction(distance) / Fraction(spec.tick_size)
    if tick_ratio.denominator != 1:
        raise ValidationError(
            f"|entry - stop| ({distance}) must be a whole multiple of tick_size ({spec.tick_size})"
        )
    ticks = Decimal(tick_ratio.numerator)

    risk_per_unit = (ticks + slippage) * spec.tick_value + commission_d
    risk_budget = equity_d * risk_pct_d / Decimal(100)

    steps = exact_floor_div(risk_budget, risk_per_unit, spec.qty_step)
    qty = steps * spec.qty_step

    if qty < spec.min_qty:
        return SizeResult(
            qty=Decimal(0),
            risk_budget=risk_budget,
            risk_per_unit=risk_per_unit,
            risk_actual=Decimal(0),
            status=SizeStatus.BELOW_MIN_QTY,
        )

    status = SizeStatus.OK
    if qty > spec.max_qty:
        qty = spec.max_qty
        status = SizeStatus.CAPPED_AT_MAX

    risk_actual = qty * risk_per_unit
    return SizeResult(
        qty=qty,
        risk_budget=risk_budget,
        risk_per_unit=risk_per_unit,
        risk_actual=risk_actual,
        status=status,
    )
