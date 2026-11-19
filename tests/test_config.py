"""Tests for the TOML configuration loader (strict, Decimal-only)."""

from __future__ import annotations

from datetime import time
from decimal import Decimal
from pathlib import Path

import pytest

from riskpilot import ConfigError
from riskpilot.config import AppConfig, load_config, load_instruments, validate_config

D = Decimal

BASE = """
default_risk_pct = "1"
[guard]
daily_loss_limit = "1000"
"""


def write(tmp_path: Path, text: str, name: str = "config.toml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_load_example_config(examples: Path) -> None:
    config = load_config(examples / "config.toml")
    assert isinstance(config, AppConfig)
    assert config.guard.daily_loss_limit == D("2000")
    assert config.guard.daily_loss_limit_pct is None
    assert config.guard.warning_ratio == D("0.7")
    assert config.guard.trailing_drawdown == D("2500")
    assert config.guard.max_open_positions == 3
    assert config.guard.max_trades_per_day == 6
    assert config.guard.session_reset_time == time(17, 0)
    assert config.guard.session_tz == "America/New_York"
    assert config.default_risk_pct == D("1")


def test_load_chicago_example(examples: Path) -> None:
    config = load_config(examples / "config_chicago.toml")
    assert config.guard.daily_loss_limit_pct == D("2")
    assert config.guard.session_reset_time == time(2, 30)
    assert config.guard.max_open_positions == 2


def test_validate_config_alias(examples: Path) -> None:
    assert validate_config(examples / "config.toml") == load_config(examples / "config.toml")


def test_minimal_config_defaults(tmp_path: Path) -> None:
    config = load_config(write(tmp_path, BASE))
    assert config.guard.daily_loss_limit == D("1000")
    assert config.guard.session_reset_time == time(0, 0)
    assert config.guard.session_tz == "UTC"
    assert config.guard.warning_ratio == D("0.7")


def test_reset_time_with_seconds(tmp_path: Path) -> None:
    text = BASE + 'session_reset_time = "23:59:58"\n'
    assert load_config(write(tmp_path, text)).guard.session_reset_time == time(23, 59, 58)


def test_config_path_is_a_directory(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="is a directory"):
        load_config(tmp_path)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="file not found"):
        load_config(tmp_path / "nope.toml")


def test_invalid_toml(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="invalid TOML"):
        load_config(write(tmp_path, "this is not toml ="))


def test_unreadable_file(tmp_path: Path) -> None:
    path = write(tmp_path, BASE)
    path.chmod(0o000)
    try:
        with pytest.raises(ConfigError, match="permission denied"):
            load_config(path)
    finally:
        path.chmod(0o644)


def test_unknown_top_level_key(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="unknown_key: unknown key"):
        load_config(write(tmp_path, BASE + "unknown_key = 3\n"))


def test_missing_guard_table(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="guard: missing required key"):
        load_config(write(tmp_path, 'default_risk_pct = "1"\n'))


def test_missing_default_risk_pct(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="default_risk_pct: missing required key"):
        load_config(write(tmp_path, '[guard]\ndaily_loss_limit = "1000"\n'))


def test_guard_must_be_a_table(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="guard: expected a table"):
        load_config(write(tmp_path, 'default_risk_pct = "1"\nguard = 5\n'))


def test_decimal_must_be_a_string(tmp_path: Path) -> None:
    text = 'default_risk_pct = 1.5\n[guard]\ndaily_loss_limit = "1000"\n'
    with pytest.raises(ConfigError, match=r"default_risk_pct: expected a decimal string"):
        load_config(write(tmp_path, text))


def test_toml_float_is_rejected_for_ratios(tmp_path: Path) -> None:
    text = 'default_risk_pct = "1"\n[guard]\ndaily_loss_limit = "1000"\nwarning_ratio = 0.7\n'
    with pytest.raises(ConfigError, match=r"guard.warning_ratio: expected a decimal string"):
        load_config(write(tmp_path, text))


def test_non_numeric_decimal_string(tmp_path: Path) -> None:
    text = 'default_risk_pct = "abc"\n[guard]\ndaily_loss_limit = "1000"\n'
    with pytest.raises(ConfigError, match=r"default_risk_pct: expected a decimal string"):
        load_config(write(tmp_path, text))


def test_nan_decimal_string(tmp_path: Path) -> None:
    text = 'default_risk_pct = "nan"\n[guard]\ndaily_loss_limit = "1000"\n'
    with pytest.raises(ConfigError, match="finite"):
        load_config(write(tmp_path, text))


