"""Serialisation tests: a restored guard must behave exactly like the original."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from riskpilot import (
    ConfigError,
    DailyRiskGuard,
    DecisionKind,
    EquityUpdate,
    Fill,
    GuardConfig,
    GuardState,
    OrderRequest,
    Reason,
)

D = Decimal
T0 = datetime(2026, 5, 4, 13, 0, tzinfo=UTC)


def at(minutes: int) -> datetime:
    """UTC timestamp ``minutes`` after the T0 anchor."""
    return T0 + timedelta(minutes=minutes)


def equity(minutes: int, value: str) -> EquityUpdate:
    return EquityUpdate(ts=at(minutes), equity=D(value))


def fill(minutes: int, qty: str, symbol: str = "EURUSD") -> Fill:
    return Fill(ts=at(minutes), symbol=symbol, qty_delta=D(qty))


def order(minutes: int, risk: str, symbol: str = "EURUSD") -> OrderRequest:
    return OrderRequest(ts=at(minutes), symbol=symbol, qty=D("1"), risk_amount=D(risk))


def test_serialization_round_trip(guard_config: GuardConfig) -> None:
    guard = DailyRiskGuard(guard_config)
    guard.on_event(equity(0, "10000"))
    guard.on_event(order(1, "100"))
    guard.on_event(fill(2, "1", symbol="NQ"))
    payload = json.loads(json.dumps(guard.to_dict()))
    restored = DailyRiskGuard.from_dict(guard_config, payload)
    assert restored.state is guard.state
    assert restored.baseline_equity == guard.baseline_equity
    assert restored.open_positions() == guard.open_positions()
    assert restored.trades_today == guard.trades_today
    assert restored.to_dict() == guard.to_dict()


def test_restored_guard_behaves_identically(guard_config: GuardConfig) -> None:
    guard = DailyRiskGuard(guard_config)
    guard.on_event(equity(0, "10000"))
    guard.on_event(order(1, "100"))
    guard.on_event(equity(2, "9400"))
    payload = json.loads(json.dumps(guard.to_dict()))
    restored = DailyRiskGuard.from_dict(guard_config, payload)
    subsequent = [order(3, "250"), order(4, "50"), equity(5, "9100"), order(6, "10")]
    left = [guard.on_event(event) for event in subsequent]
    renewed = [restored.on_event(event) for event in subsequent]
    assert left == renewed
    assert guard.to_dict() == restored.to_dict()


def test_restored_locked_guard_stays_locked(guard_config: GuardConfig) -> None:
    guard = DailyRiskGuard(guard_config)
    guard.on_event(equity(0, "10000"))
    guard.on_event(equity(1, "8000"))
    restored = DailyRiskGuard.from_dict(guard_config, json.loads(json.dumps(guard.to_dict())))
    assert restored.state is GuardState.LOCKED
    assert restored.on_event(order(2, "10")).reason is Reason.LOCKED
    assert restored.on_event(equity(3, "8000")).kind is DecisionKind.NONE


def test_from_dict_rejects_malformed_payload(guard_config: GuardConfig) -> None:
    with pytest.raises(ConfigError, match="state"):
        DailyRiskGuard.from_dict(guard_config, {"state": "NOPE"})


def test_from_dict_rejects_missing_state(guard_config: GuardConfig) -> None:
    with pytest.raises(ConfigError):
        DailyRiskGuard.from_dict(guard_config, {})


def test_empty_guard_properties() -> None:
    guard = DailyRiskGuard(GuardConfig(daily_loss_limit=D("1000")))
    assert guard.state is GuardState.ACTIVE
    assert guard.session_start is None
    assert guard.baseline_equity is None
    assert guard.high_water_equity is None
    assert guard.trades_today == 0
    assert guard.open_positions() == {}


def test_equity_update_sets_high_water(guard_config: GuardConfig) -> None:
    guard = DailyRiskGuard(guard_config)
    guard.on_event(equity(0, "10000"))
    guard.on_event(equity(1, "11000"))
    assert guard.high_water_equity == D("11000")


def test_serialised_state_uses_strings_and_round_trips_every_field(
    guard_config: GuardConfig,
) -> None:
    config = GuardConfig(
        daily_loss_limit=D("2000"),
        trailing_drawdown=D("300"),
        max_open_positions=3,
        max_trades_per_day=4,
    )
    guard = DailyRiskGuard(config)
    guard.on_event(equity(0, "10000"))
    guard.on_event(fill(1, "2", symbol="NQ"))
    state = guard.to_dict()
    assert state["state"] == "ACTIVE"
    assert state["session"]["baseline"] == "10000"
    assert state["session"]["high_water"] == "10000"
    assert state["session"]["trailing_breached"] is False
    assert state["open_positions"] == {"NQ": "2"}
    assert all(not isinstance(value, D) for value in state["session"].values() if value is not None)
    restored = DailyRiskGuard.from_dict(config, json.loads(json.dumps(state)))
    assert restored.high_water_equity == guard.high_water_equity
    assert restored.session_start == guard.session_start


def test_no_baseline_session_serialises_like_a_fresh_guard() -> None:
    config = GuardConfig(daily_loss_limit=D("500"))
    guard = DailyRiskGuard(config)
    guard.on_event(fill(0, "1"))
    state = guard.to_dict()
    assert state["session"]["baseline"] is None
    assert state["session"]["equity"] is None
    restored = DailyRiskGuard.from_dict(config, state)
    assert restored.to_dict() == state


def test_percentage_guard_round_trips_a_locked_session() -> None:
    config = GuardConfig(daily_loss_limit_pct=D("1"))
    guard = DailyRiskGuard(config)
    guard.on_event(equity(0, "10000"))
    assert guard.on_event(equity(1, "9800")).kind is DecisionKind.FLATTEN_ALL
    restored = DailyRiskGuard.from_dict(config, json.loads(json.dumps(guard.to_dict())))
    assert restored.loss_limit() == D("100.00")
    assert restored.on_event(order(2, "1")).reason is Reason.LOCKED


def test_serialise_before_any_event() -> None:
    guard = DailyRiskGuard(GuardConfig(daily_loss_limit=D("500")))
    state = guard.to_dict()
    assert state["session"] is None
    assert state["last_ts"] is None
    assert DailyRiskGuard.from_dict(guard.config, state).to_dict() == state


def test_serialise_session_without_baseline() -> None:
    guard = DailyRiskGuard(GuardConfig(daily_loss_limit=D("500")))
    guard.on_event(fill(0, "1"))
    state = guard.to_dict()
    assert state["session"]["baseline"] is None
    assert state["session"]["equity"] is None
    assert state["session"]["high_water"] is None


def test_from_dict_rejects_broken_session_payload(guard_config: GuardConfig) -> None:
    guard = DailyRiskGuard(guard_config)
    guard.on_event(equity(0, "10000"))
    corrupt = guard.to_dict()
    corrupt["session"]["start"] = "not-a-timestamp"
    with pytest.raises(ConfigError, match="invalid guard state payload"):
        DailyRiskGuard.from_dict(guard_config, corrupt)
