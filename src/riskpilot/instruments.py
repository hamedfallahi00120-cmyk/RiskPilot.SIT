"""Instrument specifications: tick size, tick value and quantity rules."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from riskpilot._decimal import to_decimal, to_positive_decimal
from riskpilot.errors import InstrumentError, ValidationError


def _is_multiple(value: Decimal, step: Decimal) -> bool:
    """Return True when ``value`` is an exact whole multiple of ``step``."""
    return value % step == 0


@dataclass(frozen=True)
class InstrumentSpec:
    """Tradable instrument definition.

    Parameters
    ----------
    symbol:
        Broker/exchange symbol, non-empty.
    tick_size:
        Smallest price increment, ``> 0``.
    tick_value:
        Account-currency value of one tick for **one unit** (1 lot / 1 contract).
    min_qty:
        Smallest tradeable quantity, ``> 0`` and an exact multiple of ``qty_step``.
    qty_step:
        Quantity increment, ``> 0``.
    max_qty:
        Largest tradeable quantity, ``>= min_qty`` and an exact multiple of
        ``qty_step``.

    Raises
    ------
    TypeError
        If a numeric field is given as ``float`` (or ``bool``).
    ValidationError
        If a rule above is violated.

    """

    symbol: str
    tick_size: Decimal
    tick_value: Decimal
    min_qty: Decimal
    qty_step: Decimal
    max_qty: Decimal

    def __post_init__(self) -> None:
        """Validate and normalise the fields into :class:`~decimal.Decimal`."""
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            msg = "symbol must be a non-empty string"
            raise ValidationError(msg)
        object.__setattr__(
            self, "tick_size", to_positive_decimal(self.tick_size, field="tick_size")
        )
        object.__setattr__(
            self, "tick_value", to_positive_decimal(self.tick_value, field="tick_value")
        )
        object.__setattr__(self, "min_qty", to_positive_decimal(self.min_qty, field="min_qty"))
        object.__setattr__(self, "qty_step", to_positive_decimal(self.qty_step, field="qty_step"))
        object.__setattr__(self, "max_qty", to_positive_decimal(self.max_qty, field="max_qty"))
        if not _is_multiple(self.min_qty, self.qty_step):
            msg = f"min_qty {self.min_qty} is not a multiple of qty_step {self.qty_step}"
            raise InstrumentError(msg)
        if not _is_multiple(self.max_qty, self.qty_step):
            msg = f"max_qty {self.max_qty} is not a multiple of qty_step {self.qty_step}"
            raise InstrumentError(msg)
        if self.max_qty < self.min_qty:
            msg = f"max_qty {self.max_qty} must be >= min_qty {self.min_qty}"
            raise InstrumentError(msg)

    @classmethod
    def from_mapping(cls, symbol: str, data: dict[str, Any]) -> InstrumentSpec:
        """Build a spec from a mapping of string/Decimal values (used by config)."""
        return cls(
            symbol=symbol,
            tick_size=to_decimal(data["tick_size"], field="tick_size"),
            tick_value=to_decimal(data["tick_value"], field="tick_value"),
            min_qty=to_decimal(data["min_qty"], field="min_qty"),
            qty_step=to_decimal(data["qty_step"], field="qty_step"),
            max_qty=to_decimal(data["max_qty"], field="max_qty"),
        )
