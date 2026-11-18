"""Ensure docs/CONFIG.md documents exactly the config dataclass fields."""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from riskpilot.config import AppConfig
from riskpilot.guard import GuardConfig
from riskpilot.instruments import InstrumentSpec

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DOC = REPO_ROOT / "docs" / "CONFIG.md"

# Documentation key -> dataclass field, for fields whose doc name differs.
_ALIASES = {
    "instruments.<symbol>.tick_size": "tick_size",
    "instruments.<symbol>.tick_value": "tick_value",
    "instruments.<symbol>.min_qty": "min_qty",
    "instruments.<symbol>.qty_step": "qty_step",
    "instruments.<symbol>.max_qty": "max_qty",
}


def _documented_keys() -> set[str]:
    text = CONFIG_DOC.read_text(encoding="utf-8")
    keys: set[str] = set()
    for line in text.splitlines():
        match = re.match(r"\|\s*`([^`]+)`\s*\|", line)
        if match:
            keys.add(match.group(1))
    return keys


def _dataclass_keys() -> set[str]:
    keys: set[str] = set()
    for field in dataclasses.fields(AppConfig):
        if field.name == "guard":
            continue
        keys.add(field.name)
    for field in dataclasses.fields(GuardConfig):
        keys.add(f"guard.{field.name}")
    for field in dataclasses.fields(InstrumentSpec):
        if field.name == "symbol":  # the TOML table name, not a key
            continue
        keys.add(f"instruments.<symbol>.{field.name}")
    return keys


def test_documented_keys_match_dataclasses() -> None:
    documented = _documented_keys()
    expected = _dataclass_keys()
    assert documented == expected, (
        f"documented but not a field: {sorted(documented - expected)}; "
        f"field but not documented: {sorted(expected - documented)}"
    )


def test_every_guard_field_is_documented() -> None:
    documented = _documented_keys()
    for field in dataclasses.fields(GuardConfig):
        assert f"guard.{field.name}" in documented


def test_every_instrument_field_is_documented() -> None:
    documented = _documented_keys()
    for field in dataclasses.fields(InstrumentSpec):
        if field.name == "symbol":
            continue
        assert f"instruments.<symbol>.{field.name}" in documented


def test_aliases_reference_real_fields() -> None:
    instrument_fields = {field.name for field in dataclasses.fields(InstrumentSpec)}
    for key, field in _ALIASES.items():
        assert field in instrument_fields, f"alias {key!r} points at unknown field {field!r}"
