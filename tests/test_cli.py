"""Tests for the argparse CLI (called in-process, never via subprocess)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from riskpilot import __version__
from riskpilot.cli import main

HEADER = re.compile(r"^Generated at \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"riskpilot-core {__version__}"


def test_no_arguments_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert "usage:" in capsys.readouterr().err


def test_unknown_command_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["explode"]) == 2
    assert "usage:" in capsys.readouterr().err


def test_size_text_output(capsys: pytest.CaptureFixture[str], examples: Path) -> None:
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
            str(examples / "instruments.toml"),
            "--symbol",
            "EURUSD",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "Quantity:       0.50" in out
    assert "Status:         OK" in out


def test_size_json_output(capsys: pytest.CaptureFixture[str], examples: Path) -> None:
    code = main(
        [
            "size",
            "--equity",
            "50000",
            "--risk-pct",
            "0.5",
            "--entry",
            "20000.00",
            "--stop",
            "19990.00",
            "--instruments",
            str(examples / "instruments.toml"),
            "--symbol",
            "MNQ",
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["qty"] == "12"
    assert payload["risk_actual"] == "240.00"
    assert payload["risk_budget"] == "250.00"
    assert payload["status"] == "OK"


def test_size_with_commission_and_slippage(
    capsys: pytest.CaptureFixture[str], examples: Path
) -> None:
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
            str(examples / "instruments.toml"),
            "--symbol",
            "EURUSD",
            "--commission",
            "7",
            "--slippage-ticks",
            "1",
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["qty"] == "0.48"
    assert payload["risk_per_unit"] == "208.00"


def test_size_invalid_decimal_is_usage_error(
    capsys: pytest.CaptureFixture[str], examples: Path
) -> None:
    code = main(
        [
            "size",
            "--equity",
            "ten",
            "--risk-pct",
            "1",
            "--entry",
            "1.1",
            "--stop",
            "1.09",
            "--instruments",
            str(examples / "instruments.toml"),
            "--symbol",
            "EURUSD",
        ]
    )
    assert code == 2
    assert "invalid decimal value" in capsys.readouterr().err


def test_size_infinite_decimal_is_usage_error(
    capsys: pytest.CaptureFixture[str], examples: Path
) -> None:
    code = main(
        [
            "size",
            "--equity",
            "inf",
            "--risk-pct",
            "1",
            "--entry",
            "1.1",
            "--stop",
            "1.09",
            "--instruments",
            str(examples / "instruments.toml"),
            "--symbol",
            "EURUSD",
        ]
    )
    assert code == 2
    assert "finite" in capsys.readouterr().err


def test_size_unknown_symbol(capsys: pytest.CaptureFixture[str], examples: Path) -> None:
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
            "1.09",
            "--instruments",
            str(examples / "instruments.toml"),
            "--symbol",
            "XXAUUSD",
        ]
    )
    assert code == 2
    assert "symbol 'XXAUUSD' not found" in capsys.readouterr().err


def test_size_validation_error(capsys: pytest.CaptureFixture[str], examples: Path) -> None:
    code = main(
        [
            "size",
            "--equity",
            "10000",
            "--risk-pct",
            "9",
            "--entry",
            "1.1",
            "--stop",
            "1.09",
            "--instruments",
            str(examples / "instruments.toml"),
            "--symbol",
            "EURUSD",
        ]
    )
    assert code == 2
    err = capsys.readouterr().err
    assert err.startswith("error: ")
    assert "Traceback" not in err


def test_validate_config_ok(capsys: pytest.CaptureFixture[str], examples: Path) -> None:
    assert main(["validate-config", str(examples / "config.toml")]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].endswith(": OK")
    assert "daily loss limit: 2000 absolute" in out
    assert "session: 17:00 America/New_York" in out


def test_validate_config_percentage(capsys: pytest.CaptureFixture[str], examples: Path) -> None:
    assert main(["validate-config", str(examples / "config_chicago.toml")]) == 0
    assert "daily loss limit: 2% of equity" in capsys.readouterr().out


def test_validate_config_invalid(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    broken = tmp_path / "broken.toml"
    broken.write_text("default_risk_pct = 1\n", encoding="utf-8")
    assert main(["validate-config", str(broken)]) == 2
    err = capsys.readouterr().err
    assert "error:" in err
    assert "Traceback" not in err


def test_validate_config_missing_file(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    assert main(["validate-config", str(tmp_path / "absent.toml")]) == 2
    assert "file not found" in capsys.readouterr().err


def test_simulate_breach(capsys: pytest.CaptureFixture[str], examples: Path) -> None:
    code = main(
        [
            "simulate",
            "--config",
            str(examples / "config.toml"),
            "--events",
            str(examples / "day_breach.csv"),
        ]
    )
    assert code == 3
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert HEADER.match(lines[0])
    assert "FLATTEN_ALL" in out
    assert lines[-3:] == ["final state: LOCKED", "final loss: 2000", "open positions: 0"]


def test_simulate_clean_day(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, examples: Path
) -> None:
    events = tmp_path / "clean.csv"
    events.write_text(
        "ts,type,symbol,qty,equity,risk_amount\n"
        "2026-05-04T13:30:00Z,EQUITY,,,100000,\n"
        "2026-05-04T13:31:00Z,ORDER,EURUSD,0.5,,100\n"
        "2026-05-04T13:32:00Z,FILL,EURUSD,0.5,,\n"
        "2026-05-04T14:00:00Z,EQUITY,,,100500,\n",
        encoding="utf-8",
    )
    code = main(["simulate", "--config", str(examples / "config.toml"), "--events", str(events)])
    assert code == 0
    out = capsys.readouterr().out
    assert "final state: ACTIVE" in out
    assert "open positions: 1" in out


def test_simulate_json(capsys: pytest.CaptureFixture[str], examples: Path) -> None:
    code = main(
        [
            "simulate",
            "--config",
            str(examples / "config.toml"),
            "--events",
            str(examples / "day_breach.csv"),
            "--json",
        ]
    )
    assert code == 3
    out = capsys.readouterr().out
    assert HEADER.match(out.splitlines()[0])
    payload = json.loads("\n".join(out.splitlines()[1:]))
    assert payload["flatten_all"] is True
    assert payload["final_state"] == "LOCKED"
    assert payload["events"] == 9


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", "header must be"),
        ("ts,type,symbol\n", "header must be"),
        (
            "ts,type,symbol,qty,equity,risk_amount\n2026-05-04T13:30:00Z,EQUITY,,,100000,,\n",
            "too many columns",
        ),
        (
            "ts,type,symbol,qty,equity,risk_amount\n2026-05-04T13:30:00,EQUITY,,,100000,\n",
            "must carry a UTC offset",
        ),
        (
            "ts,type,symbol,qty,equity,risk_amount\nnot-a-date,EQUITY,,,100000,\n",
            "is not ISO-8601",
        ),
        (
            "ts,type,symbol,qty,equity,risk_amount\n2026-05-04T13:30:00Z,EQUITY,,,lots,\n",
            "is not a decimal number",
        ),
        (
            "ts,type,symbol,qty,equity,risk_amount\n2026-05-04T13:30:00Z,TRADE,EURUSD,1,,\n",
            "is not one of EQUITY, ORDER, FILL",
        ),
        (
            "ts,type,symbol,qty,equity,risk_amount\n2026-05-04T13:30:00Z,FILL,,1,,\n",
            "symbol is required",
        ),
    ],
)
def test_simulate_rejects_bad_csv(
    text: str, expected: str, tmp_path: Path, examples: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    events = tmp_path / "bad.csv"
    events.write_text(text, encoding="utf-8")
    code = main(["simulate", "--config", str(examples / "config.toml"), "--events", str(events)])
    assert code == 2
    assert expected in capsys.readouterr().err


def test_simulate_missing_events_file(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, examples: Path
) -> None:
    code = main(
        [
            "simulate",
            "--config",
            str(examples / "config.toml"),
            "--events",
            str(tmp_path / "absent.csv"),
        ]
    )
    assert code == 2
    assert "file not found" in capsys.readouterr().err


def test_simulate_out_of_order_events(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, examples: Path
) -> None:
    events = tmp_path / "backwards.csv"
    events.write_text(
        "ts,type,symbol,qty,equity,risk_amount\n"
        "2026-05-04T14:30:00Z,EQUITY,,,100000,\n"
        "2026-05-04T13:30:00Z,EQUITY,,,100000,\n",
        encoding="utf-8",
    )
    code = main(["simulate", "--config", str(examples / "config.toml"), "--events", str(events)])
    assert code == 2
    assert "older than the previous event" in capsys.readouterr().err


def test_simulate_events_path_is_a_directory(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, examples: Path
) -> None:
    code = main(["simulate", "--config", str(examples / "config.toml"), "--events", str(tmp_path)])
    assert code == 2
    err = capsys.readouterr().err
    assert "is a directory" in err
    assert "Traceback" not in err
