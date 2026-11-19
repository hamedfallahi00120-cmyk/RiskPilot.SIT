"""Shared fixtures and deterministic helpers for the riskpilot test-suite."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from riskpilot import GuardConfig, InstrumentSpec

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"

D = Decimal


@pytest.fixture(scope="session")
def examples() -> Path:
    """Path to the repository ``examples`` directory."""
    return EXAMPLES


@pytest.fixture(scope="session")
def eurusd() -> InstrumentSpec:
    """EURUSD spec from the shipped examples."""
    return InstrumentSpec(
        symbol="EURUSD",
        tick_size=D("0.00001"),
        tick_value=D("1.00"),
        min_qty=D("0.01"),
        qty_step=D("0.01"),
        max_qty=D("100"),
    )


@pytest.fixture(scope="session")
def nq() -> InstrumentSpec:
    """NQ (full-size Nasdaq futures) spec from the shipped examples."""
    return InstrumentSpec(
        symbol="NQ",
        tick_size=D("0.25"),
        tick_value=D("5.00"),
        min_qty=D("1"),
        qty_step=D("1"),
        max_qty=D("50"),
    )


@pytest.fixture(scope="session")
def mnq() -> InstrumentSpec:
    """MNQ (micro Nasdaq futures) spec from the shipped examples."""
    return InstrumentSpec(
        symbol="MNQ",
        tick_size=D("0.25"),
        tick_value=D("0.50"),
        min_qty=D("1"),
        qty_step=D("1"),
        max_qty=D("200"),
    )


@pytest.fixture
def guard_config() -> GuardConfig:
    """Absolute-loss guard config used by most guard tests."""
    return GuardConfig(daily_loss_limit=D("1000"), session_tz="UTC")


def utc(*args: int) -> datetime:
    """Build an aware UTC datetime for a compact test call site."""
    return datetime(*args, tzinfo=UTC)
