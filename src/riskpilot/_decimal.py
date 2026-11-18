"""Internal numeric helpers shared by the core modules.

This module is a leaf: it imports nothing from :mod:`riskpilot` and holds no
mutable state. It exists so the "no binary floating point" rule (H3) is
enforced in exactly one place and can be audited quickly.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

__all__ = ["exact_floor_div", "to_decimal"]


def to_decimal(value: object, field: str) -> Decimal:
    """Coerce ``value`` to :class:`~decimal.Decimal`, rejecting floats.

    ``int`` and ``Decimal`` are accepted; ``bool`` is rejected even though it is
    an ``int`` subclass because ``True``/``False`` are never valid quantities.
    ``str`` is deliberately rejected here: string parsing is a boundary concern
    handled by :mod:`riskpilot.config` and :mod:`riskpilot.cli`.
    """
    if isinstance(value, (bool, float)):
        raise TypeError(f"{field} must be Decimal, not {type(value).__name__}")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    raise TypeError(f"{field} must be Decimal, not {type(value).__name__}")


def exact_floor_div(numerator: Decimal, *denominators: Decimal) -> Decimal:
    """Return ``floor(numerator / (d1 * d2 * ...))`` with no rounding error.

    Decimal division is context-rounded and can mis-round by one at the last
    place; converting to :class:`~fractions.Fraction` keeps the quotient exact,
    which is what guarantees ``risk_actual <= risk_budget`` for every input.
    """
    value = Fraction(numerator)
    for denominator in denominators:
        value /= Fraction(denominator)
    return Decimal(value.numerator // value.denominator)
