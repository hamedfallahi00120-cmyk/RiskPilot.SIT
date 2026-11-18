"""DST-sensitive session boundary tests for America/Chicago.

Chicago springs forward on 2026-03-08 (02:00 -> 03:00 local) and falls back on
2026-11-01 (02:00 -> 01:00 local). Both are exercised with a reset time of
02:30, which sits inside the transition.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from riskpilot._session import resolve_boundary as _resolve_boundary
from riskpilot._session import session_start_utc as _session_start_utc
from riskpilot.guard import (
    DailyRiskGuard,
    DecisionKind,
    EquityUpdate,
    GuardConfig,
    GuardState,
)
from tests.conftest import utc

D = Decimal
CHICAGO = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")


def _guard() -> DailyRiskGuard:
    return DailyRiskGuard(
        GuardConfig(
            daily_loss_limit=D("1000"),
            session_reset_time=time(2, 30),
            session_tz="America/Chicago",
        )
    )


def test_gap_boundary_is_first_instant_after_gap() -> None:
    boundary = _resolve_boundary(datetime(2026, 3, 8, 2, 30), CHICAGO)
    # The wall-clock 02:30 does not exist; the boundary is the transition instant
    # 03:00-05:00 == 08:00Z.
    assert boundary.astimezone(UTC).isoformat() == "2026-03-08T08:00:00+00:00"


def test_gap_boundary_is_independent_of_requested_wall_time() -> None:
    early = _resolve_boundary(datetime(2026, 3, 8, 2, 0), CHICAGO)
    late = _resolve_boundary(datetime(2026, 3, 8, 2, 59), CHICAGO)
    assert early == late


def test_overlap_boundary_is_first_occurrence() -> None:
    boundary = _resolve_boundary(datetime(2026, 11, 1, 1, 30), CHICAGO)
    # 01:30 occurs twice; the first occurrence is 01:30-05:00 == 06:30Z.
    assert boundary.astimezone(UTC).isoformat() == "2026-11-01T06:30:00+00:00"


def test_normal_time_resolves_to_itself() -> None:
    boundary = _resolve_boundary(datetime(2026, 6, 1, 2, 30), CHICAGO)
    assert boundary.astimezone(UTC).isoformat() == "2026-06-01T07:30:00+00:00"


def test_spring_forward_session_boundary() -> None:
    # At 07:00Z local time is 01:00 CST, before the 08:00Z gap boundary, so the
    # active session started the previous day at 02:30 CST (08:30Z).
    before = _session_start_utc(utc("2026-03-08T07:00:00+00:00"), time(2, 30), CHICAGO)
    assert before.astimezone(UTC).isoformat() == "2026-03-07T08:30:00+00:00"
    after = _session_start_utc(utc("2026-03-08T09:00:00+00:00"), time(2, 30), CHICAGO)
    assert after.astimezone(UTC).isoformat() == "2026-03-08T08:00:00+00:00"


def test_fall_back_session_boundary() -> None:
    before = _session_start_utc(utc("2026-11-01T08:00:00+00:00"), time(2, 30), CHICAGO)
    assert before.astimezone(UTC).isoformat() == "2026-10-31T07:30:00+00:00"
    after = _session_start_utc(utc("2026-11-01T09:00:00+00:00"), time(2, 30), CHICAGO)
    assert after.astimezone(UTC).isoformat() == "2026-11-01T08:30:00+00:00"


def test_spring_forward_resets_session_at_gap_boundary() -> None:
    guard = _guard()
    guard.on_event(EquityUpdate(utc("2026-03-08T07:00:00+00:00"), D("10000")))
    guard.on_event(EquityUpdate(utc("2026-03-08T07:30:00+00:00"), D("9000")))
    assert guard.state is GuardState.LOCKED

    # 08:00Z is the resolved boundary: a new session begins, state resets.
    guard.on_event(EquityUpdate(utc("2026-03-08T08:00:00+00:00"), D("9000")))
    assert guard.state is GuardState.ACTIVE
    assert guard.to_dict()["baseline"] == "9000"


def test_fall_back_resets_session_at_first_occurrence() -> None:
    guard = _guard()
    guard.on_event(EquityUpdate(utc("2026-11-01T08:00:00+00:00"), D("10000")))
    guard.on_event(EquityUpdate(utc("2026-11-01T08:10:00+00:00"), D("9000")))
    assert guard.state is GuardState.LOCKED

    guard.on_event(EquityUpdate(utc("2026-11-01T08:30:00+00:00"), D("9000")))
    assert guard.state is GuardState.ACTIVE


def test_dst_transition_does_not_break_ordering() -> None:
    guard = _guard()
    guard.on_event(EquityUpdate(utc("2026-03-08T07:59:00+00:00"), D("10000")))
    decision = guard.on_event(EquityUpdate(utc("2026-03-08T08:31:00+00:00"), D("10000")))
    assert decision.kind is DecisionKind.NONE


def test_session_length_across_spring_forward() -> None:
    start = _session_start_utc(utc("2026-03-09T12:00:00+00:00"), time(2, 30), CHICAGO)
    previous = _session_start_utc(utc("2026-03-08T12:00:00+00:00"), time(2, 30), CHICAGO)
    # 2026-03-08's boundary is the 08:00Z gap instant; the next is 07:30Z (CDT).
    assert start - previous == timedelta(hours=23, minutes=30)


def test_session_length_is_24h_across_fall_back() -> None:
    # 01:30 lies inside the repeated hour, so the elapsed UTC time is 25h.
    start = _session_start_utc(utc("2026-11-02T12:00:00+00:00"), time(1, 30), CHICAGO)
    previous = _session_start_utc(utc("2026-11-01T12:00:00+00:00"), time(1, 30), CHICAGO)
    assert start - previous == timedelta(hours=25)


def test_fall_back_boundary_outside_repeated_hour_is_24h() -> None:
    # 02:30 is after the 02:00 fall-back, so both boundaries sit at 08:30Z.
    start = _session_start_utc(utc("2026-11-02T12:00:00+00:00"), time(2, 30), CHICAGO)
    previous = _session_start_utc(utc("2026-11-01T12:00:00+00:00"), time(2, 30), CHICAGO)
    assert start - previous == timedelta(hours=24)


def test_reset_at_midnight_unaffected_by_dst() -> None:
    guard = DailyRiskGuard(
        GuardConfig(
            daily_loss_limit=D("1000"), session_reset_time=time(0, 0), session_tz="America/Chicago"
        )
    )
    guard.on_event(EquityUpdate(utc("2026-03-08T05:00:00+00:00"), D("10000")))
    guard.on_event(EquityUpdate(utc("2026-03-08T05:30:00+00:00"), D("9000")))
    assert guard.state is GuardState.LOCKED
    # 05:00Z next day is midnight CDT -> new session.
    guard.on_event(EquityUpdate(utc("2026-03-09T05:00:00+00:00"), D("10000")))
    assert guard.state is GuardState.ACTIVE


@pytest.mark.parametrize("date", ["2026-03-08", "2026-11-01"])
def test_dst_days_produce_single_boundary_per_day(date: str) -> None:
    year, month, day = (int(part) for part in date.split("-"))
    boundaries = {
        _resolve_boundary(datetime(year, month, day, 2, 30), CHICAGO).astimezone(UTC).isoformat()
    }
    assert len(boundaries) == 1
