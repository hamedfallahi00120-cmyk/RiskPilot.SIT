"""Tests for the remaining error and validation paths (H3, H4 boundary rules)."""

from __future__ import annotations

from datetime import time
from decimal import Decimal
from pathlib import Path

import pytest

from riskpilot import InstrumentSpec, size_position
from riskpilot.errors import ConfigError, OutOfOrderEventError, ValidationError
from riskpilot.guard import DailyRiskGuard, EquityUpdate, Fill, GuardConfig, OrderRequest
from riskpilot.instruments import _as_decimal
from tests.conftest import utc

D = Decimal


def _spec() -> InstrumentSpec:
    return InstrumentSpec(
        symbol="EURUSD",
        tick_size=D("0.00001"),
        tick_value=D("1.00"),
        min_qty=D("0.01"),
        qty_step=D("0.01"),
        max_qty=D("100"),
    )


def _config() -> GuardConfig:
    return GuardConfig(daily_loss_limit=D("1000"), session_tz="UTC")


# --- float rejection (H3) ---------------------------------------------------


@pytest.mark.parametrize("bad", [1.0, 0.5, -2.25])
def test_instrument_rejects_float(bad: float) -> None:
    with pytest.raises(TypeError, match="tick_size must be Decimal"):
        InstrumentSpec(
            symbol="X",
            tick_size=bad,
            tick_value=D("1"),
            min_qty=D("1"),
            qty_step=D("1"),
            max_qty=D("10"),
        )


def test_as_decimal_rejects_unsupported_type() -> None:
    with pytest.raises(TypeError, match="must be Decimal"):
        _as_decimal(object(), "tick_size")


def test_to_decimal_rejects_unsupported_type() -> None:
    from riskpilot._decimal import to_decimal

    with pytest.raises(TypeError, match="must be Decimal"):
        to_decimal(object(), "equity")


def test_to_decimal_accepts_int_and_decimal() -> None:
    from riskpilot._decimal import to_decimal

    assert to_decimal(5, "equity") == D("5")
    assert to_decimal(D("5.5"), "equity") == D("5.5")


def test_size_position_rejects_float_equity() -> None:
    with pytest.raises(TypeError, match="equity must be Decimal"):
        size_position(
            equity=1.0,
            risk_pct=D("1"),
            entry=D("1.1"),
            stop=D("1.09"),
            spec=_spec(),
        )


def test_size_position_rejects_non_spec() -> None:
    with pytest.raises(TypeError, match="spec must be an InstrumentSpec"):
        size_position(
            equity=D("1000"),
            risk_pct=D("1"),
            entry=D("1.1"),
            stop=D("1.09"),
            spec="EURUSD",
        )


# --- guard event validation -------------------------------------------------


def test_guard_rejects_naive_timestamp() -> None:
    from datetime import datetime

    guard = DailyRiskGuard(_config())
    with pytest.raises(ValidationError, match="timezone-aware"):
        guard.on_event(EquityUpdate(datetime(2026, 5, 4, 5, 0), D("10000")))


def test_guard_rejects_non_event_object() -> None:
    guard = DailyRiskGuard(_config())
    with pytest.raises(TypeError, match="EquityUpdate"):
        guard.on_event("not an event")


def test_guard_requires_guard_config() -> None:
    with pytest.raises(TypeError, match="config must be a GuardConfig"):
        DailyRiskGuard("nope")


def test_guard_rejects_out_of_order_events() -> None:
    guard = DailyRiskGuard(_config())
    guard.on_event(EquityUpdate(utc("2026-05-04T05:05:00+00:00"), D("10000")))
    with pytest.raises(OutOfOrderEventError, match="older than previous"):
        guard.on_event(EquityUpdate(utc("2026-05-04T05:00:00+00:00"), D("9900")))


def test_guard_rejects_negative_order_risk_amount() -> None:
    guard = DailyRiskGuard(_config())
    guard.on_event(EquityUpdate(utc("2026-05-04T05:00:00+00:00"), D("10000")))
    with pytest.raises(ValidationError, match="risk_amount must be >= 0"):
        guard.on_event(OrderRequest(utc("2026-05-04T05:01:00+00:00"), "NQ", D("1"), D("-5")))


def test_guard_fill_coerces_float_delta_via_type_error() -> None:
    guard = DailyRiskGuard(_config())
    with pytest.raises(TypeError, match="qty_delta must be Decimal"):
        guard.on_event(Fill(utc("2026-05-04T05:00:00+00:00"), "NQ", 1.0))


# --- guard config validation ------------------------------------------------


def test_config_rejects_both_limits() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        GuardConfig(daily_loss_limit=D("1"), daily_loss_limit_pct=D("1"))


def test_config_rejects_no_limit() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        GuardConfig()


def test_config_rejects_negative_limit() -> None:
    with pytest.raises(ValidationError, match="daily_loss_limit must be positive"):
        GuardConfig(daily_loss_limit=D("-1"))


def test_config_rejects_bad_pct() -> None:
    with pytest.raises(ValidationError, match="daily_loss_limit_pct"):
        GuardConfig(daily_loss_limit_pct=D("101"))


def test_config_rejects_bad_warning_ratio() -> None:
    with pytest.raises(ValidationError, match="warning_ratio"):
        GuardConfig(daily_loss_limit=D("1"), warning_ratio=D("1"))


