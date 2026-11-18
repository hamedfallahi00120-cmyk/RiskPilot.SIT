"""Seeded randomized property-style tests.

Each test drives real code with a fixed-seed ``random.Random`` and asserts an
invariant that must hold for every generated input. No mocks: the properties run
against the real sizing and guard implementations.
"""

from __future__ import annotations

import json
import random
from datetime import time
from decimal import Decimal

from riskpilot import (
    DailyRiskGuard,
    DecisionKind,
    EquityUpdate,
    Fill,
    GuardConfig,
    GuardState,
    InstrumentSpec,
    OrderRequest,
    size_position,
)
from tests.conftest import utc

D = Decimal


def _random_spec(rng: random.Random) -> InstrumentSpec:
    step = rng.choice([D("0.01"), D("0.1"), D("1")])
    min_qty = step * rng.randint(1, 5)
    max_qty = min_qty + step * rng.randint(1, 500)
    return InstrumentSpec(
        symbol="RND",
        tick_size=D(rng.choice(["0.00001", "0.25", "0.1", "0.01"])),
        tick_value=D(str(rng.randint(1, 1000))) / D(100),
        min_qty=min_qty,
        qty_step=step,
        max_qty=max_qty,
    )


def _random_sizing_case(
    rng: random.Random,
) -> tuple[Decimal, Decimal, Decimal, Decimal, InstrumentSpec]:
    spec = _random_spec(rng)
    entry = D(str(rng.randint(1, 10000))) / D(10)
    ticks = rng.randint(1, 200)
    stop = entry - ticks * spec.tick_size
    equity = D(str(rng.randint(100, 1_000_000))) / D(10)
    risk_pct = D(str(rng.randint(1, 500))) / D(100)
    return equity, risk_pct, entry, stop, spec


def test_property_risk_actual_never_exceeds_budget() -> None:
    rng = random.Random(1001)
    for _ in range(2000):
        equity, risk_pct, entry, stop, spec = _random_sizing_case(rng)
        result = size_position(equity=equity, risk_pct=risk_pct, entry=entry, stop=stop, spec=spec)
        assert result.risk_actual <= result.risk_budget


def test_property_qty_is_a_multiple_of_step() -> None:
    rng = random.Random(1002)
    for _ in range(2000):
        equity, risk_pct, entry, stop, spec = _random_sizing_case(rng)
        result = size_position(equity=equity, risk_pct=risk_pct, entry=entry, stop=stop, spec=spec)
        assert result.qty % spec.qty_step == 0


def test_property_qty_never_exceeds_max() -> None:
    rng = random.Random(1003)
    for _ in range(2000):
        equity, risk_pct, entry, stop, spec = _random_sizing_case(rng)
        result = size_position(equity=equity, risk_pct=risk_pct, entry=entry, stop=stop, spec=spec)
        assert result.qty <= spec.max_qty


def test_property_status_is_consistent_with_qty() -> None:
    rng = random.Random(1004)
    for _ in range(2000):
        equity, risk_pct, entry, stop, spec = _random_sizing_case(rng)
        result = size_position(equity=equity, risk_pct=risk_pct, entry=entry, stop=stop, spec=spec)
        if result.qty == 0:
            assert result.status.name == "BELOW_MIN_QTY"
        elif result.qty == spec.max_qty and result.risk_actual > result.risk_budget:
            assert result.status.name == "CAPPED_AT_MAX"


def test_property_serialization_round_trip_is_identity() -> None:
    rng = random.Random(1005)
    for _ in range(100):
        config = GuardConfig(daily_loss_limit=D("1000"), session_tz="UTC")
        guard = DailyRiskGuard(config)
        for minute in range(1, rng.randint(2, 20)):
            ts = utc(f"2026-05-04T10:{minute:02d}:00+00:00")
            roll = rng.random()
            if roll < 0.5:
                event: EquityUpdate | OrderRequest | Fill = EquityUpdate(
                    ts, D(str(rng.randint(8000, 12000)))
                )
            elif roll < 0.75:
                event = OrderRequest(ts, "NQ", D("1"), D(str(rng.randint(1, 200))))
            else:
                event = Fill(ts, "NQ", D(str(rng.randint(-3, 3))))
            guard.on_event(event)
        snapshot = json.loads(json.dumps(guard.to_dict()))
        restored = DailyRiskGuard.from_dict(config, snapshot)
        assert restored.to_dict() == guard.to_dict()


def test_property_locked_is_sticky_within_a_session() -> None:
    rng = random.Random(1006)
    for _ in range(100):
        config = GuardConfig(daily_loss_limit=D("500"), session_tz="UTC")
        guard = DailyRiskGuard(config)
        locked_seen = False
        for minute in range(1, 30):
            ts = utc(f"2026-05-04T10:{minute:02d}:00+00:00")
            equity = D(str(rng.randint(9000, 10000)))
            decision = guard.on_event(EquityUpdate(ts, equity))
            if decision.kind is DecisionKind.FLATTEN_ALL:
                locked_seen = True
            if locked_seen:
                assert guard.state is GuardState.LOCKED


def test_property_flatten_all_is_announced_once() -> None:
    rng = random.Random(1007)
    for _ in range(100):
        config = GuardConfig(daily_loss_limit=D("500"), session_tz="UTC")
        guard = DailyRiskGuard(config)
        announcements = 0
        for minute in range(1, 30):
            ts = utc(f"2026-05-04T10:{minute:02d}:00+00:00")
            equity = D(str(rng.randint(8000, 10000)))
            if guard.on_event(EquityUpdate(ts, equity)).kind is DecisionKind.FLATTEN_ALL:
                announcements += 1
        assert announcements <= 1


def test_property_session_reset_clears_state() -> None:
    rng = random.Random(1008)
    for _ in range(50):
        config = GuardConfig(
            daily_loss_limit=D("500"),
            session_reset_time=time(0, 0),
            session_tz="UTC",
        )
        guard = DailyRiskGuard(config)
        guard.on_event(EquityUpdate(utc("2026-05-04T10:00:00+00:00"), D("10000")))
        drop = D(str(rng.randint(8000, 9500)))
        guard.on_event(EquityUpdate(utc("2026-05-04T11:00:00+00:00"), drop))
        # A new session begins the next calendar day.
        decision = guard.on_event(EquityUpdate(utc("2026-05-05T10:00:00+00:00"), D("9000")))
        assert decision.state is GuardState.ACTIVE
