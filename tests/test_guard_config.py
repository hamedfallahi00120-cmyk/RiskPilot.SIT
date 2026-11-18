"""Tests for guard configuration validation."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import time
from decimal import Decimal

import pytest

from riskpilot.errors import ValidationError
from riskpilot.guard import GuardConfig

D = Decimal


def test_requires_exactly_one_limit_kind() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        GuardConfig()


def test_rejects_both_limit_kinds() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        GuardConfig(daily_loss_limit=D("100"), daily_loss_limit_pct=D("1"))


@pytest.mark.parametrize("bad", [D("0"), D("-5")])
def test_absolute_limit_must_be_positive(bad: Decimal) -> None:
    with pytest.raises(ValidationError, match="daily_loss_limit"):
        GuardConfig(daily_loss_limit=bad)


@pytest.mark.parametrize("bad", [D("0"), D("100.1")])
def test_pct_limit_range(bad: Decimal) -> None:
    with pytest.raises(ValidationError, match="daily_loss_limit_pct"):
        GuardConfig(daily_loss_limit_pct=bad)


@pytest.mark.parametrize("bad", [D("0"), D("1"), D("-0.5")])
def test_warning_ratio_range(bad: Decimal) -> None:
    with pytest.raises(ValidationError, match="warning_ratio"):
        GuardConfig(daily_loss_limit=D("100"), warning_ratio=bad)


def test_warning_ratio_default() -> None:
    assert GuardConfig(daily_loss_limit=D("100")).warning_ratio == D("0.7")


@pytest.mark.parametrize("bad", [D("0"), D("-1")])
def test_trailing_drawdown_positive(bad: Decimal) -> None:
    with pytest.raises(ValidationError, match="trailing_drawdown"):
        GuardConfig(daily_loss_limit=D("100"), trailing_drawdown=bad)


@pytest.mark.parametrize("field", ["max_open_positions", "max_trades_per_day"])
@pytest.mark.parametrize("bad", [0, -1, True])
def test_int_caps_positive(field: str, bad: object) -> None:
    with pytest.raises(ValidationError, match=field):
        GuardConfig(daily_loss_limit=D("100"), **{field: bad})


def test_reset_time_must_be_naive() -> None:
    from datetime import UTC

    with pytest.raises(ValidationError, match="naive"):
        GuardConfig(daily_loss_limit=D("100"), session_reset_time=time(1, tzinfo=UTC))


def test_reset_time_must_be_time() -> None:
    with pytest.raises(ValidationError, match=r"datetime\.time"):
        GuardConfig(daily_loss_limit=D("100"), session_reset_time="01:00")


def test_unknown_timezone_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        GuardConfig(daily_loss_limit=D("100"), session_tz="Mars/Olympus")


def test_session_tz_must_be_str() -> None:
    with pytest.raises(ValidationError, match="IANA"):
        GuardConfig(daily_loss_limit=D("100"), session_tz=123)


def test_float_limit_rejected() -> None:
    with pytest.raises(TypeError):
        GuardConfig(daily_loss_limit=100.0)


def test_config_is_frozen() -> None:
    config = GuardConfig(daily_loss_limit=D("100"))
    with pytest.raises(FrozenInstanceError):
        config.warning_ratio = D("0.5")
