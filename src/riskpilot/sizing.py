"""Position sizing from a fixed-fractional risk budget.

All arithmetic is exact :class:`decimal.Decimal` arithmetic performed inside a
wide local context so that quotient flooring can never round *up*.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal, localcontext
from enum import Enum

from riskpilot._decimal import NumericInput, to_decimal, to_positive_decimal
from riskpilot.errors import ValidationError
from riskpilot.instruments import InstrumentSpec

#: Internal working precision. With inputs of at most 28 significant digits,
#: a quotient can never be closer than 10**-40 to an integer, so 60 digits is
#: enough for every floor() decision to be exact.
WORK_PRECISION = 60

#: Maximum allowed ``risk_pct`` (percent of equity risked per trade).
MAX_RISK_PCT = Decimal(5)

#: ``risk_pct`` must be strictly greater than this value.
MIN_RISK_PCT_EXCLUSIVE = Decimal(0)

_HUNDRED = Decimal(100)
_ZERO = Decimal(0)


class SizeStatus(Enum):
    """Outcome of a sizing request."""

    OK = "OK"
    BELOW_MIN_QTY = "BELOW_MIN_QTY"
    CAPPED_AT_MAX = "CAPPED_AT_MAX"


@dataclass(frozen=True)
class SizeResult:
    """Result of :func:`size_position`.

    Attributes
    ----------
    qty:
        Position size, always a multiple of the instrument's ``qty_step`` and
        never rounded up.
    risk_budget:
        ``equity * risk_pct / 100``, in account currency.
    risk_per_unit:
        Loss per one unit (lot/contract) if the stop is hit, including slippage
        and round-turn commission.
    risk_actual:
        ``qty * risk_per_unit``; always ``<= risk_budget``.
    status:
        :class:`SizeStatus` describing adjustments (zeroed or capped).

    """

    qty: Decimal
    risk_budget: Decimal
    risk_per_unit: Decimal
    risk_actual: Decimal
    status: SizeStatus


def _whole_multiple(value: Decimal, step: Decimal) -> bool:
    """Return True when ``value`` is an exact non-zero whole multiple of ``step``."""
    with localcontext() as ctx:
        ctx.prec = WORK_PRECISION
        ticks = value / step
    return ticks == ticks.to_integral_value()


def size_position(
    *,
    equity: NumericInput,
    risk_pct: NumericInput,
    entry: NumericInput,
    stop: NumericInput,
    spec: InstrumentSpec,
    commission_per_unit: NumericInput = 0,
    slippage_ticks: NumericInput = 0,
) -> SizeResult:
    """Size a position so that the realised risk never exceeds the budget.

    Parameters
    ----------
    equity:
        Account equity in account currency, ``> 0``.
    risk_pct:
        Risk per trade in percent, in the open-closed range ``(0, 5]``.
    entry, stop:
        Entry and stop prices; ``|entry - stop|`` must be a positive whole
        multiple of ``spec.tick_size``. Slippage is added separately.
    spec:
        Instrument definition.
    commission_per_unit:
        Round-turn commission per unit, ``>= 0``.
    slippage_ticks:
        Whole number of extra ticks of adverse slippage, ``>= 0``.

    Returns
    -------
    SizeResult

    Raises
    ------
    TypeError
        If any numeric argument is a ``float`` (or ``bool``).
    ValidationError
        If a value is outside its allowed range or the stop distance is not a
        whole multiple of the tick size.

    """
    equity_dec = to_positive_decimal(equity, field="equity")
    risk_pct_dec = to_decimal(risk_pct, field="risk_pct")
    entry_dec = to_decimal(entry, field="entry")
    stop_dec = to_decimal(stop, field="stop")
    commission_dec = to_decimal(commission_per_unit, field="commission_per_unit")
    slippage_dec = to_decimal(slippage_ticks, field="slippage_ticks")

    if not (MIN_RISK_PCT_EXCLUSIVE < risk_pct_dec <= MAX_RISK_PCT):
        msg = f"risk_pct must be in (0, 5] percent, got {risk_pct_dec}"
        raise ValidationError(msg)
    if commission_dec < _ZERO:
        msg = f"commission_per_unit must be >= 0, got {commission_dec}"
        raise ValidationError(msg)
    if slippage_dec < _ZERO:
        msg = f"slippage_ticks must be >= 0, got {slippage_dec}"
        raise ValidationError(msg)
    if slippage_dec != slippage_dec.to_integral_value():
        msg = f"slippage_ticks must be a whole number of ticks, got {slippage_dec}"
        raise ValidationError(msg)

    distance = abs(entry_dec - stop_dec)
    if distance == _ZERO:
        msg = "entry and stop must differ"
        raise ValidationError(msg)
    if not _whole_multiple(distance, spec.tick_size):
        msg = (
            f"|entry - stop| = {distance} is not a whole multiple of "
            f"tick_size {spec.tick_size} for {spec.symbol}"
        )
        raise ValidationError(msg)

    with localcontext() as ctx:
        ctx.prec = WORK_PRECISION
        ticks = distance / spec.tick_size
        risk_per_unit = (ticks + slippage_dec) * spec.tick_value + commission_dec
        risk_budget = equity_dec * risk_pct_dec / _HUNDRED
        raw_steps = risk_budget / (risk_per_unit * spec.qty_step)
        steps = int(raw_steps.to_integral_value(rounding=ROUND_FLOOR))
        qty = steps * spec.qty_step if steps > 0 else _ZERO

    status = SizeStatus.OK
    if qty < spec.min_qty:
        qty = _ZERO
        status = SizeStatus.BELOW_MIN_QTY
    elif qty > spec.max_qty:
        qty = spec.max_qty
        status = SizeStatus.CAPPED_AT_MAX

    with localcontext() as ctx:
        ctx.prec = WORK_PRECISION
        risk_actual = qty * risk_per_unit

    return SizeResult(
        qty=qty,
        risk_budget=risk_budget,
        risk_per_unit=risk_per_unit,
        risk_actual=risk_actual,
        status=status,
    )
