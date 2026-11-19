"""DST-sensitive session boundary tests for America/Chicago."""

from __future__ import annotations

from datetime import UTC, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from riskpilot import DailyRiskGuard, DecisionKind, EquityUpdate, GuardConfig
from riskpilot._session import boundary_utc, session_start

D = Decimal
CHICAGO = ZoneInfo("America/Chicago")


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


@pytest.mark.parametrize(
    ("local_date_part", "reset", "expected"),
    [
        # 2026-03-08: 02:30 local does not exist -> first instant after the gap (08:00Z)
        ((2026, 3, 8), time(2, 30), utc(2026, 3, 8, 8, 0)),
        ((2026, 3, 8), time(3, 0), utc(2026, 3, 8, 8, 0)),
        ((2026, 3, 8), time(1, 59), utc(2026, 3, 8, 7, 59)),
        ((2026, 3, 8), time(0, 0), utc(2026, 3, 8, 6, 0)),
        # 2026-11-01: 01:30 local happens twice -> first occurrence (06:30Z)
        ((2026, 11, 1), time(1, 30), utc(2026, 11, 1, 6, 30)),
        ((2026, 11, 1), time(2, 30), utc(2026, 11, 1, 8, 30)),
        ((2026, 11, 1), time(0, 30), utc(2026, 11, 1, 5, 30)),
    ],
)
def test_boundary_utc_handles_dst_edges(
    local_date_part: tuple[int, int, int], reset: time, expected: datetime
) -> None:
    from datetime import date

    assert boundary_utc(date(*local_date_part), reset, CHICAGO) == expected


def test_session_start_walks_back_before_boundary() -> None:
    instant = utc(2026, 3, 8, 7, 0)  # 01:00 CST, before the 08:00Z boundary
    assert session_start(instant, time(2, 30), CHICAGO) == utc(2026, 3, 7, 8, 30)


def test_session_start_at_exact_boundary_belongs_to_new_session() -> None:
    instant = utc(2026, 3, 8, 8, 0)
    assert session_start(instant, time(2, 30), CHICAGO) == instant


def test_spring_forward_session_spans_gap() -> None:
    config = GuardConfig(
        daily_loss_limit=D("1000"),
        session_reset_time=time(2, 30),
        session_tz="America/Chicago",
    )
    guard = DailyRiskGuard(config)
    guard.on_event(EquityUpdate(ts=utc(2026, 3, 8, 8, 1), equity=D("10000")))
    assert guard.session_start == utc(2026, 3, 8, 8, 0)
    guard.on_event(EquityUpdate(ts=utc(2026, 3, 8, 20, 0), equity=D("9800")))
    assert guard.session_start == utc(2026, 3, 8, 8, 0)
    rolled = guard.on_event(EquityUpdate(ts=utc(2026, 3, 9, 7, 30), equity=D("9800")))
    assert rolled.reason.value == "SESSION_RESET"
    assert guard.session_start == utc(2026, 3, 9, 7, 30)


def test_fall_back_first_occurrence_is_used() -> None:
    config = GuardConfig(
        daily_loss_limit=D("1000"),
        session_reset_time=time(1, 30),
        session_tz="America/Chicago",
    )
    guard = DailyRiskGuard(config)
    guard.on_event(EquityUpdate(ts=utc(2026, 11, 1, 5, 0), equity=D("10000")))
    # 05:30Z is 00:30 CDT, so the session started on 2026-10-31 at 06:30Z.
    assert guard.session_start == utc(2026, 10, 31, 6, 30)
    guard.on_event(EquityUpdate(ts=utc(2026, 11, 1, 6, 30), equity=D("10000")))
    assert guard.session_start == utc(2026, 11, 1, 6, 30)


def test_second_occurrence_of_overlap_is_same_session() -> None:
    config = GuardConfig(
        daily_loss_limit=D("1000"),
        session_reset_time=time(1, 30),
        session_tz="America/Chicago",
    )
    guard = DailyRiskGuard(config)
    guard.on_event(EquityUpdate(ts=utc(2026, 11, 1, 6, 30), equity=D("10000")))
    # 07:30Z is 01:30 CST, the *second* 01:30 of the day: still the same session.
    decision = guard.on_event(EquityUpdate(ts=utc(2026, 11, 1, 7, 30), equity=D("9900")))
    assert decision.kind is DecisionKind.NONE
    assert decision.reason.value == "EQUITY_UPDATE"
    assert guard.session_start == utc(2026, 11, 1, 6, 30)


def test_session_length_differs_across_dst() -> None:
    spring = utc(2026, 3, 9, 7, 30) - utc(2026, 3, 8, 8, 0)
    fall = utc(2026, 11, 1, 7, 30) - utc(2026, 10, 31, 7, 30)
    assert spring.total_seconds() == 23.5 * 3600
    assert fall.total_seconds() == 24 * 3600


def test_dst_day_example_file_breaches(
    examples: object, capsys: pytest.CaptureFixture[str]
) -> None:
    from riskpilot.cli import main

    code = main(
        [
            "simulate",
            "--config",
            str(examples / "config_chicago.toml"),
            "--events",
            str(examples / "dst_day.csv"),
        ]
    )
    assert code == 3
    out = capsys.readouterr().out
    assert out.startswith("Generated at ")
    assert "final state: LOCKED" in out
