"""Tests for :class:`riskpilot.InstrumentSpec`."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from riskpilot.errors import ValidationError
from riskpilot.instruments import InstrumentSpec


def _spec(**overrides: object) -> InstrumentSpec:
    base: dict[str, object] = {
        "symbol": "X",
        "tick_size": Decimal("0.5"),
        "tick_value": Decimal("1"),
        "min_qty": Decimal("1"),
        "qty_step": Decimal("1"),
        "max_qty": Decimal("10"),
    }
    base.update(overrides)
    return InstrumentSpec(**base)


def test_valid_spec_is_frozen() -> None:
    spec = _spec()
    with pytest.raises(FrozenInstanceError):
        spec.symbol = "Y"


def test_ints_are_accepted_and_converted() -> None:
    spec = _spec(tick_value=5, min_qty=2, max_qty=10, qty_step=2)
    assert spec.tick_value == Decimal(5)
    assert spec.min_qty == Decimal(2)


@pytest.mark.parametrize("bad", [1.0, True, None, object()])
def test_float_and_bool_rejected(bad: object) -> None:
    with pytest.raises(TypeError):
        _spec(tick_size=bad)


def test_empty_symbol_rejected() -> None:
    with pytest.raises(ValidationError, match="symbol"):
        _spec(symbol="")


@pytest.mark.parametrize(
    "field",
    ["tick_size", "tick_value", "min_qty", "qty_step", "max_qty"],
)
def test_non_positive_rejected(field: str) -> None:
    with pytest.raises(ValidationError, match="positive"):
        _spec(**{field: Decimal(0)})


def test_max_below_min_rejected() -> None:
    with pytest.raises(ValidationError, match="max_qty"):
        _spec(min_qty=Decimal("5"), max_qty=Decimal("1"), qty_step=Decimal("1"))


def test_min_not_multiple_of_step_rejected() -> None:
    with pytest.raises(ValidationError, match="min_qty"):
        _spec(min_qty=Decimal("3"), qty_step=Decimal("2"), max_qty=Decimal("10"))


def test_max_not_multiple_of_step_rejected() -> None:
    with pytest.raises(ValidationError, match="max_qty"):
        _spec(min_qty=Decimal("2"), qty_step=Decimal("2"), max_qty=Decimal("9"))
