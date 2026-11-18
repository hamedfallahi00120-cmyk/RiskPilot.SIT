"""Tests for the exception hierarchy."""

from __future__ import annotations

import pytest

from riskpilot.errors import (
    ConfigError,
    OutOfOrderEventError,
    RiskPilotError,
    ValidationError,
)


@pytest.mark.parametrize(
    "exc_type",
    [ValidationError, ConfigError, OutOfOrderEventError],
)
def test_all_errors_derive_from_base(exc_type: type[RiskPilotError]) -> None:
    assert issubclass(exc_type, RiskPilotError)


def test_base_derives_from_exception() -> None:
    assert issubclass(RiskPilotError, Exception)


def test_error_carries_message() -> None:
    error = ValidationError("boom")
    assert str(error) == "boom"


def test_error_is_catchable_as_base() -> None:
    with pytest.raises(RiskPilotError):
        raise ConfigError("nope")
