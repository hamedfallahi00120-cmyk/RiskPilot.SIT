"""Command-line interface.

This is the only module permitted to touch files, stdout/stderr or the clock
(H4). It is a thin adapter: it parses arguments, calls into the pure core and
formats results. ``main(argv)`` returns an exit code so it can be tested
in-process without spawning a subprocess.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import tomllib
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from riskpilot._version import __version__
from riskpilot.config import load_config, load_instruments
from riskpilot.errors import RiskPilotError
from riskpilot.guard import DailyRiskGuard, DecisionKind, EquityUpdate, Fill, OrderRequest
from riskpilot.instruments import InstrumentSpec
from riskpilot.sizing import size_position

__all__ = ["main"]

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_FLATTEN = 3

_CSV_FIELDS = ("ts", "type", "symbol", "qty", "equity", "risk_amount")


class _CliError(Exception):
    """Internal marker for expected, user-facing failures (exit code 2)."""


def _decimal(text: str, flag: str) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise _CliError(f"{flag}: expected a decimal number, got {text!r}") from exc
    if not value.is_finite():
        raise _CliError(f"{flag}: expected a finite decimal, got {text!r}")
    return value


def _int(text: str, flag: str) -> int:
    try:
        return int(text)
    except ValueError as exc:
        raise _CliError(f"{flag}: expected an integer, got {text!r}") from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="riskpilot", description="Position sizing and daily-risk guard."
    )
    parser.add_argument("--version", action="version", version=f"riskpilot {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    size = sub.add_parser("size", help="size a position for one trade")
    size.add_argument("--equity", required=True)
    size.add_argument("--risk-pct", required=True)
    size.add_argument("--entry", required=True)
    size.add_argument("--stop", required=True)
    size.add_argument("--instruments", required=True, type=Path)
    size.add_argument("--symbol", required=True)
    size.add_argument("--commission", default="0")
    size.add_argument("--slippage-ticks", default="0")
    size.add_argument("--json", action="store_true", dest="as_json")

    simulate = sub.add_parser("simulate", help="replay an events CSV through the guard")
    simulate.add_argument("--config", required=True, type=Path)
    simulate.add_argument("--events", required=True, type=Path)
    simulate.add_argument("--json", action="store_true", dest="as_json")

    validate = sub.add_parser("validate-config", help="validate a config or instruments file")
    validate.add_argument("file", type=Path)

    return parser


def _cmd_size(args: argparse.Namespace) -> int:
    instruments = load_instruments(args.instruments)
    if args.symbol not in instruments:
        known = ", ".join(sorted(instruments)) or "(none)"
        raise _CliError(f"--symbol: unknown symbol {args.symbol!r} (known: {known})")
    spec: InstrumentSpec = instruments[args.symbol]
    result = size_position(
        equity=_decimal(args.equity, "--equity"),
        risk_pct=_decimal(args.risk_pct, "--risk-pct"),
        entry=_decimal(args.entry, "--entry"),
        stop=_decimal(args.stop, "--stop"),
        spec=spec,
        commission_per_unit=_decimal(args.commission, "--commission"),
        slippage_ticks=_int(args.slippage_ticks, "--slippage-ticks"),
    )
    payload = {
        "symbol": spec.symbol,
        "qty": format(result.qty, "f"),
        "status": result.status.value,
        "risk_budget": format(result.risk_budget, "f"),
        "risk_per_unit": format(result.risk_per_unit, "f"),
        "risk_actual": format(result.risk_actual, "f"),
    }
    if args.as_json:
        print(json.dumps(payload, indent=2))
    else:
        for key in ("symbol", "qty", "status", "risk_budget", "risk_per_unit", "risk_actual"):
            print(f"{key}: {payload[key]}")
    return EXIT_OK


def _read_events(path: Path) -> list[EquityUpdate | OrderRequest | Fill]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != list(_CSV_FIELDS):
                expected = ",".join(_CSV_FIELDS)
                actual = ",".join(reader.fieldnames or [])
                raise _CliError(f"{path}: header must be exactly {expected}, got {actual}")
            events: list[EquityUpdate | OrderRequest | Fill] = []
            for row in reader:
                events.append(_parse_row(row, path))
            return events
    except FileNotFoundError as exc:
        raise _CliError(f"events file not found: {path}") from exc


def _parse_row(row: dict[str, str], path: Path) -> EquityUpdate | OrderRequest | Fill:
    try:
        ts = datetime.fromisoformat(row["ts"])
    except (ValueError, TypeError) as exc:
        raise _CliError(f"{path}: bad ts {row.get('ts')!r}") from exc
    kind = (row["type"] or "").strip().upper()
    if kind == "EQUITY":
        return EquityUpdate(ts=ts, equity=Decimal(row["equity"]))
    if kind == "ORDER":
        return OrderRequest(
            ts=ts,
            symbol=row["symbol"],
            qty=Decimal(row["qty"]),
            risk_amount=Decimal(row["risk_amount"]),
        )
    if kind == "FILL":
        return Fill(ts=ts, symbol=row["symbol"], qty_delta=Decimal(row["qty"]))
    raise _CliError(f"{path}: unknown type {row.get('type')!r} (expected EQUITY, ORDER or FILL)")


def _cmd_simulate(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    events = _read_events(args.events)
    guard = DailyRiskGuard(config.guard)

    records: list[dict[str, str]] = []
    flatten_count = 0
    for event in events:
        decision = guard.on_event(event)
        if decision.kind is DecisionKind.FLATTEN_ALL:
            flatten_count += 1
        records.append(
            {
                "ts": event.ts.isoformat(),
                "type": type(event).__name__,
                "kind": decision.kind.value,
                "reason": decision.reason.value,
                "state": decision.state.value,
            }
        )

    generated_at = datetime.now(UTC).isoformat()
    final_state = guard.state.value
    if args.as_json:
        print(
            json.dumps(
                {
                    "generated_at": generated_at,
                    "events": records,
                    "flatten_all": flatten_count,
                    "final_state": final_state,
                },
                indent=2,
            )
        )
    else:
        print(f"Generated at {generated_at}")
        for record in records:
            fields = " ".join(
                (record["ts"], record["type"], record["kind"], record["reason"], record["state"])
            )
            print(fields)
        print(f"events: {len(records)}")
        print(f"flatten_all: {flatten_count}")
        print(f"final_state: {final_state}")
    return EXIT_FLATTEN if flatten_count > 0 else EXIT_OK


def _cmd_validate(args: argparse.Namespace) -> int:
    path: Path = args.file
    try:
        with path.open("rb") as handle:
            document: dict[str, Any] = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise _CliError(f"file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise _CliError(f"invalid TOML in {path}: {exc}") from exc

    if "guard" in document or "default_risk_pct" in document:
        load_config(path)
        print(f"OK: {path} is a valid application config")
    else:
        specs = load_instruments(path)
        print(f"OK: {path} is a valid instruments file ({len(specs)} symbols)")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return an exit code (0 ok, 2 usage/config error, 3 flatten)."""
    parser = _build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:  # argparse exits for --help/--version/usage errors
        return int(exc.code) if exc.code is not None else EXIT_OK

    handlers = {
        "size": _cmd_size,
        "simulate": _cmd_simulate,
        "validate-config": _cmd_validate,
    }
    handler = handlers[args.command]
    try:
        return handler(args)
    except _CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except (RiskPilotError, InvalidOperation) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover - exercised via the console script
    raise SystemExit(main())
