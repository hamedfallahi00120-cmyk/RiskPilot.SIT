"""Configuration loading.

Parses TOML into validated dataclasses. This module performs no work beyond
reading the supplied path; it is the only core module allowed to touch the
filesystem (via :func:`open`), and even then only when explicitly called.

Decimal quantities are written as *strings* in TOML (for example
``risk_pct = "1.0"``). A TOML float is rejected, because binary floating point
must never enter the library (H3).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from riskpilot.errors import ConfigError, ValidationError
from riskpilot.guard import GuardConfig
from riskpilot.instruments import InstrumentSpec

__all__ = ["AppConfig", "load_config", "load_instruments"]

_MAX_RISK_PCT = Decimal("5")

_GUARD_KEYS = frozenset(
    {
        "daily_loss_limit",
        "daily_loss_limit_pct",
        "warning_ratio",
        "trailing_drawdown",
        "max_open_positions",
        "max_trades_per_day",
        "session_reset_time",
        "session_tz",
    }
)
_TOP_KEYS = frozenset({"default_risk_pct", "guard"})
_INSTRUMENT_KEYS = frozenset({"tick_size", "tick_value", "min_qty", "qty_step", "max_qty"})


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Top-level application configuration."""

    guard: GuardConfig
    default_risk_pct: Decimal


def _read_toml(path: str | Path) -> dict[str, Any]:
    try:
        with Path(path).open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except OSError as exc:
        raise ConfigError(f"cannot read config file {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc


def _expect_mapping(value: object, key: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{key}: expected a table, got {type(value).__name__}")
    return value


def _require(mapping: dict[str, Any], key: str, dotted: str) -> object:
    if key not in mapping:
        raise ConfigError(f"{dotted}: missing required key")
    return mapping[key]


def _reject_unknown(mapping: dict[str, Any], allowed: frozenset[str], prefix: str) -> None:
    for key in mapping:
        if key not in allowed:
            allowed_list = ", ".join(sorted(allowed))
            raise ConfigError(f"{prefix}{key}: unknown key (allowed: {allowed_list})")


def _decimal(value: object, dotted: str) -> Decimal:
    if isinstance(value, (bool, float)):
        raise ConfigError(f"{dotted}: expected decimal string, got {type(value).__name__}")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            parsed = Decimal(value)
        except InvalidOperation as exc:
            raise ConfigError(f"{dotted}: expected decimal string, got {value!r}") from exc
        if not parsed.is_finite():
            raise ConfigError(f"{dotted}: expected a finite decimal, got {value!r}")
        return parsed
    raise ConfigError(f"{dotted}: expected decimal string, got {type(value).__name__}")


def _optional_decimal(mapping: dict[str, Any], key: str, prefix: str) -> Decimal | None:
    if key not in mapping:
        return None
    return _decimal(mapping[key], f"{prefix}{key}")


def _optional_positive_int(mapping: dict[str, Any], key: str, prefix: str) -> int | None:
    if key not in mapping:
        return None
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{prefix}{key}: expected integer, got {type(value).__name__}")
    if value < 1:
        raise ConfigError(f"{prefix}{key}: expected integer >= 1, got {value}")
    return value


def _parse_reset_time(mapping: dict[str, Any], prefix: str) -> time:
    raw = _require(mapping, "session_reset_time", f"{prefix}session_reset_time")
    if not isinstance(raw, str):
        raise ConfigError(f"{prefix}session_reset_time: expected string, got {type(raw).__name__}")
    try:
        parsed = time.fromisoformat(raw)
    except ValueError as exc:
        raise ConfigError(
            f"{prefix}session_reset_time: expected HH:MM or HH:MM:SS, got {raw!r}"
        ) from exc
    if parsed.tzinfo is not None:
        raise ConfigError(f"{prefix}session_reset_time: must be a naive time, got {raw!r}")
    return parsed


def _parse_session_tz(mapping: dict[str, Any], prefix: str) -> str:
    if "session_tz" not in mapping:
        return "UTC"
    raw = mapping["session_tz"]
    if not isinstance(raw, str):
        raise ConfigError(f"{prefix}session_tz: expected string, got {type(raw).__name__}")
    return raw


def _build_guard(table: dict[str, Any]) -> GuardConfig:
    prefix = "guard."
    _reject_unknown(table, _GUARD_KEYS, prefix)
    if "warning_ratio" in table:
        warning_ratio = _decimal(table["warning_ratio"], f"{prefix}warning_ratio")
    else:
        warning_ratio = Decimal("0.7")
    try:
        return GuardConfig(
            daily_loss_limit=_optional_decimal(table, "daily_loss_limit", prefix),
            daily_loss_limit_pct=_optional_decimal(table, "daily_loss_limit_pct", prefix),
            warning_ratio=warning_ratio,
            trailing_drawdown=_optional_decimal(table, "trailing_drawdown", prefix),
            max_open_positions=_optional_positive_int(table, "max_open_positions", prefix),
            max_trades_per_day=_optional_positive_int(table, "max_trades_per_day", prefix),
            session_reset_time=_parse_reset_time(table, prefix)
            if "session_reset_time" in table
            else time(0, 0),
            session_tz=_parse_session_tz(table, prefix),
        )
    except ValidationError as exc:
        raise ConfigError(f"guard: {exc}") from exc


def load_config(path: str | Path) -> AppConfig:
    """Load and validate an application configuration file."""
    document = _read_toml(path)
    _reject_unknown(document, _TOP_KEYS, "")

    guard_table = _expect_mapping(document.get("guard", {}), "guard")
    guard = _build_guard(guard_table)

    raw_risk = _require(document, "default_risk_pct", "default_risk_pct")
    default_risk_pct = _decimal(raw_risk, "default_risk_pct")
    if default_risk_pct <= 0 or default_risk_pct > _MAX_RISK_PCT:
        raise ConfigError(
            f"default_risk_pct: expected value in (0, {_MAX_RISK_PCT}], got {default_risk_pct}"
        )

    return AppConfig(guard=guard, default_risk_pct=default_risk_pct)


def load_instruments(path: str | Path) -> dict[str, InstrumentSpec]:
    """Load and validate an instrument catalogue file."""
    document = _read_toml(path)
    specs: dict[str, InstrumentSpec] = {}
    for symbol, raw_table in document.items():
        table = _expect_mapping(raw_table, symbol)
        prefix = f"{symbol}."
        _reject_unknown(table, _INSTRUMENT_KEYS, prefix)
        try:
            specs[symbol] = InstrumentSpec(
                symbol=symbol,
                tick_size=_decimal(
                    _require(table, "tick_size", f"{prefix}tick_size"), f"{prefix}tick_size"
                ),
                tick_value=_decimal(
                    _require(table, "tick_value", f"{prefix}tick_value"), f"{prefix}tick_value"
                ),
                min_qty=_decimal(
                    _require(table, "min_qty", f"{prefix}min_qty"), f"{prefix}min_qty"
                ),
                qty_step=_decimal(
                    _require(table, "qty_step", f"{prefix}qty_step"), f"{prefix}qty_step"
                ),
                max_qty=_decimal(
                    _require(table, "max_qty", f"{prefix}max_qty"), f"{prefix}max_qty"
                ),
            )
        except ValidationError as exc:
            raise ConfigError(f"{symbol}: {exc}") from exc
    return specs