def test_max_open_positions_wrong_type(tmp_path: Path) -> None:
    text = BASE + 'max_open_positions = "3"\n'
    with pytest.raises(ConfigError, match=r"guard.max_open_positions: expected an int"):
        load_config(write(tmp_path, text))


def test_unknown_guard_key(tmp_path: Path) -> None:
    text = BASE + 'made_up = "1"\n'
    with pytest.raises(ConfigError, match=r"guard\.made_up: unknown key"):
        load_config(write(tmp_path, text))


@pytest.mark.parametrize("value", ["9", "midnight", "24:00", "12:60", "12:30:60", "12"])
def test_invalid_reset_time(tmp_path: Path, value: str) -> None:
    text = BASE + f'session_reset_time = "{value}"\n'
    with pytest.raises(ConfigError, match=r"guard\.session_reset_time"):
        load_config(write(tmp_path, text))


def test_reset_time_wrong_type(tmp_path: Path) -> None:
    text = BASE + "session_reset_time = 930\n"
    with pytest.raises(ConfigError, match=r"guard.session_reset_time: expected a 'HH:MM"):
        load_config(write(tmp_path, text))


def test_session_tz_wrong_type(tmp_path: Path) -> None:
    text = BASE + "session_tz = 5\n"
    with pytest.raises(ConfigError, match=r"guard\.session_tz: expected a non-empty string"):
        load_config(write(tmp_path, text))


def test_invalid_timezone(tmp_path: Path) -> None:
    text = BASE + 'session_tz = "Nowhere/Land"\n'
    with pytest.raises(ConfigError, match="IANA timezone"):
        load_config(write(tmp_path, text))


def test_both_limits_in_config(tmp_path: Path) -> None:
    text = (
        'default_risk_pct = "1"\n[guard]\ndaily_loss_limit = "1000"\ndaily_loss_limit_pct = "2"\n'
    )
    with pytest.raises(ConfigError, match="exactly one"):
        load_config(write(tmp_path, text))


def test_warning_ratio_out_of_range(tmp_path: Path) -> None:
    text = BASE + 'warning_ratio = "1.5"\n'
    with pytest.raises(ConfigError, match="warning_ratio"):
        load_config(write(tmp_path, text))


def test_instruments_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="file not found"):
        load_instruments(tmp_path / "nope.toml")


def test_instruments_missing_field(tmp_path: Path) -> None:
    text = '[X]\ntick_size = "1"\ntick_value = "1"\nmin_qty = "1"\nqty_step = "1"\n'
    with pytest.raises(ConfigError, match=r"X\.max_qty: missing required key"):
        load_instruments(write(tmp_path, text, "instruments.toml"))


def test_instruments_unknown_symbol_field(tmp_path: Path) -> None:
    text = (
        '[X]\ntick_size = "1"\ntick_value = "1"\n'
        'min_qty = "1"\nqty_step = "1"\nmax_qty = "10"\nlot = "1"\n'
    )
    with pytest.raises(ConfigError, match=r"X\.lot: unknown key"):
        load_instruments(write(tmp_path, text, "instruments.toml"))


def test_instruments_rejects_invalid_spec(tmp_path: Path) -> None:
    text = '[X]\ntick_size = "1"\ntick_value = "1"\nmin_qty = "0"\nqty_step = "1"\nmax_qty = "10"\n'
    with pytest.raises(ConfigError, match="X: min_qty"):
        load_instruments(write(tmp_path, text, "instruments.toml"))


def test_instruments_accepts_nested_table(tmp_path: Path) -> None:
    text = (
        '[instruments.X]\ntick_size = "1"\ntick_value = "1"\n'
        'min_qty = "1"\nqty_step = "1"\nmax_qty = "10"\n'
    )
    specs = load_instruments(write(tmp_path, text, "instruments.toml"))
    assert list(specs) == ["X"]


def test_instruments_rejects_nested_scalar(tmp_path: Path) -> None:
    text = "instruments = 5\n"
    with pytest.raises(ConfigError, match="instruments: expected"):
        load_instruments(write(tmp_path, text, "instruments.toml"))


def test_instruments_rejects_symbol_scalar(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="X: expected a table"):
        load_instruments(write(tmp_path, "X = 5\n", "instruments.toml"))


def test_empty_instruments(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="instruments: expected at least one"):
        load_instruments(write(tmp_path, "", "instruments.toml"))


def test_float_in_instruments_rejected(tmp_path: Path) -> None:
    text = (
        '[X]\ntick_size = 0.25\ntick_value = "1"\nmin_qty = "1"\nqty_step = "1"\nmax_qty = "10"\n'
    )
    with pytest.raises(ConfigError, match=r"X.tick_size: expected a decimal string"):
        load_instruments(write(tmp_path, text, "instruments.toml"))
