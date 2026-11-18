"""Tests for :mod:`riskpilot.config`."""

from __future__ import annotations

from datetime import time
from decimal import Decimal
from pathlib import Path

import pytest

from riskpilot.config import AppConfig, load_config, load_instruments
from riskpilot.errors import ConfigError
from tests.conftest import EXAMPLES

D = Decimal


def _write(tmp_path: Path, text: str, name: str = "config.toml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


VALID_CONFIG = """
default_risk_pct = "1.0"

[guard]
daily_loss_limit_pct = "2.0"
warning_ratio = "0.7"
session_reset_time = "00:00"
session_tz = "America/Chicago"
"""


def test_load_example_config() -> None:
    config = load_config(EXAMPLES / "config.toml")
    assert isinstance(config, AppConfig)
    assert config.default_risk_pct == D("1.0")
    assert config.guard.session_tz == "America/Chicago"
    assert config.guard.daily_loss_limit_pct == D("2.0")


def test_load_example_instruments() -> None:
    specs = load_instruments(EXAMPLES / "instruments.toml")
    assert set(specs) == {"EURUSD", "NQ", "MNQ"}
    assert specs["NQ"].tick_value == D("5.00")
    assert specs["MNQ"].qty_step == D("1")


def test_minimal_config_uses_defaults(tmp_path: Path) -> None:
    text = 'default_risk_pct = "1"\n\n[guard]\ndaily_loss_limit = "500"\n'
    config = load_config(_write(tmp_path, text))
    assert config.guard.warning_ratio == D("0.7")
    assert config.guard.session_tz == "UTC"
    assert config.guard.session_reset_time == time(0, 0)


def test_missing_file_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.toml")


def test_invalid_toml_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="invalid TOML"):
        load_config(_write(tmp_path, "this is = = broken"))


def test_unknown_top_level_key(tmp_path: Path) -> None:
    text = 'default_risk_pct = "1"\nbogus = "x"\n\n[guard]\ndaily_loss_limit = "1"\n'
    with pytest.raises(ConfigError, match="bogus: unknown key"):
        load_config(_write(tmp_path, text))


def test_unknown_guard_key(tmp_path: Path) -> None:
    text = 'default_risk_pct = "1"\n\n[guard]\ndaily_loss_limit = "1"\nnope = "x"\n'
    with pytest.raises(ConfigError, match=r"guard\.nope: unknown key"):
        load_config(_write(tmp_path, text))


def test_missing_default_risk_pct(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="default_risk_pct: missing"):
        load_config(_write(tmp_path, '[guard]\ndaily_loss_limit = "1"\n'))


def test_missing_guard_table_is_allowed_defaults(tmp_path: Path) -> None:
    # No guard table means no limit -> GuardConfig raises; the dotted path is surfaced.
    with pytest.raises(ConfigError, match="guard"):
        load_config(_write(tmp_path, 'default_risk_pct = "1"\n'))


def test_float_rejected_with_dotted_path(tmp_path: Path) -> None:
    text = 'default_risk_pct = 1.0\n\n[guard]\ndaily_loss_limit = "1"\n'
    with pytest.raises(ConfigError, match="default_risk_pct: expected decimal string"):
        load_config(_write(tmp_path, text))


def test_guard_float_rejected(tmp_path: Path) -> None:
    text = 'default_risk_pct = "1"\n\n[guard]\ndaily_loss_limit = 1.0\n'
    with pytest.raises(ConfigError, match=r"guard\.daily_loss_limit: expected decimal string"):
        load_config(_write(tmp_path, text))


def test_out_of_range_default_risk_pct(tmp_path: Path) -> None:
    text = 'default_risk_pct = "9"\n\n[guard]\ndaily_loss_limit = "1"\n'
    with pytest.raises(ConfigError, match="default_risk_pct"):
        load_config(_write(tmp_path, text))


def test_out_of_range_warning_ratio(tmp_path: Path) -> None:
    text = 'default_risk_pct = "1"\n\n[guard]\ndaily_loss_limit = "1"\nwarning_ratio = "1.5"\n'
    with pytest.raises(ConfigError, match="warning_ratio"):
        load_config(_write(tmp_path, text))


def test_both_limits_rejected(tmp_path: Path) -> None:
    text = 'default_risk_pct = "1"\n\n[guard]\ndaily_loss_limit = "1"\ndaily_loss_limit_pct = "1"\n'
    with pytest.raises(ConfigError, match="exactly one"):
        load_config(_write(tmp_path, text))


