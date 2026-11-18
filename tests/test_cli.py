"""Tests for the :mod:`riskpilot.cli` command-line interface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from riskpilot import __version__
from riskpilot.cli import EXIT_FLATTEN, EXIT_OK, EXIT_USAGE, main
from tests.conftest import EXAMPLES

INSTRUMENTS = str(EXAMPLES / "instruments.toml")
CONFIG = str(EXAMPLES / "config.toml")


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--version"])
    assert code == EXIT_OK
    assert capsys.readouterr().out.strip() == f"riskpilot {__version__}"


def test_no_command_is_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == EXIT_USAGE
    assert "usage" in capsys.readouterr().err.lower()


def test_help_flag(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--help"]) == EXIT_OK
    assert "riskpilot" in capsys.readouterr().out


def test_size_human_output(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "size",
            "--equity",
            "10000",
            "--risk-pct",
            "1",
            "--entry",
            "1.10000",
            "--stop",
            "1.09800",
            "--instruments",
            INSTRUMENTS,
            "--symbol",
            "EURUSD",
        ]
    )
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "symbol: EURUSD" in out
    assert "qty: 0.50" in out
    assert "risk_actual: 100.0000" in out


def test_size_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "size",
            "--equity",
            "50000",
            "--risk-pct",
            "0.5",
            "--entry",
            "20000",
            "--stop",
            "19990",
            "--instruments",
            INSTRUMENTS,
            "--symbol",
            "MNQ",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == EXIT_OK
    assert payload["qty"] == "12"
    assert payload["status"] == "OK"


def test_size_commission_and_slippage(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "size",
            "--equity",
            "10000",
            "--risk-pct",
            "1",
            "--entry",
            "1.10000",
            "--stop",
            "1.09800",
            "--instruments",
            INSTRUMENTS,
            "--symbol",
            "EURUSD",
            "--commission",
            "7",
            "--slippage-ticks",
            "1",
        ]
    )
    assert code == EXIT_OK
    assert "qty:" in capsys.readouterr().out


def test_size_unknown_symbol(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "size",
            "--equity",
            "10000",
            "--risk-pct",
            "1",
            "--entry",
            "1.1",
            "--stop",
            "1.0",
            "--instruments",
            INSTRUMENTS,
            "--symbol",
            "ZZZ",
        ]
    )
    assert code == EXIT_USAGE
    assert "unknown symbol" in capsys.readouterr().err


def test_size_bad_decimal(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "size",
            "--equity",
            "abc",
            "--risk-pct",
            "1",
            "--entry",
            "1.1",
            "--stop",
            "1.0",
            "--instruments",
            INSTRUMENTS,
            "--symbol",
            "EURUSD",
        ]
    )
    assert code == EXIT_USAGE
    assert "expected a decimal" in capsys.readouterr().err


def test_size_bad_slippage(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "size",
            "--equity",
            "10000",
            "--risk-pct",
            "1",
            "--entry",
            "1.1",
            "--stop",
            "1.0",
            "--instruments",
            INSTRUMENTS,
            "--symbol",
            "EURUSD",
            "--slippage-ticks",
            "x",
        ]
    )
    assert code == EXIT_USAGE
    assert "expected an integer" in capsys.readouterr().err


def test_size_missing_file(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "size",
            "--equity",
            "1",
            "--risk-pct",
            "1",
            "--entry",
            "1",
            "--stop",
            "2",
            "--instruments",
            "does-not-exist.toml",
            "--symbol",
            "X",
        ]
    )
    assert code == EXIT_USAGE
    assert "error:" in capsys.readouterr().err


def test_size_validation_error_is_exit_two(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "size",
            "--equity",
            "10000",
            "--risk-pct",
            "1",
            "--entry",
            "1.100005",
            "--stop",
            "1.09800",
            "--instruments",
            INSTRUMENTS,
            "--symbol",
            "EURUSD",
        ]
    )
    assert code == EXIT_USAGE
    assert "whole multiple" in capsys.readouterr().err


def test_simulate_breach_returns_three(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["simulate", "--config", CONFIG, "--events", str(EXAMPLES / "day_breach.csv")])
    out = capsys.readouterr().out
    assert code == EXIT_FLATTEN
    assert out.startswith("Generated at ")
    assert "FLATTEN_ALL" in out
    assert "final_state: LOCKED" in out


def test_simulate_clean_day_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["simulate", "--config", CONFIG, "--events", str(EXAMPLES / "dst_day.csv")])
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert out.startswith("Generated at ")
    assert "flatten_all: 0" in out


def test_simulate_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        ["simulate", "--config", CONFIG, "--events", str(EXAMPLES / "day_breach.csv"), "--json"]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == EXIT_FLATTEN
    assert payload["flatten_all"] == 1
    assert payload["final_state"] == "LOCKED"
    assert payload["generated_at"].endswith("+00:00")


def test_simulate_missing_events_file(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["simulate", "--config", CONFIG, "--events", "nope.csv"])
    assert code == EXIT_USAGE
    assert "not found" in capsys.readouterr().err


def test_simulate_bad_header(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    events = tmp_path / "bad.csv"
    events.write_text("a,b\n1,2\n", encoding="utf-8")
    code = main(["simulate", "--config", CONFIG, "--events", str(events)])
    assert code == EXIT_USAGE
    assert "header must be exactly" in capsys.readouterr().err


def test_simulate_unknown_type(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    events = tmp_path / "bad.csv"
    events.write_text(
        "ts,type,symbol,qty,equity,risk_amount\n2026-05-04T05:00:00+00:00,WOBBLE,,,, \n",
        encoding="utf-8",
    )
    code = main(["simulate", "--config", CONFIG, "--events", str(events)])
    assert code == EXIT_USAGE
    assert "unknown type" in capsys.readouterr().err


def test_simulate_bad_ts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    events = tmp_path / "bad.csv"
    events.write_text(
        "ts,type,symbol,qty,equity,risk_amount\nnot-a-ts,EQUITY,,,10000,\n", encoding="utf-8"
    )
    code = main(["simulate", "--config", CONFIG, "--events", str(events)])
    assert code == EXIT_USAGE
    assert "bad ts" in capsys.readouterr().err


def test_simulate_out_of_order_returns_usage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    events = tmp_path / "ooo.csv"
    events.write_text(
        "ts,type,symbol,qty,equity,risk_amount\n"
        "2026-05-04T05:05:00+00:00,EQUITY,,,10000,\n"
        "2026-05-04T05:01:00+00:00,EQUITY,,,9900,\n",
        encoding="utf-8",
    )
    code = main(["simulate", "--config", CONFIG, "--events", str(events)])
    assert code == EXIT_USAGE
    assert "error:" in capsys.readouterr().err


def test_validate_config_file(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["validate-config", CONFIG])
    assert code == EXIT_OK
    assert "valid application config" in capsys.readouterr().out


def test_validate_instruments_file(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["validate-config", INSTRUMENTS])
    assert code == EXIT_OK
    assert "valid instruments file (3 symbols)" in capsys.readouterr().out


def test_validate_missing_file(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["validate-config", "nope.toml"])
    assert code == EXIT_USAGE
    assert "not found" in capsys.readouterr().err


def test_validate_invalid_toml(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text("= = =", encoding="utf-8")
    code = main(["validate-config", str(bad)])
    assert code == EXIT_USAGE
    assert "invalid TOML" in capsys.readouterr().err


def test_validate_invalid_config_value(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text(
        'default_risk_pct = "1"\n\n[guard]\ndaily_loss_limit = "1"\nwarning_ratio = "5"\n',
        encoding="utf-8",
    )
    code = main(["validate-config", str(bad)])
    assert code == EXIT_USAGE
    assert "error:" in capsys.readouterr().err


def test_validate_directory_reports_oserror(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Passing a directory where a file is expected surfaces an OSError, which the
    # CLI reports as a usage error rather than a traceback.
    code = main(["validate-config", str(tmp_path)])
    assert code == EXIT_USAGE
    assert "error:" in capsys.readouterr().err
