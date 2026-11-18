"""Tests for :func:`riskpilot.size_position`, including the spec acceptance cases."""

from __future__ import annotations

import random
from decimal import Decimal

import pytest

from riskpilot import InstrumentSpec, SizeStatus, size_position
from riskpilot.errors import ValidationError

D = Decimal


def _size(spec: InstrumentSpec, **kwargs: object):
    params: dict[str, object] = {
        "equity": D("10000"),
        "risk_pct": D("1"),
        "entry": D("1.10000"),
        "stop": D("1.09800"),
    }
    params.update(kwargs)
    return size_position(spec=spec, **params)


def test_acceptance_1_eurusd_basic(eurusd: InstrumentSpec) -> None:
    result = _size(eurusd)
    assert result.qty == D("0.50")
    assert result.risk_actual == D("100.0000")
    assert result.status is SizeStatus.OK
    assert result.risk_actual <= result.risk_budget


def test_acceptance_2_eurusd_with_commission(eurusd: InstrumentSpec) -> None:
    result = _size(eurusd, commission_per_unit=D("7"))
    assert result.qty == D("0.48")
    assert result.risk_per_unit == D("207.00")
    assert result.risk_actual <= result.risk_budget


def test_acceptance_3_nq(nq: InstrumentSpec) -> None:
    result = _size(nq, equity=D("50000"), risk_pct=D("0.5"), entry=D("20000"), stop=D("19990"))
    assert result.qty == D("1")
    assert result.risk_actual == D("200.00")
    assert result.status is SizeStatus.OK


def test_acceptance_4_mnq(mnq: InstrumentSpec) -> None:
    result = _size(mnq, equity=D("50000"), risk_pct=D("0.5"), entry=D("20000"), stop=D("19990"))
    assert result.qty == D("12")
    assert result.risk_actual == D("240.00")
    assert result.status is SizeStatus.OK


def test_acceptance_5_nq_below_min(nq: InstrumentSpec) -> None:
    result = _size(nq, equity=D("1000"), risk_pct=D("0.5"), entry=D("20000"), stop=D("19990"))
    assert result.qty == D("0")
    assert result.status is SizeStatus.BELOW_MIN_QTY
    assert result.risk_actual == D("0")


def test_capped_at_max(nq: InstrumentSpec) -> None:
    result = _size(nq, equity=D("100000000"), risk_pct=D("5"), entry=D("20000"), stop=D("19990"))
    assert result.qty == nq.max_qty
    assert result.status is SizeStatus.CAPPED_AT_MAX
    assert result.risk_actual <= result.risk_budget


def test_slippage_increases_risk_per_unit(eurusd: InstrumentSpec) -> None:
    without = _size(eurusd)
    with_slip = _size(eurusd, slippage_ticks=2)
    assert with_slip.risk_per_unit == without.risk_per_unit + 2 * eurusd.tick_value
    assert with_slip.qty <= without.qty


def test_short_side_uses_absolute_distance(eurusd: InstrumentSpec) -> None:
    long_side = _size(eurusd, entry=D("1.09800"), stop=D("1.10000"))
    short_side = _size(eurusd, entry=D("1.10000"), stop=D("1.09800"))
    assert long_side.qty == short_side.qty


def test_entry_equals_stop_rejected(eurusd: InstrumentSpec) -> None:
    with pytest.raises(ValidationError, match="differ"):
        _size(eurusd, entry=D("1.1"), stop=D("1.1"))


def test_non_whole_tick_distance_rejected(eurusd: InstrumentSpec) -> None:
    with pytest.raises(ValidationError, match="whole multiple"):
        _size(eurusd, entry=D("1.100005"), stop=D("1.09800"))


@pytest.mark.parametrize("bad", [1.0, True])
def test_float_arguments_raise_type_error(eurusd: InstrumentSpec, bad: object) -> None:
    with pytest.raises(TypeError):
        _size(eurusd, equity=bad)


