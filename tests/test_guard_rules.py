"""Tests for :class:`riskpilot.DailyRiskGuard` rule behaviour."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, time
from decimal import Decimal

import pytest

from riskpilot.errors import OutOfOrderEventError, ValidationError
from riskpilot.guard import (
    DailyRiskGuard,
    Decision,
    DecisionKind,
    EquityUpdate,
    Fill,
    GuardConfig,
    GuardState,
    OrderRequest,
    Reason,
)
from tests.conftest import utc

D = Decimal


def _guard(**overrides: object) -> DailyRiskGuard:
    params: dict[str, object] = {
        "daily_loss_limit": D("1000"),
        "session_reset_time": time(0, 0),
        "session_tz": "UTC",
    }
    params.update(overrides)
    return DailyRiskGuard(GuardConfig(**params))


def _equity(minute: int, equity: str) -> EquityUpdate:
    return EquityUpdate(ts=utc(f"2026-05-04T10:{minute:02d}:00+00:00"), equity=D(equity))


def test_first_equity_sets_baseline_no_decision() -> None:
    guard = _guard()
    decision = guard.on_event(_equity(0, "10000"))
    assert decision.kind is DecisionKind.NONE
    assert decision.reason is Reason.NONE
    assert guard.state is GuardState.ACTIVE


def test_order_before_baseline_rejected() -> None:
    guard = _guard()
    decision = guard.on_event(OrderRequest(utc("2026-05-04T10:00:00+00:00"), "NQ", D("1"), D("10")))
    assert decision.kind is DecisionKind.REJECT
    assert decision.reason is Reason.NO_EQUITY_BASELINE


def test_order_allowed_when_within_limit() -> None:
    guard = _guard()
    guard.on_event(_equity(0, "10000"))
    decision = guard.on_event(
        OrderRequest(utc("2026-05-04T10:01:00+00:00"), "NQ", D("1"), D("100"))
    )
    assert decision.kind is DecisionKind.ALLOW
    assert decision.reason is Reason.OK


def test_order_would_breach_limit_rejected() -> None:
    guard = _guard()
    guard.on_event(_equity(0, "10000"))
    guard.on_event(_equity(1, "9500"))  # loss 500, warning
    decision = guard.on_event(
        OrderRequest(utc("2026-05-04T10:02:00+00:00"), "NQ", D("1"), D("500"))
    )
    assert decision.kind is DecisionKind.REJECT
    assert decision.reason is Reason.WOULD_BREACH_LIMIT


def test_rejected_order_does_not_mutate_state() -> None:
    guard = _guard(max_trades_per_day=1)
    guard.on_event(_equity(0, "10000"))
    first = guard.on_event(OrderRequest(utc("2026-05-04T10:01:00+00:00"), "NQ", D("1"), D("10")))
    assert first.kind is DecisionKind.ALLOW
    second = guard.on_event(OrderRequest(utc("2026-05-04T10:02:00+00:00"), "NQ", D("1"), D("10")))
    assert second.kind is DecisionKind.REJECT
    assert second.reason is Reason.MAX_TRADES
    # ``last_ts`` advances for every accepted event (monotonicity), so compare
    # the risk-relevant state only.
    before = {k: v for k, v in guard.to_dict().items() if k != "last_ts"}
    guard.on_event(OrderRequest(utc("2026-05-04T10:03:00+00:00"), "NQ", D("1"), D("10")))
    after = {k: v for k, v in guard.to_dict().items() if k != "last_ts"}
    assert after == before


def test_warning_then_active_moves_both_ways() -> None:
    guard = _guard()
    guard.on_event(_equity(0, "10000"))
    guard.on_event(_equity(1, "9500"))
    assert guard.state is GuardState.ACTIVE  # loss 500 < 700
    guard.on_event(_equity(2, "9200"))
    assert guard.state is GuardState.WARNING  # loss 800 >= 700
    guard.on_event(_equity(3, "9800"))
    assert guard.state is GuardState.ACTIVE


def test_limit_breach_locks_and_flattens_once() -> None:
    guard = _guard()
    guard.on_event(_equity(0, "10000"))
    first = guard.on_event(_equity(1, "9000"))
    assert first.kind is DecisionKind.FLATTEN_ALL
    assert first.reason is Reason.LOCKED
    assert guard.state is GuardState.LOCKED
    again = guard.on_event(_equity(2, "8999"))
    assert again.kind is DecisionKind.NONE
    assert again.state is GuardState.LOCKED


def test_locked_order_rejected() -> None:
    guard = _guard()
    guard.on_event(_equity(0, "10000"))
    guard.on_event(_equity(1, "9000"))
    decision = guard.on_event(OrderRequest(utc("2026-05-04T10:02:00+00:00"), "NQ", D("1"), D("10")))
    assert decision.kind is DecisionKind.REJECT
    assert decision.reason is Reason.LOCKED


def test_locked_is_sticky_until_next_session() -> None:
    guard = _guard()
    guard.on_event(_equity(0, "10000"))
    guard.on_event(_equity(1, "9000"))
    assert guard.state is GuardState.LOCKED
    # Next day at 00:01 UTC resets the session.
    guard.on_event(EquityUpdate(utc("2026-05-05T00:01:00+00:00"), D("10000")))
    assert guard.state is GuardState.ACTIVE


def test_trailing_drawdown_locks_even_when_daily_limit_intact() -> None:
    guard = _guard(trailing_drawdown=D("300"))
    guard.on_event(_equity(0, "10000"))
    guard.on_event(_equity(1, "10500"))  # high water 10500
    decision = guard.on_event(_equity(2, "10100"))  # drawdown 400 >= 300
    assert decision.kind is DecisionKind.FLATTEN_ALL
    assert guard.state is GuardState.LOCKED


def test_max_open_positions_rejected() -> None:
    guard = _guard(max_open_positions=1)
    guard.on_event(_equity(0, "10000"))
    guard.on_event(Fill(utc("2026-05-04T10:01:00+00:00"), "NQ", D("1")))
    decision = guard.on_event(
        OrderRequest(utc("2026-05-04T10:02:00+00:00"), "MNQ", D("1"), D("10"))
    )
    assert decision.kind is DecisionKind.REJECT
    assert decision.reason is Reason.MAX_OPEN_POSITIONS


def test_adding_to_existing_symbol_is_allowed() -> None:
    guard = _guard(max_open_positions=1)
    guard.on_event(_equity(0, "10000"))
    guard.on_event(Fill(utc("2026-05-04T10:01:00+00:00"), "NQ", D("1")))
    decision = guard.on_event(OrderRequest(utc("2026-05-04T10:02:00+00:00"), "NQ", D("1"), D("10")))
    assert decision.kind is DecisionKind.ALLOW


def test_open_positions_ignores_flat_symbols() -> None:
    guard = _guard(max_open_positions=1)
    guard.on_event(_equity(0, "10000"))
    guard.on_event(Fill(utc("2026-05-04T10:01:00+00:00"), "NQ", D("1")))
    guard.on_event(Fill(utc("2026-05-04T10:02:00+00:00"), "NQ", D("-1")))
    decision = guard.on_event(
        OrderRequest(utc("2026-05-04T10:03:00+00:00"), "MNQ", D("1"), D("10"))
    )
    assert decision.kind is DecisionKind.ALLOW


def test_max_trades_per_day_rejected() -> None:
    guard = _guard(max_trades_per_day=2)
    guard.on_event(_equity(0, "10000"))
    for minute in (1, 2):
        decision = guard.on_event(
            OrderRequest(utc(f"2026-05-04T10:0{minute}:00+00:00"), "NQ", D("1"), D("10"))
        )
        assert decision.kind is DecisionKind.ALLOW
    third = guard.on_event(OrderRequest(utc("2026-05-04T10:03:00+00:00"), "NQ", D("1"), D("10")))
    assert third.kind is DecisionKind.REJECT
    assert third.reason is Reason.MAX_TRADES


def test_trade_counter_resets_next_session() -> None:
    guard = _guard(max_trades_per_day=1)
    guard.on_event(_equity(0, "10000"))
    guard.on_event(OrderRequest(utc("2026-05-04T10:01:00+00:00"), "NQ", D("1"), D("10")))
    blocked = guard.on_event(OrderRequest(utc("2026-05-04T10:02:00+00:00"), "NQ", D("1"), D("10")))
    assert blocked.reason is Reason.MAX_TRADES
    guard.on_event(EquityUpdate(utc("2026-05-05T00:01:00+00:00"), D("10000")))
    allowed = guard.on_event(OrderRequest(utc("2026-05-05T00:02:00+00:00"), "NQ", D("1"), D("10")))
    assert allowed.kind is DecisionKind.ALLOW


def test_open_positions_survive_session_reset() -> None:
    guard = _guard(max_open_positions=1)
    guard.on_event(_equity(0, "10000"))
    guard.on_event(Fill(utc("2026-05-04T10:01:00+00:00"), "NQ", D("1")))
    guard.on_event(EquityUpdate(utc("2026-05-05T00:01:00+00:00"), D("10000")))
    decision = guard.on_event(
        OrderRequest(utc("2026-05-05T00:02:00+00:00"), "MNQ", D("1"), D("10"))
    )
    assert decision.kind is DecisionKind.REJECT
    assert decision.reason is Reason.MAX_OPEN_POSITIONS


def test_pct_limit_uses_session_baseline() -> None:
    guard = _guard(daily_loss_limit=None, daily_loss_limit_pct=D("2"))
    guard.on_event(_equity(0, "10000"))  # limit = 200
    decision = guard.on_event(_equity(1, "9800"))
    assert decision.kind is DecisionKind.FLATTEN_ALL


def test_naive_timestamp_rejected() -> None:
    guard = _guard()
    with pytest.raises(ValidationError, match="timezone-aware"):
        guard.on_event(EquityUpdate(datetime(2026, 5, 4, 10, 0), D("10000")))


def test_out_of_order_timestamp_rejected() -> None:
    guard = _guard()
    guard.on_event(_equity(5, "10000"))
    with pytest.raises(OutOfOrderEventError):
        guard.on_event(_equity(4, "10000"))


def test_equal_timestamp_is_allowed() -> None:
    guard = _guard()
    guard.on_event(_equity(5, "10000"))
    decision = guard.on_event(OrderRequest(utc("2026-05-04T10:05:00+00:00"), "NQ", D("1"), D("10")))
    assert decision.kind is DecisionKind.ALLOW


def test_non_event_rejected() -> None:
    guard = _guard()
    with pytest.raises(TypeError):
        guard.on_event("nope")


def test_non_config_rejected() -> None:
    with pytest.raises(TypeError):
        DailyRiskGuard("nope")


def test_negative_risk_amount_rejected() -> None:
    guard = _guard()
    guard.on_event(_equity(0, "10000"))
    with pytest.raises(ValidationError, match="risk_amount"):
        guard.on_event(OrderRequest(utc("2026-05-04T10:01:00+00:00"), "NQ", D("1"), D("-5")))


def test_decision_is_frozen() -> None:
    guard = _guard()
    decision = guard.on_event(_equity(0, "10000"))
    assert isinstance(decision, Decision)
    with pytest.raises(FrozenInstanceError):
        decision.kind = DecisionKind.ALLOW


def test_high_water_tracks_peak_equity() -> None:
    guard = _guard()
    guard.on_event(_equity(0, "10000"))
    guard.on_event(_equity(1, "10500"))
    guard.on_event(_equity(2, "10200"))
    assert guard.to_dict()["high_water"] == "10500"


def test_session_boundary_detected_by_reset_time() -> None:
    guard = _guard(session_reset_time=time(6, 0))
    guard.on_event(EquityUpdate(utc("2026-05-04T05:59:00+00:00"), D("10000")))
    guard.on_event(EquityUpdate(utc("2026-05-04T06:01:00+00:00"), D("9000")))
    # 06:01 UTC starts a new session, so 9000 is a fresh baseline, not a loss.
    assert guard.state is GuardState.ACTIVE
    assert guard.to_dict()["baseline"] == "9000"


def test_equity_update_after_lock_does_not_reflatten() -> None:
    guard = _guard()
    guard.on_event(_equity(0, "10000"))
    guard.on_event(_equity(1, "9000"))
    guard.on_event(_equity(2, "8000"))
    decision = guard.on_event(_equity(3, "7000"))
    assert decision.kind is DecisionKind.NONE


def test_out_of_order_after_session_reset() -> None:
    guard = _guard()
    guard.on_event(EquityUpdate(utc("2026-05-05T00:01:00+00:00"), D("10000")))
    with pytest.raises(OutOfOrderEventError):
        guard.on_event(EquityUpdate(utc("2026-05-04T23:59:00+00:00"), D("10000")))


def test_missing_ts_attribute_rejected() -> None:
    guard = _guard()

    class Bogus:
        pass

    with pytest.raises(TypeError):
        guard.on_event(Bogus())


def test_state_property_exposes_state() -> None:
    guard = _guard()
    assert guard.state is GuardState.ACTIVE


def test_fill_of_zero_net_removes_symbol() -> None:
    guard = _guard(max_open_positions=1)
    guard.on_event(_equity(0, "10000"))
    guard.on_event(Fill(utc("2026-05-04T10:01:00+00:00"), "NQ", D("2")))
    guard.on_event(Fill(utc("2026-05-04T10:02:00+00:00"), "NQ", D("-2")))
    assert guard.to_dict()["net_qty"] == {}


def test_signed_qty_delta_nets_positions() -> None:
    guard = _guard()
    guard.on_event(_equity(0, "10000"))
    guard.on_event(Fill(utc("2026-05-04T10:01:00+00:00"), "NQ", D("3")))
    guard.on_event(Fill(utc("2026-05-04T10:02:00+00:00"), "NQ", D("-1")))
    assert guard.to_dict()["net_qty"] == {"NQ": "2"}


def test_timestamps_are_normalised_across_timezones() -> None:
    guard = _guard()
    guard.on_event(EquityUpdate(datetime.fromisoformat("2026-05-04T12:00:00+02:00"), D("10000")))
    # 12:00+02:00 == 10:00Z; a later event at 10:01Z must not be "out of order".
    decision = guard.on_event(EquityUpdate(utc("2026-05-04T10:01:00+00:00"), D("9900")))
    assert decision.kind is DecisionKind.NONE


def test_warning_ratio_boundary_is_inclusive() -> None:
    guard = _guard(daily_loss_limit=D("1000"), warning_ratio=D("0.5"))
    guard.on_event(_equity(0, "10000"))
    guard.on_event(_equity(1, "9500"))
    assert guard.state is GuardState.WARNING
