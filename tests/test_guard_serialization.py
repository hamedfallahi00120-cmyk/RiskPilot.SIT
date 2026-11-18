"""Serialization tests for :class:`riskpilot.DailyRiskGuard`."""

from __future__ import annotations

import json
import random
from datetime import time
from decimal import Decimal

import pytest

from riskpilot.errors import ValidationError
from riskpilot.guard import (
    DailyRiskGuard,
    DecisionKind,
    EquityUpdate,
    Fill,
    GuardConfig,
    OrderRequest,
    Reason,
)
from tests.conftest import utc

D = Decimal


def _config() -> GuardConfig:
    return GuardConfig(
        daily_loss_limit=D("1000"),
        trailing_drawdown=D("2000"),
        max_open_positions=3,
        max_trades_per_day=5,
        session_reset_time=time(0, 0),
        session_tz="America/Chicago",
    )


def _events() -> list[EquityUpdate | OrderRequest | Fill]:
    return [
        EquityUpdate(utc("2026-05-04T05:00:00+00:00"), D("10000")),
        OrderRequest(utc("2026-05-04T05:01:00+00:00"), "NQ", D("1"), D("50")),
        Fill(utc("2026-05-04T05:02:00+00:00"), "NQ", D("1")),
        EquityUpdate(utc("2026-05-04T05:03:00+00:00"), D("9800")),
        OrderRequest(utc("2026-05-04T05:04:00+00:00"), "MNQ", D("1"), D("50")),
        EquityUpdate(utc("2026-05-04T05:05:00+00:00"), D("9700")),
    ]


def test_to_dict_is_json_serialisable() -> None:
    guard = DailyRiskGuard(_config())
    for event in _events():
        guard.on_event(event)
    payload = guard.to_dict()
    encoded = json.dumps(payload)
    assert json.loads(encoded) == payload


def test_to_dict_encodes_decimals_as_strings() -> None:
    guard = DailyRiskGuard(_config())
    guard.on_event(EquityUpdate(utc("2026-05-04T05:00:00+00:00"), D("10000.55")))
    payload = guard.to_dict()
    assert payload["baseline"] == "10000.55"
    assert isinstance(payload["baseline"], str)
    assert isinstance(payload["net_qty"], dict)


def test_round_trip_preserves_behaviour() -> None:
    original = DailyRiskGuard(_config())
    for event in _events():
        original.on_event(event)

    restored = DailyRiskGuard.from_dict(_config(), original.to_dict())
    assert restored.to_dict() == original.to_dict()

    subsequent = [
        EquityUpdate(utc("2026-05-04T05:06:00+00:00"), D("9600")),
        OrderRequest(utc("2026-05-04T05:07:00+00:00"), "NQ", D("1"), D("10")),
        Fill(utc("2026-05-04T05:08:00+00:00"), "MNQ", D("-1")),
    ]
    for event in subsequent:
        assert restored.on_event(event) == original.on_event(event)


def test_round_trip_property_random_sequences() -> None:
    rng = random.Random(4242)
    for _ in range(50):
        config = GuardConfig(
            daily_loss_limit=D("1000"),
            session_reset_time=time(0, 0),
            session_tz="UTC",
        )
        original = DailyRiskGuard(config)
        for minute in range(1, rng.randint(2, 16)):
            choice = rng.random()
            ts = utc(f"2026-05-04T10:{minute:02d}:00+00:00")
            if choice < 0.5:
                event: EquityUpdate | OrderRequest | Fill = EquityUpdate(
                    ts, D(str(rng.randint(8000, 12000)))
                )
            elif choice < 0.75:
                event = OrderRequest(ts, "NQ", D("1"), D(str(rng.randint(1, 100))))
            else:
                event = Fill(ts, "NQ", D(str(rng.randint(-3, 3))))
            original.on_event(event)
        restored = DailyRiskGuard.from_dict(config, json.loads(json.dumps(original.to_dict())))
        assert restored.to_dict() == original.to_dict()


def test_from_dict_rejects_bad_field_types() -> None:
    config = _config()
    good = DailyRiskGuard(config).to_dict()

    with pytest.raises(ValidationError, match="net_qty"):
        DailyRiskGuard.from_dict(config, {**good, "net_qty": "nope"})
    with pytest.raises(ValidationError, match="trades_today"):
        DailyRiskGuard.from_dict(config, {**good, "trades_today": "x"})
    with pytest.raises(ValidationError, match="locked_announced"):
        DailyRiskGuard.from_dict(config, {**good, "locked_announced": 1})
    with pytest.raises(ValidationError, match="session_start"):
        DailyRiskGuard.from_dict(config, {**good, "session_start": 123})
    with pytest.raises(ValidationError, match="baseline"):
        DailyRiskGuard.from_dict(config, {**good, "baseline": 1.5})


def test_from_dict_unknown_state_rejected() -> None:
    config = _config()
    good = DailyRiskGuard(config).to_dict()
    with pytest.raises(ValueError):
        DailyRiskGuard.from_dict(config, {**good, "state": "BROKEN"})


def test_restored_guard_continues_lock_state() -> None:
    config = _config()
    original = DailyRiskGuard(config)
    original.on_event(EquityUpdate(utc("2026-05-04T05:00:00+00:00"), D("10000")))
    original.on_event(EquityUpdate(utc("2026-05-04T05:01:00+00:00"), D("8900")))

    restored = DailyRiskGuard.from_dict(config, original.to_dict())
    decision = restored.on_event(
        OrderRequest(utc("2026-05-04T05:02:00+00:00"), "NQ", D("1"), D("10"))
    )
    assert decision.kind is DecisionKind.REJECT
    assert decision.reason is Reason.LOCKED
    assert restored.state is original.state
