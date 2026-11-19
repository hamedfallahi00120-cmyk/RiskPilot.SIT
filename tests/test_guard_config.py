"""Tests for GuardConfig validation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, time, timedelta, timezone
from decimal import Decimal
from typing import cast

import pytest

from riskpilot import ConfigError, GuardConfig, ValidationError

D = Decimal


def build_guard(kwargs: dict[str, object]) -> GuardConfig:
    """Construct a GuardConfig through a dynamic signature (tests pass wrong types)."""
    constructor = cast(Callable[..., GuardConfig], GuardConfig)
    return constructor(**kwargs)


def test_defaults_are_applied() -> None:
    config = GuardConfig(daily_loss_limit=D("500"))
    assert config.warning_ratio == D("0.7")
    assert config.session_reset_time == time(0, 0)
    assert config.session_tz == "UTC"
    assert config.trailing_drawdown is None
    assert config.max_open_positions is None
    assert config.max_trades_per_day is None
    assert config.is_percentage_limit is False


def test_percentage_mode_flag() -> None:
    assert GuardConfig(daily_loss_limit_pct=D("1.5")).is_percentage_limit is True


def test_config_is_frozen() -> None:
    config = GuardConfig(daily_loss_limit=D("500"))
    with pytest.raises(AttributeError):
        config.warning_ratio = D("0.5")


def test_both_limits_rejected() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        GuardConfig(daily_loss_limit=D("500"), daily_loss_limit_pct=D("1"))


def test_neither_limit_rejected() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        GuardConfig()


@pytest.mark.parametrize("limit", [D("0"), D("-100")])
def test_non_positive_absolute_limit_rejected(limit: Decimal) -> None:
    with pytest.raises(ValidationError, match="daily_loss_limit"):
        GuardConfig(daily_loss_limit=limit)


@pytest.mark.parametrize("pct", [D("0"), D("-1"), D("100.5")])
def test_percentage_limit_range(pct: Decimal) -> None:
    with pytest.raises(ValidationError, match="daily_loss_limit_pct"):
        GuardConfig(daily_loss_limit_pct=pct)


@pytest.mark.parametrize("ratio", [D("0"), D("1"), D("-0.2"), D("1.5")])
def test_warning_ratio_range(ratio: Decimal) -> None:
    with pytest.raises(ValidationError, match="warning_ratio"):
        GuardConfig(daily_loss_limit=D("100"), warning_ratio=ratio)


def test_warning_ratio_float_rejected() -> None:
    with pytest.raises(TypeError, match="float"):
        build_guard({"daily_loss_limit": D("100"), "warning_ratio": 0.7})


@pytest.mark.parametrize("drawdown", [D("0"), D("-5")])
def test_trailing_drawdown_must_be_positive(drawdown: Decimal) -> None:
    with pytest.raises(ValidationError, match="trailing_drawdown"):
        GuardConfig(daily_loss_limit=D("100"), trailing_drawdown=drawdown)


@pytest.mark.parametrize("field", ["max_open_positions", "max_trades_per_day"])
@pytest.mark.parametrize("value", [0, -1, True, "3", 2.5])
def test_integer_limits_validated(field: str, value: object) -> None:
    kwargs: dict[str, object] = {"daily_loss_limit": D("100"), field: value}
    with pytest.raises((ValidationError, TypeError)):
        build_guard(kwargs)


def test_aware_reset_time_rejected() -> None:
    with pytest.raises(ValidationError, match="naive local time"):
        GuardConfig(daily_loss_limit=D("100"), session_reset_time=time(9, tzinfo=UTC))


def test_reset_time_must_be_a_time() -> None:
    with pytest.raises(ValidationError, match=r"datetime\.time"):
        build_guard({"daily_loss_limit": D("100"), "session_reset_time": "09:30"})


def test_unknown_timezone_rejected() -> None:
    with pytest.raises(ConfigError, match="IANA timezone"):
        GuardConfig(daily_loss_limit=D("100"), session_tz="Mars/Olympus_Mons")


def test_empty_timezone_rejected() -> None:
    with pytest.raises(ConfigError, match="IANA timezone"):
        GuardConfig(daily_loss_limit=D("100"), session_tz="")


def test_timezone_with_offset_rejected() -> None:
    with pytest.raises(ConfigError):
        GuardConfig(daily_loss_limit=D("100"), session_tz="+03:00")


def test_zoneinfo_returns_zone() -> None:
    zone = GuardConfig(daily_loss_limit=D("100"), session_tz="America/Chicago").zoneinfo()
    assert zone.utcoffset(None) is None
    assert zone.key == "America/Chicago"


def test_fixed_offset_timezone_is_not_iana() -> None:
    with pytest.raises(ConfigError):
        GuardConfig(
            daily_loss_limit=D("100"),
            session_tz=timezone(timedelta(hours=2)).tzname(None) or "",
        )
