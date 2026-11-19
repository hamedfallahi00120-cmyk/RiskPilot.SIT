"""TOML configuration loading (the only place where config files are read).

Parsing is strict: unknown keys, missing keys, wrong types, unusable nested
tables and out-of-range values all raise :class:`~riskpilot.errors.ConfigError`
with the dotted key path and the expected type or range in the message.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from datetime import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, NoReturn

from riskpilot.errors import ConfigError, RiskPilotError
from riskpilot.guard import GuardConfig
from riskpilot.instruments import InstrumentSpec

_APP_KEYS = ("guard", "default_risk_pct")
_INSTRUMENT_FIELDS = ("tick_size", "tick_value", "min_qty", "qty_step", "max_qty")
_TIME_PATTERN = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9])?$")


@dataclass(frozen=True)
class AppConfig:
    """Application configuration loaded from a TOML file."""

    guard: GuardConfig
    default_risk_pct: Decimal


def _fail(path: str, message: str) -> NoReturn:
    raise ConfigError(f"{path}: {message}")


def _read_toml(file: Path) -> dict[str, Any]:
    try:
        with file.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"{file}: file not found") from exc
    except IsADirectoryError as exc:
        raise ConfigError(f"{file}: is a directory, expected a TOML file") from exc
    except PermissionError as exc:
        raise ConfigError(f"{file}: permission denied") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{file}: invalid TOML: {exc}") from exc


def _check_keys(data: dict[str, Any], *, path: str, allowed: tuple[str, ...]) -> None:
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        _fail(f"{path}.{unknown[0]}" if path else unknown[0], f"unknown key; allowed: {allowed}")


def _require(data: dict[str, Any], *, key: str, path: str) -> object:
    if key not in data:
        _fail(f"{path}.{key}" if path else key, "missing required key")
    return data[key]


def _decimal(value: object, *, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, str):
        _fail(field, f"expected a decimal string (Decimal), got {type(value).__name__}")
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        _fail(field, f"expected a decimal string (Decimal), got {value!r}")
    if not parsed.is_finite():
        _fail(field, f"expected a finite decimal string, got {value!r}")
    return parsed


def _optional_decimal(data: dict[str, Any], *, key: str, field: str) -> Decimal | None:
    if key not in data or data[key] is None:
        return None
    return _decimal(data[key], field=field)


def _optional_int(data: dict[str, Any], *, key: str, field: str) -> int | None:
    if key not in data or data[key] is None:
        return None
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(field, f"expected an int, got {type(value).__name__}")
    return value


def _reset_time(data: dict[str, Any]) -> time:
    if "session_reset_time" not in data or data["session_reset_time"] is None:
        return time(0, 0)
    field = "guard.session_reset_time"
    value = data["session_reset_time"]
    if not isinstance(value, str):
        _fail(field, f"expected a 'HH:MM[:SS]' string, got {type(value).__name__}")
    if not _TIME_PATTERN.match(value):
        _fail(field, f"expected a 'HH:MM[:SS]' string in 00:00-23:59:59, got {value!r}")
    return time.fromisoformat(value)


def _string(data: dict[str, Any], *, key: str, field: str, default: str) -> str:
    if key not in data or data[key] is None:
        return default
    value = data[key]
    if not isinstance(value, str) or not value:
        _fail(field, f"expected a non-empty string, got {type(value).__name__}")
    return value


def load_config(path: str | Path) -> AppConfig:
    """Load ``AppConfig`` from a TOML file.

    Parameters
    ----------
    path:
        Path to a TOML file with ``[guard]`` and top-level ``default_risk_pct``.

    Raises
    ------
    ConfigError
        On any structural or range problem.

    """
    file = Path(path)
    data = _read_toml(file)
    _check_keys(data, path="", allowed=_APP_KEYS)
    guard_data = _require(data, key="guard", path="")
    if not isinstance(guard_data, dict):
        _fail("guard", f"expected a table, got {type(guard_data).__name__}")
    default_risk_pct = _decimal(
        _require(data, key="default_risk_pct", path=""), field="default_risk_pct"
    )
    return AppConfig(
        guard=_guard_config(guard_data),
        default_risk_pct=default_risk_pct,
    )


def _guard_config(guard_data: dict[str, Any]) -> GuardConfig:
    _check_keys(guard_data, path="guard", allowed=_guard_keys())
    try:
        return GuardConfig(
            daily_loss_limit=_optional_decimal(
                guard_data, key="daily_loss_limit", field="guard.daily_loss_limit"
            ),
            daily_loss_limit_pct=_optional_decimal(
                guard_data, key="daily_loss_limit_pct", field="guard.daily_loss_limit_pct"
            ),
            warning_ratio=_decimal(
                guard_data.get("warning_ratio", "0.7"), field="guard.warning_ratio"
            ),
            trailing_drawdown=_optional_decimal(
                guard_data, key="trailing_drawdown", field="guard.trailing_drawdown"
            ),
            max_open_positions=_optional_int(
                guard_data, key="max_open_positions", field="guard.max_open_positions"
            ),
            max_trades_per_day=_optional_int(
                guard_data, key="max_trades_per_day", field="guard.max_trades_per_day"
            ),
            session_reset_time=_reset_time(guard_data),
            session_tz=_string(
                guard_data, key="session_tz", field="guard.session_tz", default="UTC"
            ),
        )
    except RiskPilotError as exc:
        raise ConfigError(f"guard: {exc}") from exc


def _guard_keys() -> tuple[str, ...]:
    return tuple(GuardConfig.__dataclass_fields__)


def load_instruments(path: str | Path) -> dict[str, InstrumentSpec]:
    """Load instrument specifications from a TOML file.

    The file must contain one ``[symbol]`` table per instrument (optionally
    nested under ``[instruments]``). Unknown fields and unknown top-level keys
    are rejected.

    Raises
    ------
    ConfigError
        On any structural or range problem.

    """
    file = Path(path)
    data = _read_toml(file)
    table = data
    if isinstance(data.get("instruments"), dict) and len(data) == 1:
        table = data["instruments"]
    elif "instruments" in data:
        _fail(
            "instruments", "expected [symbol] tables at top level or a single [instruments] table"
        )
    if not table:
        _fail("instruments", "expected at least one [symbol] table")

    specs: dict[str, InstrumentSpec] = {}
    for symbol, raw in table.items():
        field_base = symbol
        if not isinstance(raw, dict):
            _fail(field_base, f"expected a table of instrument fields, got {type(raw).__name__}")
        _check_keys(raw, path=field_base, allowed=_INSTRUMENT_FIELDS)
        values: dict[str, Decimal] = {}
        for field in _INSTRUMENT_FIELDS:
            key = f"{field_base}.{field}"
            values[field] = _decimal(_require(raw, key=field, path=field_base), field=key)
        try:
            specs[symbol] = InstrumentSpec(symbol=symbol, **values)
        except RiskPilotError as exc:
            raise ConfigError(f"{field_base}: {exc}") from exc
    return specs


def validate_config(path: str | Path) -> AppConfig:
    """Alias of :func:`load_config` used by the ``validate-config`` CLI command."""
    return load_config(path)


__all__ = ["AppConfig", "load_config", "load_instruments", "validate_config"]
