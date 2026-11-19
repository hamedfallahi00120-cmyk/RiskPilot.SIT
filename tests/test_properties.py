"""Randomised property-style tests using the standard library ``random``.

Every test uses a fixed seed, so failures are reproducible.
"""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from riskpilot import (
    DailyRiskGuard,
    DecisionKind,
    EquityUpdate,
    Fill,
    GuardConfig,
    InstrumentSpec,
    OrderRequest,
    SizeStatus,
    size_position,
)

D = Decimal


def random_spec(rng: random.Random) -> InstrumentSpec:
    """Return a random but internally consistent instrument."""
    if rng.random() < 0.5:
        tick_size = D("0.00001")
        tick_value = D(rng.choice(["1", "0.5", "2.25"]))
        qty_step = D("0.01")
        min_qty = D("0.01")
        max_qty = D(rng.choice(["10", "100", "500"]))
    else:
        tick_size = D(rng.choice(["0.25", "0.05", "0.5"]))
        tick_value = D(rng.choice(["5", "0.5", "12.5"]))
        qty_step = D(rng.choice(["1", "2"]))
        min_qty = qty_step
        max_qty = qty_step * D(rng.randint(2, 200))
    return InstrumentSpec(
        symbol="RND",
        tick_size=tick_size,
        tick_value=tick_value,
        min_qty=min_qty,
        qty_step=qty_step,
        max_qty=max_qty,
    )


def random_inputs(rng: random.Random, spec: InstrumentSpec) -> dict[str, Decimal]:
    """Return random valid sizing inputs for ``spec``."""
    ticks = rng.randint(1, 400)
    entry = D(rng.randint(100, 30000)) + spec.tick_size * D(rng.randint(0, 3))
    distance = spec.tick_size * D(ticks)
    stop = entry - distance if rng.random() < 0.5 else entry + distance
    return {
        "equity": D(rng.randint(1, 5_000_000)) / D(rng.choice([1, 10, 100])),
        "risk_pct": D(rng.randint(1, 500)) / D(100),
        "entry": entry,
        "stop": stop,
        "commission_per_unit": D(rng.randint(0, 2000)) / D(100),
        "slippage_ticks": D(rng.randint(0, 5)),
    }


def test_risk_actual_never_exceeds_budget() -> None:
    rng = random.Random(20260504)
    for _ in range(2000):
        spec = random_spec(rng)
        result = size_position(spec=spec, **random_inputs(rng, spec))
        assert result.risk_actual <= result.risk_budget, result
        assert result.risk_actual >= 0


def test_qty_is_always_a_multiple_of_qty_step() -> None:
    rng = random.Random(7)
    for _ in range(2000):
        spec = random_spec(rng)
        result = size_position(spec=spec, **random_inputs(rng, spec))
        assert result.qty % spec.qty_step == 0, (result.qty, spec.qty_step)
        assert result.qty == result.qty.to_integral_value() * 1 or spec.qty_step < 1


def test_qty_is_never_rounded_up() -> None:
    rng = random.Random(99)
    for _ in range(2000):
        spec = random_spec(rng)
        inputs = random_inputs(rng, spec)
        result = size_position(spec=spec, **inputs)
        if result.status is SizeStatus.CAPPED_AT_MAX:
            continue
        one_more_step = result.qty + spec.qty_step
        assert one_more_step * result.risk_per_unit > result.risk_budget


def test_status_matches_quantity_bounds() -> None:
    rng = random.Random(1234)
    seen = set()
    for _ in range(500):
        spec = random_spec(rng)
        result = size_position(spec=spec, **random_inputs(rng, spec))
        seen.add(result.status)
        if result.status is SizeStatus.OK:
            assert spec.min_qty <= result.qty <= spec.max_qty
        elif result.status is SizeStatus.BELOW_MIN_QTY:
            assert result.qty == 0
        else:
            assert result.qty == spec.max_qty
    assert seen == set(SizeStatus)


def test_guard_serialisation_round_trip_is_lossless() -> None:
    rng = random.Random(424242)
    start = datetime(2026, 5, 4, 0, 0, tzinfo=UTC)
    symbols = ["EURUSD", "NQ", "MNQ"]
    config = GuardConfig(daily_loss_limit=D("2500"), max_trades_per_day=25)
    for _ in range(30):
        guard = DailyRiskGuard(config)
        timestamp = start
        for _ in range(rng.randint(1, 40)):
            timestamp += timedelta(minutes=rng.randint(1, 60))
            roll = rng.random()
            if roll < 0.5:
                guard.on_event(EquityUpdate(ts=timestamp, equity=D(rng.randint(9000, 11000))))
            elif roll < 0.75:
                guard.on_event(
                    OrderRequest(
                        ts=timestamp, symbol=rng.choice(symbols), qty=D("1"), risk_amount=D("50")
                    )
                )
            else:
                guard.on_event(
                    Fill(ts=timestamp, symbol=rng.choice(symbols), qty_delta=D(rng.randint(-3, 3)))
                )
        payload = json.loads(json.dumps(guard.to_dict()))
        restored = DailyRiskGuard.from_dict(config, payload)
        assert restored.to_dict() == guard.to_dict()
        assert restored.state is guard.state
        onward = timestamp + timedelta(minutes=5)
        event = EquityUpdate(ts=onward, equity=D("9500"))
        assert restored.on_event(event) == guard.on_event(event)


def test_random_valid_timestamps_never_raise() -> None:
    rng = random.Random(555)
    config = GuardConfig(daily_loss_limit_pct=D("1"), session_tz="America/Chicago")
    guard = DailyRiskGuard(config)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    for _ in range(300):
        timestamp += timedelta(hours=rng.randint(1, 36), minutes=rng.randint(0, 59))
        decision = guard.on_event(EquityUpdate(ts=timestamp, equity=D(rng.randint(1, 100000))))
        assert decision.kind in set(DecisionKind)


def test_lockout_volume_is_at_most_one_per_session() -> None:
    rng = random.Random(31337)
    config = GuardConfig(daily_loss_limit=D("500"))
    guard = DailyRiskGuard(config)
    timestamp = datetime(2026, 5, 4, tzinfo=UTC)
    flattens = 0
    for _ in range(400):
        timestamp += timedelta(minutes=rng.randint(1, 120))
        decision = guard.on_event(EquityUpdate(ts=timestamp, equity=D(rng.randint(9000, 10000))))
        if decision.kind is DecisionKind.FLATTEN_ALL:
            flattens += 1
            assert guard.state.value == "LOCKED"
        if decision.kind is DecisionKind.NONE and decision.reason.value == "SESSION_RESET":
            flattens = 0
    assert flattens <= 1