def test_bad_reset_time(tmp_path: Path) -> None:
    text = (
        'default_risk_pct = "1"\n\n[guard]\ndaily_loss_limit = "1"\nsession_reset_time = "25:00"\n'
    )
    with pytest.raises(ConfigError, match="session_reset_time"):
        load_config(_write(tmp_path, text))


def test_reset_time_wrong_type(tmp_path: Path) -> None:
    text = 'default_risk_pct = "1"\n\n[guard]\ndaily_loss_limit = "1"\nsession_reset_time = 100\n'
    with pytest.raises(ConfigError, match="session_reset_time: expected string"):
        load_config(_write(tmp_path, text))


def test_session_tz_wrong_type(tmp_path: Path) -> None:
    text = 'default_risk_pct = "1"\n\n[guard]\ndaily_loss_limit = "1"\nsession_tz = 5\n'
    with pytest.raises(ConfigError, match="session_tz: expected string"):
        load_config(_write(tmp_path, text))


def test_unknown_timezone_rejected(tmp_path: Path) -> None:
    text = (
        'default_risk_pct = "1"\n\n[guard]\ndaily_loss_limit = "1"\nsession_tz = "Nowhere/Land"\n'
    )
    with pytest.raises(ConfigError, match="timezone"):
        load_config(_write(tmp_path, text))


@pytest.mark.parametrize("field", ["max_open_positions", "max_trades_per_day"])
def test_negative_int_caps_rejected(tmp_path: Path, field: str) -> None:
    text = f'default_risk_pct = "1"\n\n[guard]\ndaily_loss_limit = "1"\n{field} = 0\n'
    with pytest.raises(ConfigError, match=field):
        load_config(_write(tmp_path, text))


@pytest.mark.parametrize("field", ["max_open_positions", "max_trades_per_day"])
def test_non_int_caps_rejected(tmp_path: Path, field: str) -> None:
    text = f'default_risk_pct = "1"\n\n[guard]\ndaily_loss_limit = "1"\n{field} = "x"\n'
    with pytest.raises(ConfigError, match=f"{field}: expected integer"):
        load_config(_write(tmp_path, text))


def test_guard_not_a_table(tmp_path: Path) -> None:
    text = 'default_risk_pct = "1"\nguard = "nope"\n'
    with pytest.raises(ConfigError, match="guard: expected a table"):
        load_config(_write(tmp_path, text))


def test_instruments_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_instruments(tmp_path / "none.toml")


def test_instruments_unknown_key(tmp_path: Path) -> None:
    fields = ("tick_size", "tick_value", "min_qty", "qty_step", "max_qty")
    keys = "\n".join(f'{key} = "1"' for key in fields)
    text = f'[X]\n{keys}\nbogus = "1"\n'
    with pytest.raises(ConfigError, match=r"X\.bogus: unknown key"):
        load_instruments(_write(tmp_path, text, "instruments.toml"))


def test_instruments_missing_key(tmp_path: Path) -> None:
    text = '[X]\ntick_size = "1"\ntick_value = "1"\nmin_qty = "1"\nqty_step = "1"\n'
    with pytest.raises(ConfigError, match=r"X\.max_qty: missing"):
        load_instruments(_write(tmp_path, text, "instruments.toml"))


def test_instruments_invalid_spec(tmp_path: Path) -> None:
    text = '[X]\ntick_size = "0"\ntick_value = "1"\nmin_qty = "1"\nqty_step = "1"\nmax_qty = "1"\n'
    with pytest.raises(ConfigError, match="X:"):
        load_instruments(_write(tmp_path, text, "instruments.toml"))


def test_instruments_float_rejected(tmp_path: Path) -> None:
    text = '[X]\ntick_size = 1.0\ntick_value = "1"\nmin_qty = "1"\nqty_step = "1"\nmax_qty = "1"\n'
    with pytest.raises(ConfigError, match=r"X\.tick_size: expected decimal string"):
        load_instruments(_write(tmp_path, text, "instruments.toml"))


def test_instruments_not_a_table(tmp_path: Path) -> None:
    text = "X = 5\n"
    with pytest.raises(ConfigError, match="X: expected a table"):
        load_instruments(_write(tmp_path, text, "instruments.toml"))


def test_config_not_serialisable_decimal_raises(tmp_path: Path) -> None:
    text = 'default_risk_pct = "nan"\n\n[guard]\ndaily_loss_limit = "1"\n'
    with pytest.raises(ConfigError, match="finite decimal"):
        load_config(_write(tmp_path, text))


def test_unreadable_file_raises_config_error(tmp_path: Path) -> None:
    target = tmp_path / "adir"
    target.mkdir()
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(target)
