"""Tests for the daily risk guard state machine."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast

import pytest

from riskpilot import (
    DailyRiskGuard,
    Decision,
    DecisionKind,
    EquityUpdate,
    Fill,
    GuardConfig,
    GuardState,
    OrderRequest,
    OutOfOrderEventError,
    Reason,
    ValidationError,
)

D = Decimal
T0 = datetime(2026, 5, 4, 13, 0, tzinfo=UTC)


def at(minutes: int) -> datetime:
    """UTC timestamp ``minutes`` after the T0 anchor."""
    return T0 + timedelta(minutes=minutes)


def equity(minutes: int, value: str) -> EquityUpdate:
    return EquityUpdate(ts=at(minutes), equity=D(value))


def order(minutes: int, risk: str, symbol: str = "EURUSD") -> OrderRequest:
    return OrderRequest(ts=at(minutes), symbol=symbol, qty=D("1"), risk_amount=D(risk))


def fill(minutes: int, qty: str, symbol: str = "EURUSD") -> Fill:
    return Fill(ts=at(minutes), symbol=symbol, qty_delta=D(qty))


def test_first_event_starts_session(guard_config: GuardConfig) -> None:
    guard = DailyRiskGuard(guard_config)
    decision = guard.on_event(equity(0, "10000"))
    assert decision.kind is DecisionKind.NONE
    assert decision.reason is Reason.SESSION_RESET
    assert decision.state is GuardState.ACTIVE
    assert guard.baseline_equity == D("10000")
    assert guard.session_start == datetime(2026, 5, 4, 0, 0, tzinfo=UTC)


def test_order_before_baseline_rejected(guard_config: GuardConfig) -> None:
    guard = DailyRiskGuard(guard_config)
    decision = guard.on_event(order(1, "100"))
    assert decision.kind is DecisionKind.REJECT
    assert decision.reason is Reason.NO_EQUITY_BASELINE
    assert guard.trades_today == 0


def test_allow_then_reject_would_breach(guard_config: GuardConfig) -> None:
    guard = DailyRiskGuard(guard_config)
    guard.on_event(equity(0, "10000"))
    assert guard.on_event(order(1, "300")).kind is DecisionKind.ALLOW
    assert guard.on_event(equity(2, "9300")).state is GuardState.WARNING
    strict = guard.on_event(order(3, "250"))  # 700 + 250 = 950 < 1000 -> allowed
    assert strict.kind is DecisionKind.ALLOW
    rejected = guard.on_event(order(4, "300"))  # 700 + 300 == 1000 -> rejected
    assert rejected.kind is DecisionKind.REJECT
    assert rejected.reason is Reason.WOULD_BREACH_LIMIT
    assert guard.trades_today == 2


def test_warning_is_bidirectional(guard_config: GuardConfig) -> None:
    guard = DailyRiskGuard(guard_config)
    guard.on_event(equity(0, "10000"))  # limit 1000, warning at 700
    assert guard.on_event(equity(1, "9300")).state is GuardState.WARNING
    assert guard.on_event(equity(2, "9400")).state is GuardState.ACTIVE


def test_breach_locks_and_flattens_once(guard_config: GuardConfig) -> None:
    guard = DailyRiskGuard(guard_config)
    guard.on_event(equity(0, "10000"))
    first = guard.on_event(equity(1, "9000"))
    assert first.kind is DecisionKind.FLATTEN_ALL
    assert first.state is GuardState.LOCKED
    second = guard.on_event(equity(2, "8000"))
    assert second.kind is DecisionKind.NONE
    assert second.reason is Reason.LOCKED
    assert guard.state is GuardState.LOCKED


def test_locked_is_sticky_even_after_recovery(guard_config: GuardConfig) -> None:
    guard = DailyRiskGuard(guard_config)
    guard.on_event(equity(0, "10000"))
    guard.on_event(equity(1, "8000"))
    assert guard.state is GuardState.LOCKED
    assert guard.on_event(equity(2, "12000")).state is GuardState.LOCKED
    assert guard.state is GuardState.LOCKED
    decision = guard.on_event(order(3, "10"))
    assert decision.kind is DecisionKind.REJECT
    assert decision.reason is Reason.LOCKED


def test_lockout_is_idempotent_within_session(guard_config: GuardConfig) -> None:
    guard = DailyRiskGuard(guard_config)
    guard.on_event(equity(0, "10000"))
    assert guard.on_event(equity(1, "8500")).kind is DecisionKind.FLATTEN_ALL
    for minute, value in ((2, "8000"), (3, "7000"), (4, "8200")):
        assert guard.on_event(equity(minute, value)).kind is DecisionKind.NONE


def test_new_session_resets_state_and_baseline(guard_config: GuardConfig) -> None:
    guard = DailyRiskGuard(guard_config)
    guard.on_event(equity(0, "10000"))
    guard.on_event(equity(1, "8500"))
    next_day = EquityUpdate(ts=T0 + timedelta(days=1), equity=D("8400"))
    decision = guard.on_event(next_day)
    assert decision.state is GuardState.ACTIVE
    assert decision.reason is Reason.SESSION_RESET
    assert guard.baseline_equity == D("8400")
    nxt = T0 + timedelta(days=1, minutes=5)
    assert (
        guard.on_event(OrderRequest(ts=nxt, symbol="EURUSD", qty=D("1"), risk_amount=D("100"))).kind
        is DecisionKind.ALLOW
    )


def test_open_positions_survive_session_reset(guard_config: GuardConfig) -> None:
    guard = DailyRiskGuard(guard_config)
    guard.on_event(equity(0, "10000"))
    guard.on_event(fill(1, "2", symbol="NQ"))
    guard.on_event(EquityUpdate(ts=T0 + timedelta(days=1), equity=D("10000")))
    assert guard.open_positions() == {"NQ": D("2")}


def test_max_trades_per_day() -> None:
    config = GuardConfig(daily_loss_limit=D("1000"), max_trades_per_day=2)
    guard = DailyRiskGuard(config)
    guard.on_event(equity(0, "10000"))
    assert guard.on_event(order(1, "10")).kind is DecisionKind.ALLOW
    assert guard.on_event(order(2, "10")).kind is DecisionKind.ALLOW
    blocked = guard.on_event(order(3, "10"))
    assert blocked.reason is Reason.MAX_TRADES
    assert guard.trades_today == 2


def test_rejected_order_does_not_count_as_trade() -> None:
    config = GuardConfig(daily_loss_limit=D("1000"), max_trades_per_day=1)
    guard = DailyRiskGuard(config)
    guard.on_event(equity(0, "10000"))
    assert guard.on_event(order(1, "5000")).kind is DecisionKind.REJECT
    assert guard.trades_today == 0
    assert guard.on_event(order(2, "10")).kind is DecisionKind.ALLOW


def test_max_open_positions() -> None:
    config = GuardConfig(daily_loss_limit=D("1000"), max_open_positions=2)
    guard = DailyRiskGuard(config)
    guard.on_event(equity(0, "10000"))
    guard.on_event(fill(1, "1", symbol="EURUSD"))
    guard.on_event(fill(2, "1", symbol="NQ"))
    blocked = guard.on_event(order(3, "10", symbol="MNQ"))
    assert blocked.kind is DecisionKind.REJECT
    assert blocked.reason is Reason.MAX_OPEN_POSITIONS
    same_symbol = guard.on_event(order(4, "10", symbol="NQ"))
    assert same_symbol.kind is DecisionKind.ALLOW


def test_flattened_symbol_frees_a_slot() -> None:
    config = GuardConfig(daily_loss_limit=D("1000"), max_open_positions=1)
    guard = DailyRiskGuard(config)
    guard.on_event(equity(0, "10000"))
    guard.on_event(fill(1, "1", symbol="EURUSD"))
    assert guard.on_event(order(2, "10", symbol="NQ")).kind is DecisionKind.REJECT
    guard.on_event(fill(3, "-1", symbol="EURUSD"))
    assert guard.on_event(order(4, "10", symbol="NQ")).kind is DecisionKind.ALLOW


def test_net_zero_quantity_closes_position() -> None:
    guard = DailyRiskGuard(GuardConfig(daily_loss_limit=D("1000")))
    guard.on_event(equity(0, "10000"))
    guard.on_event(fill(1, "3"))
    guard.on_event(fill(2, "-3"))
    assert guard.open_positions() == {}


def test_naive_timestamp_raises() -> None:
    guard = DailyRiskGuard(GuardConfig(daily_loss_limit=D("1000")))
    with pytest.raises(ValidationError, match="timezone-aware"):
        guard.on_event(EquityUpdate(ts=datetime(2026, 5, 4, 13, 0), equity=D("10000")))


def test_out_of_order_timestamp_raises() -> None:
    guard = DailyRiskGuard(GuardConfig(daily_loss_limit=D("1000")))
    guard.on_event(equity(10, "10000"))
    with pytest.raises(OutOfOrderEventError):
        guard.on_event(equity(9, "10000"))


def test_equal_timestamp_is_allowed() -> None:
    guard = DailyRiskGuard(GuardConfig(daily_loss_limit=D("1000")))
    guard.on_event(equity(0, "10000"))
    assert guard.on_event(fill(0, "1")).kind is DecisionKind.NONE


def test_percentage_limit_uses_session_baseline() -> None:
    config = GuardConfig(daily_loss_limit_pct=D("2"), max_trades_per_day=5)
    guard = DailyRiskGuard(config)
    guard.on_event(equity(0, "50000"))
    assert guard.loss_limit() == D("1000.00")
    guard.on_event(equity(1, "49300"))
    assert guard.state is GuardState.WARNING
    decision = guard.on_event(equity(2, "49000"))
    assert decision.kind is DecisionKind.FLATTEN_ALL


def test_percentage_limit_unknown_before_baseline() -> None:
    guard = DailyRiskGuard(GuardConfig(daily_loss_limit_pct=D("2")))
    assert guard.loss_limit() is None
    assert guard.current_loss() == D("0")


def test_trailing_drawdown_locks_before_daily_limit() -> None:
    config = GuardConfig(daily_loss_limit=D("5000"), trailing_drawdown=D("500"))
    guard = DailyRiskGuard(config)
    guard.on_event(equity(0, "10000"))
    guard.on_event(equity(1, "10600"))
    decision = guard.on_event(equity(2, "10100"))
    assert decision.kind is DecisionKind.FLATTEN_ALL
    assert decision.reason is Reason.TRAILING_DRAWDOWN
    assert guard.current_loss() == D("0")


def test_trailing_drawdown_stays_locked_if_equity_recovers() -> None:
    config = GuardConfig(daily_loss_limit=D("5000"), trailing_drawdown=D("500"))
    guard = DailyRiskGuard(config)
    guard.on_event(equity(0, "10000"))
    guard.on_event(equity(1, "10600"))
    guard.on_event(equity(2, "10000"))
    assert guard.on_event(equity(3, "10600")).kind is DecisionKind.NONE
    assert guard.state is GuardState.LOCKED


def test_invalid_order_risk_amount_rejected() -> None:
    guard = DailyRiskGuard(GuardConfig(daily_loss_limit=D("1000")))
    guard.on_event(equity(0, "10000"))
    with pytest.raises(ValidationError, match="risk_amount"):
        guard.on_event(order(1, "0"))


def test_fill_requires_symbol() -> None:
    guard = DailyRiskGuard(GuardConfig(daily_loss_limit=D("1000")))
    guard.on_event(equity(0, "10000"))
    with pytest.raises(ValidationError, match="symbol"):
        guard.on_event(Fill(ts=at(1), symbol="", qty_delta=D("1")))


def test_unexpected_event_type_raises_type_error() -> None:
    guard = DailyRiskGuard(GuardConfig(daily_loss_limit=D("1000")))
    feed = cast(Callable[[object], Decision], guard.on_event)
    with pytest.raises(TypeError, match="EquityUpdate"):
        feed("not an event")
