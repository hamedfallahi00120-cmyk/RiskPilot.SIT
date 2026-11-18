"""Instrument specifications.

An :class:`InstrumentSpec` describes the contract mechanics needed to convert a
price distance into an account-currency risk. It is a frozen, self-validating
dataclass; construction rejects floats and any inconsistent field combination.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from riskpilot.errors import ValidationError

__all__ = ["InstrumentSpec"]


def _as_decimal(value: object, field: str) -> Decimal:
    """Coerce ``value`` to Decimal, rejecting floats explicitly.

    The whole library forbids binary floating point for money, price and
    quantity math; accepting a float here would silently import rounding error.
    """
    if isinstance(value, (bool, float)):
        raise TypeError(f"{field} must be Decimal, not {type(value).__name__}")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        return Decimal(value)
    raise TypeError(f"{field} must be Decimal, not {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    """Contract mechanics for one tradable symbol.

    ``tick_value`` is the account-currency value of a single tick for one unit
    (one lot for forex, one contract for futures).
    """

    symbol: str
    tick_size: Decimal
    tick_value: Decimal
    min_qty: Decimal
    qty_step: Decimal
    max_qty: Decimal

    def __post_init__(self) -> None:
        symbol = self.symbol
        if not isinstance(symbol, str) or not symbol:
            raise ValidationError("symbol must be a non-empty string")

        tick_size = _as_decimal(self.tick_size, "tick_size")
        tick_value = _as_decimal(self.tick_value, "tick_value")
        min_qty = _as_decimal(self.min_qty, "min_qty")
        qty_step = _as_decimal(self.qty_step, "qty_step")
        max_qty = _as_decimal(self.max_qty, "max_qty")

        for name, value in (
            ("tick_size", tick_size),
            ("tick_value", tick_value),
            ("min_qty", min_qty),
            ("qty_step", qty_step),
            ("max_qty", max_qty),
        ):
            if value <= 0:
                raise ValidationError(f"{name} must be positive, got {value}")

        if max_qty < min_qty:
            raise ValidationError(f"max_qty ({max_qty}) must be >= min_qty ({min_qty})")
        if min_qty % qty_step != 0:
            raise ValidationError(
                f"min_qty ({min_qty}) must be a multiple of qty_step ({qty_step})"
            )
        if max_qty % qty_step != 0:
            raise ValidationError(
                f"max_qty ({max_qty}) must be a multiple of qty_step ({qty_step})"
            )

        object.__setattr__(self, "tick_size", tick_size)
        object.__setattr__(self, "tick_value", tick_value)
        object.__setattr__(self, "min_qty", min_qty)
        object.__setattr__(self, "qty_step", qty_step)
        object.__setattr__(self, "max_qty", max_qty)