def test_float_risk_pct_raises_type_error(eurusd: InstrumentSpec) -> None:
    with pytest.raises(TypeError):
        _size(eurusd, risk_pct=1.0)


def test_float_commission_raises_type_error(eurusd: InstrumentSpec) -> None:
    with pytest.raises(TypeError):
        _size(eurusd, commission_per_unit=7.0)


def test_non_spec_raises_type_error() -> None:
    with pytest.raises(TypeError):
        size_position(
            equity=D("1000"),
            risk_pct=D("1"),
            entry=D("1"),
            stop=D("2"),
            spec="not-a-spec",
        )


@pytest.mark.parametrize("risk_pct", [D("0"), D("-1"), D("5.0001")])
def test_risk_pct_out_of_range(eurusd: InstrumentSpec, risk_pct: Decimal) -> None:
    with pytest.raises(ValidationError, match="risk_pct"):
        _size(eurusd, risk_pct=risk_pct)


def test_risk_pct_upper_bound_inclusive(eurusd: InstrumentSpec) -> None:
    result = _size(eurusd, risk_pct=D("5"))
    assert result.status is SizeStatus.OK


def test_non_positive_equity_rejected(eurusd: InstrumentSpec) -> None:
    with pytest.raises(ValidationError, match="equity"):
        _size(eurusd, equity=D("0"))


def test_negative_commission_rejected(eurusd: InstrumentSpec) -> None:
    with pytest.raises(ValidationError, match="commission"):
        _size(eurusd, commission_per_unit=D("-1"))


def test_negative_slippage_rejected(eurusd: InstrumentSpec) -> None:
    with pytest.raises(ValidationError, match="slippage"):
        _size(eurusd, slippage_ticks=-1)


def test_non_integer_slippage_rejected(eurusd: InstrumentSpec) -> None:
    with pytest.raises(ValidationError, match="whole number"):
        _size(eurusd, slippage_ticks=D("1.5"))


def test_never_rounds_up_property() -> None:
    """Property: risk_actual <= risk_budget across 2000 seeded random inputs."""
    rng = random.Random(20240517)
    step_choices = [D("0.01"), D("0.1"), D("1")]
    for _ in range(2000):
        step = rng.choice(step_choices)
        min_qty = step * rng.randint(1, 5)
        max_qty = min_qty + step * rng.randint(1, 500)
        spec = InstrumentSpec(
            symbol="RND",
            tick_size=D(rng.choice(["0.00001", "0.25", "0.1", "0.01"])),
            tick_value=D(str(rng.randint(1, 1000))) / D(100),
            min_qty=min_qty,
            qty_step=step,
            max_qty=max_qty,
        )
        tick = spec.tick_size
        entry = D(str(rng.randint(1, 10000))) / D(10)
        ticks = rng.randint(1, 200)
        stop = entry - ticks * tick
        equity = D(str(rng.randint(100, 1_000_000))) / D(10)
        risk_pct = D(str(rng.randint(1, 500))) / D(100)
        result = size_position(equity=equity, risk_pct=risk_pct, entry=entry, stop=stop, spec=spec)
        assert result.risk_actual <= result.risk_budget
        assert result.qty % spec.qty_step == 0
        if result.qty > 0:
            assert result.qty >= spec.min_qty


def test_qty_is_always_a_multiple_of_step() -> None:
    rng = random.Random(777)
    spec = InstrumentSpec(
        symbol="S",
        tick_size=D("0.25"),
        tick_value=D("5"),
        min_qty=D("1"),
        qty_step=D("1"),
        max_qty=D("1000"),
    )
    for _ in range(500):
        ticks = rng.randint(1, 400)
        entry = D(str(rng.randint(100, 50000)))
        stop = entry - ticks * spec.tick_size
        equity = D(str(rng.randint(1000, 5_000_000)))
        risk_pct = D(str(rng.randint(1, 500))) / D(100)
        result = size_position(equity=equity, risk_pct=risk_pct, entry=entry, stop=stop, spec=spec)
        assert result.qty % spec.qty_step == 0