def test_config_rejects_bad_trailing_drawdown() -> None:
    with pytest.raises(ValidationError, match="trailing_drawdown"):
        GuardConfig(daily_loss_limit=D("1"), trailing_drawdown=D("0"))


@pytest.mark.parametrize("field", ["max_open_positions", "max_trades_per_day"])
def test_config_rejects_bad_int_caps(field: str) -> None:
    with pytest.raises(ValidationError, match=f"{field} must be an int"):
        GuardConfig(daily_loss_limit=D("1"), **{field: 0})


def test_config_rejects_aware_reset_time() -> None:
    from datetime import UTC, datetime

    aware = datetime(2026, 1, 1, tzinfo=UTC).timetz()
    with pytest.raises(ValidationError, match="naive"):
        GuardConfig(daily_loss_limit=D("1"), session_reset_time=aware)


def test_config_rejects_unknown_timezone() -> None:
    with pytest.raises(ValidationError, match="unknown IANA timezone"):
        GuardConfig(daily_loss_limit=D("1"), session_tz="Mars/Olympus")


def test_config_rejects_non_time_reset() -> None:
    with pytest.raises(ValidationError, match=r"datetime\.time"):
        GuardConfig(daily_loss_limit=D("1"), session_reset_time="00:00")


# --- config loader error paths ----------------------------------------------


def _write(tmp_path: Path, text: str, name: str = "c.toml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_load_config_reports_unreadable_path() -> None:
    from riskpilot.config import load_config

    with pytest.raises(ConfigError, match="not found"):
        load_config(Path("/nonexistent/does-not-exist.toml"))


def test_load_config_rejects_non_table_guard(tmp_path: Path) -> None:
    from riskpilot.config import load_config

    text = 'default_risk_pct = "1"\nguard = "x"\n'
    with pytest.raises(ConfigError, match="guard: expected a table"):
        load_config(_write(tmp_path, text))


def test_load_config_rejects_non_string_reset_time(tmp_path: Path) -> None:
    from riskpilot.config import load_config

    text = 'default_risk_pct = "1"\n\n[guard]\ndaily_loss_limit = "1"\nsession_reset_time = 5\n'
    with pytest.raises(ConfigError, match="session_reset_time: expected string"):
        load_config(_write(tmp_path, text))


def test_load_config_rejects_aware_reset_time(tmp_path: Path) -> None:
    from riskpilot.config import load_config

    text = (
        'default_risk_pct = "1"\n\n[guard]\ndaily_loss_limit = "1"\n'
        'session_reset_time = "02:00:00+05:00"\n'
    )
    with pytest.raises(ConfigError, match="naive"):
        load_config(_write(tmp_path, text))


def test_load_config_rejects_non_string_tz(tmp_path: Path) -> None:
    from riskpilot.config import load_config

    text = 'default_risk_pct = "1"\n\n[guard]\ndaily_loss_limit = "1"\nsession_tz = 5\n'
    with pytest.raises(ConfigError, match="session_tz: expected string"):
        load_config(_write(tmp_path, text))


def test_load_config_rejects_bad_int_cap(tmp_path: Path) -> None:
    from riskpilot.config import load_config

    text = 'default_risk_pct = "1"\n\n[guard]\ndaily_loss_limit = "1"\nmax_open_positions = 0\n'
    with pytest.raises(ConfigError, match="max_open_positions: expected integer >= 1"):
        load_config(_write(tmp_path, text))


def test_load_config_rejects_non_finite_decimal(tmp_path: Path) -> None:
    from riskpilot.config import load_config

    text = 'default_risk_pct = "inf"\n\n[guard]\ndaily_loss_limit = "1"\n'
    with pytest.raises(ConfigError, match="finite decimal"):
        load_config(_write(tmp_path, text))


def test_load_config_rejects_non_numeric_decimal(tmp_path: Path) -> None:
    from riskpilot.config import load_config

    text = 'default_risk_pct = "abc"\n\n[guard]\ndaily_loss_limit = "1"\n'
    with pytest.raises(ConfigError, match="expected decimal string"):
        load_config(_write(tmp_path, text))


def test_load_instruments_rejects_non_table(tmp_path: Path) -> None:
    from riskpilot.config import load_instruments

    with pytest.raises(ConfigError, match="expected a table"):
        load_instruments(_write(tmp_path, "EURUSD = 5\n"))


def test_load_instruments_rejects_invalid_spec(tmp_path: Path) -> None:
    from riskpilot.config import load_instruments

    text = '[X]\ntick_size = "1"\ntick_value = "1"\nmin_qty = "3"\nqty_step = "2"\nmax_qty = "10"\n'
    with pytest.raises(ConfigError, match="must be a multiple of qty_step"):
        load_instruments(_write(tmp_path, text))


def test_load_instruments_rejects_missing_key(tmp_path: Path) -> None:
    from riskpilot.config import load_instruments

    text = '[X]\ntick_size = "1"\ntick_value = "1"\n'
    with pytest.raises(ConfigError, match="min_qty: missing required key"):
        load_instruments(_write(tmp_path, text))


# --- session boundary helper ------------------------------------------------


def test_session_start_uses_previous_day_when_boundary_ahead() -> None:
    from zoneinfo import ZoneInfo

    from riskpilot._session import session_start_utc

    start = session_start_utc(utc("2026-05-04T05:00:00+00:00"), time(0, 0), ZoneInfo("UTC"))
    assert start == utc("2026-05-04T00:00:00+00:00")
