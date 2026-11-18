"""Shared fixtures and helpers for the riskpilot test-suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from riskpilot import InstrumentSpec

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = REPO_ROOT / "examples"


@pytest.fixture
def eurusd() -> InstrumentSpec:
    return InstrumentSpec(
        symbol="EURUSD",
        tick_size="0.00001",
        tick_value="1.00",
        min_qty="0.01",
        qty_step="0.01",
        max_qty="100",
    )


@pytest.fixture
def nq() -> InstrumentSpec:
    return InstrumentSpec(
        symbol="NQ",
        tick_size="0.25",
        tick_value="5.00",
        min_qty="1",
        qty_step="1",
        max_qty="50",
    )


@pytest.fixture
def mnq() -> InstrumentSpec:
    return InstrumentSpec(
        symbol="MNQ",
        tick_size="0.25",
        tick_value="0.50",
        min_qty="1",
        qty_step="1",
        max_qty="200",
    )
