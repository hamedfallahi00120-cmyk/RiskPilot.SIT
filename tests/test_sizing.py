"""Tests for position sizing.

The engine must never round a quantity up and must reject binary floats
everywhere, so most tests assert an exact Decimal result or an exact exception.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import cast

import pytest

from riskpilot import InstrumentSpec, SizeResult, SizeStatus, ValidationError, size_position

D = Decimal


def test_acceptance_eurusd_basic(eurusd: InstrumentSpec) -> None:
    result = size_position(
        equity=D("10000"), risk_pct=D("1"), entry=D("1.10000"), stop=D("1.09800"), spec=eurusd
    )
    assert result.qty == D("0.50")
    assert result.risk_actual == D("100.00")
    assert result.risk_budget == D("100")
    assert result.risk_per_unit == D("200.00")
    assert result.status is SizeStatus.OK


def test_acceptance_eurusd_with_commission(eurusd: InstrumentSpec) -> None:
    result = size_position(
        equity=D("10000"),
        risk_pct=D("1"),
        entry=D("1.10000"),
        stop=D("1.09800"),
        spec=eurusd,
        commission_per_unit=D("7"),
    )
    assert result.qty == D("0.48")
    assert result.risk_per_unit == D("207.00")
    assert result.risk_actual <= result.risk_budget


def test_acceptance_nq(nq: InstrumentSpec) -> None:
    result = size_position(
        equity=D("50000"),
        risk_pct=D("0.5"),
        entry=D("20000.00"),
        stop=D("19990.00"),
        spec=nq,
    )
    assert result.qty == D("1")
    assert result.risk_actual == D("200.00")
    assert result.status is SizeStatus.OK


def test_acceptance_mnq(mnq: InstrumentSpec) -> None:
    result = size_position(
        equity=D("50000"),
        risk_pct=D("0.5"),
        entry=D("20000.00"),
        stop=D("19990.00"),
        spec=mnq,
    )
    assert result.qty == D("12")
    assert result.risk_actual == D("240.00")


def test_acceptance_below_min_qty(nq: InstrumentSpec) -> None:
    result = size_position(
        equity=D("1000"), risk_pct=D("0.5"), entry=D("20000.00"), stop=D("19990.00"), spec=nq
    )
    assert result.qty == D("0")
    assert result.status is SizeStatus.BELOW_MIN_QTY
    assert result.risk_actual == D("0")


def test_capped_at_max(nq: InstrumentSpec) -> None:
    result = size_position(
        equity=D("10000000"), risk_pct=D("1"), entry=D("20000.00"), stop=D("19990.00"), spec=nq
    )
    assert result.status is SizeStatus.CAPPED_AT_MAX
    assert result.qty == nq.max_qty
    assert result.risk_actual <= result.risk_budget


def test_short_side_uses_absolute_distance(eurusd: InstrumentSpec) -> None:
    short = size_position(
        equity=D("10000"), risk_pct=D("1"), entry=D("1.09800"), stop=D("1.10000"), spec=eurusd
    )
    assert short.qty == D("0.50")


def test_slippage_ticks_increase_risk_per_unit(eurusd: InstrumentSpec) -> None:
    result = size_position(
        equity=D("10000"),
        risk_pct=D("1"),
        entry=D("1.10000"),
        stop=D("1.09800"),
        spec=eurusd,
        slippage_ticks=D("2"),
    )
    assert result.risk_per_unit == D("202.00")
    assert result.qty == D("0.49")
    assert result.risk_actual <= result.risk_budget


@pytest.mark.parametrize("field", ["equity", "risk_pct", "entry", "stop", "commission_per_unit"])
def test_float_arguments_raise_type_error(field: str, eurusd: InstrumentSpec) -> None:
    kwargs: dict[str, object] = {
        "equity": D("10000"),
        "risk_pct": D("1"),
        "entry": D("1.10000"),
        "stop": D("1.09800"),
        "spec": eurusd,
    }
    kwargs[field] = 1.5
    with pytest.raises(TypeError, match="float"):
        call_sizing(kwargs)


def test_float_slippage_raises_type_error(eurusd: InstrumentSpec) -> None:
    with pytest.raises(TypeError, match="float"):
        size_position(
            equity=D("10000"),
            risk_pct=D("1"),
            entry=D("1.10000"),
            stop=D("1.09800"),
            spec=eurusd,
            slippage_ticks=1.0,
        )


def test_bool_equity_raises_type_error(eurusd: InstrumentSpec) -> None:
    with pytest.raises(TypeError, match="bool"):
        size_position(equity=True, risk_pct=D("1"), entry=D("1.1"), stop=D("1.09"), spec=eurusd)


@pytest.mark.parametrize("risk_pct", [D("0"), D("-1"), D("5.01"), D("10")])
def test_risk_pct_out_of_range(risk_pct: Decimal, eurusd: InstrumentSpec) -> None:
    with pytest.raises(ValidationError, match=r"risk_pct must be in \(0, 5\]"):
        size_position(
            equity=D("10000"), risk_pct=risk_pct, entry=D("1.10000"), stop=D("1.09800"), spec=eurusd
        )


def test_risk_pct_at_upper_bound_is_allowed(eurusd: InstrumentSpec) -> None:
    result = size_position(
        equity=D("10000"), risk_pct=D("5"), entry=D("1.10000"), stop=D("1.09800"), spec=eurusd
    )
    assert result.risk_actual <= result.risk_budget


@pytest.mark.parametrize("equity", [D("0"), D("-5")])
def test_non_positive_equity_rejected(equity: Decimal, eurusd: InstrumentSpec) -> None:
    with pytest.raises(ValidationError, match="equity"):
        size_position(
            equity=equity, risk_pct=D("1"), entry=D("1.10000"), stop=D("1.09800"), spec=eurusd
        )


def test_equal_entry_and_stop_rejected(eurusd: InstrumentSpec) -> None:
    with pytest.raises(ValidationError, match="differ"):
        size_position(
            equity=D("10000"), risk_pct=D("1"), entry=D("1.1"), stop=D("1.1"), spec=eurusd
        )


def test_distance_not_a_tick_multiple_rejected(eurusd: InstrumentSpec) -> None:
    with pytest.raises(ValidationError, match="whole multiple of"):
        size_position(
            equity=D("10000"),
            risk_pct=D("1"),
            entry=D("1.100005"),
            stop=D("1.09800"),
            spec=eurusd,
        )


def test_negative_commission_rejected(eurusd: InstrumentSpec) -> None:
    with pytest.raises(ValidationError, match="commission_per_unit"):
        size_position(
            equity=D("10000"),
            risk_pct=D("1"),
            entry=D("1.10000"),
            stop=D("1.09800"),
            spec=eurusd,
            commission_per_unit=D("-1"),
        )


@pytest.mark.parametrize("slippage", [D("-1"), D("0.5")])
def test_invalid_slippage_rejected(slippage: Decimal, eurusd: InstrumentSpec) -> None:
    with pytest.raises(ValidationError, match="slippage_ticks"):
        size_position(
            equity=D("10000"),
            risk_pct=D("1"),
            entry=D("1.10000"),
            stop=D("1.09800"),
            spec=eurusd,
            slippage_ticks=slippage,
        )


def test_non_numeric_string_rejected(eurusd: InstrumentSpec) -> None:
    with pytest.raises(ValidationError, match="not a valid decimal"):
        size_position(
            equity="ten thousand",
            risk_pct=D("1"),
            entry=D("1.10000"),
            stop=D("1.09800"),
            spec=eurusd,
        )


def test_none_equity_rejected(eurusd: InstrumentSpec) -> None:
    with pytest.raises(TypeError, match="Decimal, int or str"):
        call_sizing(
            {
                "equity": None,
                "risk_pct": D("1"),
                "entry": D("1.10000"),
                "stop": D("1.09800"),
                "spec": eurusd,
            }
        )


def test_tiny_budget_yields_zero_and_below_min(eurusd: InstrumentSpec) -> None:
    result = size_position(
        equity=D("1"), risk_pct=D("0.5"), entry=D("1.10000"), stop=D("1.09800"), spec=eurusd
    )
    assert result.qty == D("0")
    assert result.status is SizeStatus.BELOW_MIN_QTY


def test_risk_actual_never_exceeds_budget_on_repeating_decimal(eurusd: InstrumentSpec) -> None:
    result = size_position(
        equity=D("3333.33"),
        risk_pct=D("0.7"),
        entry=D("1.12345"),
        stop=D("1.12012"),
        spec=eurusd,
        commission_per_unit=D("3.33"),
    )
    assert result.risk_actual <= result.risk_budget
    assert result.qty % eurusd.qty_step == 0


def call_sizing(kwargs: dict[str, object]) -> SizeResult:
    """Call size_position through a dynamic signature (tests pass wrong types)."""
    function = cast(Callable[..., SizeResult], size_position)
    return function(**kwargs)


def test_result_is_frozen(eurusd: InstrumentSpec) -> None:
    result = size_position(
        equity=D("10000"), risk_pct=D("1"), entry=D("1.10000"), stop=D("1.09800"), spec=eurusd
    )
    with pytest.raises(AttributeError):
        result.qty = D("9")
