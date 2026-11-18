"""Shared fixtures and helpers for the riskpilot test-suite."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from riskpilot import InstrumentSpec

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = REPO_ROOT / "examples"


@pytest.fixture
def eurusd() -> InstrumentSpec:
    return InstrumentSpec(
        symbol="EURUSD",
        tick_size=Decimal("0.00001"),
        tick_value=Decimal("1.00"),
        min_qty=Decimal("0.01"),
        qty_step=Decimal("0.01"),
        max_qty=Decimal("100"),
    )


@pytest.fixture
def nq() -> InstrumentSpec:
    return InstrumentSpec(
        symbol="NQ",
        tick_size=Decimal("0.25"),
        tick_value=Decimal("5.00"),
        min_qty=Decimal("1"),
        qty_step=Decimal("1"),
        max_qty=Decimal("50"),
    )


@pytest.fixture
def mnq() -> InstrumentSpec:
    return InstrumentSpec(
        symbol="MNQ",
        tick_size=Decimal("0.25"),
        tick_value=Decimal("0.50"),
        min_qty=Decimal("1"),
        qty_step=Decimal("1"),
        max_qty=Decimal("200"),
    )


def utc(text: str) -> datetime:
    """Parse an ISO-8601 string into a timezone-aware UTC datetime."""
    parsed = datetime.fromisoformat(text)
    assert parsed.tzinfo is not None
    return parsed.astimezone(UTC)
