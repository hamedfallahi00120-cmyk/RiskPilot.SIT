"""Strict Decimal coercion shared by the pure core modules.

Every public function that accepts money, price or quantity goes through
:func:`to_decimal`, which rejects ``float``, ``bool`` and non-numeric values.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TypeAlias

from riskpilot.errors import ValidationError

#: Types accepted wherever money, price or quantity is expected. ``float`` and
#: ``bool`` are deliberately excluded and raise :class:`TypeError` at runtime.
NumericInput: TypeAlias = Decimal | int | str


def to_decimal(value: object, *, field: str) -> Decimal:
    """Coerce ``value`` to :class:`decimal.Decimal`, refusing floating point.

    Parameters
    ----------
    value:
        A ``Decimal``, ``int`` or numeric ``str``. ``float`` and ``bool`` are
        rejected on purpose so no binary floating point enters the maths.
    field:
        Human readable field name used in error messages.

    Raises
    ------
    TypeError
        If ``value`` is a ``float`` or ``bool``.
    ValidationError
        If ``value`` is not a finite, valid decimal number.

    """
    if isinstance(value, bool):
        msg = f"{field} must be a number, not bool"
        raise TypeError(msg)
    if isinstance(value, float):
        msg = f"{field} must be a Decimal (or int/str), got float; floats are never accepted"
        raise TypeError(msg)
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, str):
        try:
            result = Decimal(value)
        except InvalidOperation as exc:
            msg = f"{field} is not a valid decimal number: {value!r}"
            raise ValidationError(msg) from exc
    else:
        msg = f"{field} must be Decimal, int or str, got {type(value).__name__}"
        raise TypeError(msg)
    if not result.is_finite():
        msg = f"{field} must be finite, got {result}"
        raise ValidationError(msg)
    return result


def to_positive_decimal(value: object, *, field: str) -> Decimal:
    """Like :func:`to_decimal` but additionally require a strictly positive value."""
    result = to_decimal(value, field=field)
    if result <= 0:
        msg = f"{field} must be > 0, got {result}"
        raise ValidationError(msg)
    return result
