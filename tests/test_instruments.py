"""Tests for InstrumentSpec construction and validation."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from riskpilot import InstrumentError, InstrumentSpec, ValidationError

D = Decimal


def make(overrides: dict[str, object] | None = None) -> InstrumentSpec:
    """Build a valid EURUSD-like spec, overriding individual fields."""
    fields: dict[str, object] = {
        "symbol": "EURUSD",
        "tick_size": D("0.00001"),
        "tick_value": D("1.00"),
        "min_qty": D("0.01"),
        "qty_step": D("0.01"),
        "max_qty": D("100"),
    }
    fields.update(overrides or {})
    # A deliberate dynamic call: the tests drive individual fields by name.
    return build_spec(fields)


def build_spec(fields: dict[str, object]) -> InstrumentSpec:
    """Construct an InstrumentSpec from a mapping without static field checks."""
    constructor = cast(Callable[..., InstrumentSpec], InstrumentSpec)
    return constructor(**fields)


def test_spec_is_frozen() -> None:
    spec = make()
    with pytest.raises(AttributeError):
        spec.tick_size = D("1")


def test_spec_normalises_int_and_str_to_decimal() -> None:
    spec = make(
        {
            "tick_size": "0.25",
            "tick_value": 5,
            "min_qty": "1",
            "qty_step": "1",
            "max_qty": "50",
        }
    )
    assert isinstance(spec.tick_size, Decimal)
    assert spec.tick_value == D("5")
    assert spec.min_qty == D("1")


@pytest.mark.parametrize(
    "overrides",
    [
        {"tick_size": D("0")},
        {"tick_size": D("-0.01")},
        {"tick_value": D("0")},
        {"min_qty": D("0")},
        {"qty_step": D("-1")},
        {"max_qty": D("0")},
    ],
)
def test_spec_rejects_non_positive_fields(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        make(overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"min_qty": D("0.015")},
        {"max_qty": D("100.005")},
    ],
)
def test_spec_rejects_non_multiples_of_qty_step(overrides: dict[str, object]) -> None:
    with pytest.raises(InstrumentError):
        make(overrides)


def test_spec_rejects_max_below_min() -> None:
    with pytest.raises(InstrumentError, match="max_qty"):
        make({"min_qty": D("1"), "max_qty": D("0.5"), "qty_step": D("0.5")})


@pytest.mark.parametrize("symbol", ["", "   "])
def test_spec_rejects_blank_symbol(symbol: str) -> None:
    with pytest.raises(ValidationError, match="symbol"):
        make({"symbol": symbol})


def test_spec_rejects_float_tick_value() -> None:
    with pytest.raises(TypeError, match="float"):
        make({"tick_value": 1.0})


def test_spec_rejects_nan() -> None:
    with pytest.raises(ValidationError, match="finite"):
        make({"tick_size": D("NaN")})


def test_from_mapping_round_trips() -> None:
    spec = InstrumentSpec.from_mapping(
        "MNQ",
        {
            "tick_size": "0.25",
            "tick_value": "0.50",
            "min_qty": "1",
            "qty_step": "1",
            "max_qty": "200",
        },
    )
    assert spec == make(
        {
            "symbol": "MNQ",
            "tick_size": D("0.25"),
            "tick_value": D("0.50"),
            "min_qty": D("1"),
            "qty_step": D("1"),
            "max_qty": D("200"),
        }
    )


def test_examples_load_into_expected_specs(examples: Path) -> None:
    from riskpilot.config import load_instruments

    specs = load_instruments(examples / "instruments.toml")
    assert sorted(specs) == ["EURUSD", "MNQ", "NQ"]
    assert specs["NQ"].tick_value == D("5.00")
    assert specs["MNQ"].max_qty == D("200")
