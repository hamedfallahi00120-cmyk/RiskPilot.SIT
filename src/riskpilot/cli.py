"""Command line interface for riskpilot-core.

This module is the only place in the package that touches files, standard
streams or the clock. It parses every numeric argument as :class:`Decimal`
(never ``float``) and maps expected failures to documented exit codes.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, TextIO

from riskpilot import __version__
from riskpilot.config import load_config, load_instruments
from riskpilot.errors import RiskPilotError
from riskpilot.guard import DailyRiskGuard, DecisionKind, EquityUpdate, Fill, OrderRequest
from riskpilot.sizing import size_position

EXIT_OK = 0
EXIT_ERROR = 2
EXIT_FLATTEN = 3

_CSV_COLUMNS = ("ts", "type", "symbol", "qty", "equity", "risk_amount")
_EVENT_TYPES = ("EQUITY", "ORDER", "FILL")


class UsageError(Exception):
    """Raised for user-facing usage problems detected after argparse."""


def _decimal_arg(text: str) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        msg = f"invalid decimal value: {text!r}"
        raise argparse.ArgumentTypeError(msg) from exc
    if not value.is_finite():
        msg = f"decimal value must be finite: {text!r}"
        raise argparse.ArgumentTypeError(msg)
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="riskpilot",
        description="Position sizing and daily risk guarding for trading accounts.",
    )
    parser.add_argument("--version", action="version", version=f"riskpilot-core {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    size = sub.add_parser("size", help="size a position from a risk budget")
    size.add_argument("--equity", required=True, type=_decimal_arg)
    size.add_argument("--risk-pct", required=True, type=_decimal_arg)
    size.add_argument("--entry", required=True, type=_decimal_arg)
    size.add_argument("--stop", required=True, type=_decimal_arg)
    size.add_argument("--instruments", required=True, type=Path)
    size.add_argument("--symbol", required=True)
    size.add_argument("--commission", type=_decimal_arg, default=Decimal(0))
    size.add_argument("--slippage-ticks", type=_decimal_arg, default=Decimal(0))
    size.add_argument("--json", action="store_true")

    simulate = sub.add_parser("simulate", help="replay an event CSV through the guard")
    simulate.add_argument("--config", required=True, type=Path)
    simulate.add_argument("--events", required=True, type=Path)
    simulate.add_argument("--json", action="store_true")

    validate = sub.add_parser("validate-config", help="validate a config TOML file")
    validate.add_argument("file", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return the process exit code (see README)."""
    parser = _build_parser()
    try:
        try:
            args = parser.parse_args(argv)
        except SystemExit as exc:  # argparse already reported usage/help
            return exc.code if isinstance(exc.code, int) else EXIT_ERROR
        if args.command == "size":
            return _run_size(args, sys.stdout)
        if args.command == "simulate":
            return _run_simulate(args, sys.stdout)
        if args.command == "validate-config":
            return _run_validate(args, sys.stdout)
        msg = f"unknown command: {args.command}"
        raise UsageError(msg)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except RiskPilotError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


def _run_size(args: argparse.Namespace, out: TextIO) -> int:
    specs = load_instruments(args.instruments)
    spec = specs.get(args.symbol)
    if spec is None:
        known = ", ".join(sorted(specs))
        msg = f"symbol {args.symbol!r} not found in {args.instruments} (known: {known})"
        raise UsageError(msg)
    result = size_position(
        equity=args.equity,
        risk_pct=args.risk_pct,
        entry=args.entry,
        stop=args.stop,
        spec=spec,
        commission_per_unit=args.commission,
        slippage_ticks=args.slippage_ticks,
    )
    payload: dict[str, Any] = {
        "symbol": spec.symbol,
        "qty": str(result.qty),
        "risk_budget": str(result.risk_budget),
        "risk_per_unit": str(result.risk_per_unit),
        "risk_actual": str(result.risk_actual),
        "status": result.status.value,
    }
    if args.json:
        print(json.dumps(payload, indent=2), file=out)
    else:
        print(f"Symbol:         {payload['symbol']}", file=out)
        print(f"Quantity:       {payload['qty']}", file=out)
        print(f"Risk budget:    {payload['risk_budget']}", file=out)
        print(f"Risk per unit:  {payload['risk_per_unit']}", file=out)
        print(f"Risk actual:    {payload['risk_actual']}", file=out)
        print(f"Status:         {payload['status']}", file=out)
    return EXIT_OK


def _run_validate(args: argparse.Namespace, out: TextIO) -> int:
    config = load_config(args.file)
    limit = (
        f"{config.guard.daily_loss_limit_pct}% of equity"
        if config.guard.daily_loss_limit_pct is not None
        else f"{config.guard.daily_loss_limit} absolute"
    )
    print(f"{args.file}: OK", file=out)
    print(f"daily loss limit: {limit}", file=out)
    reset = config.guard.session_reset_time.strftime("%H:%M")
    print(f"session: {reset} {config.guard.session_tz}", file=out)
    print(f"default risk: {config.default_risk_pct}%", file=out)
    return EXIT_OK


def _parse_ts(text: str, *, line: int) -> datetime:
    try:
        ts = datetime.fromisoformat(text)
    except ValueError as exc:
        msg = f"events line {line}: ts {text!r} is not ISO-8601 with a UTC offset"
        raise UsageError(msg) from exc
    if ts.tzinfo is None or ts.utcoffset() is None:
        msg = f"events line {line}: ts {text!r} must carry a UTC offset"
        raise UsageError(msg)
    return ts


def _row_decimal(row: dict[str, str], column: str, *, line: int) -> Decimal:
    text = (row.get(column) or "").strip()
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        msg = f"events line {line}: {column} {text!r} is not a decimal number"
        raise UsageError(msg) from exc


def _row_text(row: dict[str, str], column: str, *, line: int) -> str:
    text = (row.get(column) or "").strip()
    if not text:
        msg = f"events line {line}: {column} is required"
        raise UsageError(msg)
    return text


def _build_event(row: dict[str, str], *, line: int) -> EquityUpdate | OrderRequest | Fill:
    ts = _parse_ts(_row_text(row, "ts", line=line), line=line)
    kind = _row_text(row, "type", line=line).upper()
    if kind == "EQUITY":
        return EquityUpdate(ts=ts, equity=_row_decimal(row, "equity", line=line))
    if kind == "FILL":
        return Fill(
            ts=ts,
            symbol=_row_text(row, "symbol", line=line),
            qty_delta=_row_decimal(row, "qty", line=line),
        )
    if kind == "ORDER":
        return OrderRequest(
            ts=ts,
            symbol=_row_text(row, "symbol", line=line),
            qty=_row_decimal(row, "qty", line=line),
            risk_amount=_row_decimal(row, "risk_amount", line=line),
        )
    msg = f"events line {line}: type {kind!r} is not one of {', '.join(_EVENT_TYPES)}"
    raise UsageError(msg)


def _read_events(path: Path) -> list[EquityUpdate | OrderRequest | Fill]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != _CSV_COLUMNS:
                msg = f"{path}: header must be {','.join(_CSV_COLUMNS)}"
                raise UsageError(msg)
            events = []
            for offset, row in enumerate(reader, start=2):
                if None in row:
                    msg = f"{path} line {offset}: too many columns"
                    raise UsageError(msg)
                events.append(_build_event(row, line=offset))
    except FileNotFoundError as exc:
        msg = f"{path}: file not found"
        raise UsageError(msg) from exc
    return events


def _run_simulate(args: argparse.Namespace, out: TextIO) -> int:
    config = load_config(args.config)
    events = _read_events(args.events)
    guard = DailyRiskGuard(config.guard)
    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [f"Generated at {generated_at}"]
    flatten = False
    for index, event in enumerate(events, start=1):
        decision = guard.on_event(event)
        if decision.kind is DecisionKind.FLATTEN_ALL:
            flatten = True
        lines.append(
            f"{index:>3} {event.ts.isoformat()} {type(event).__name__:<12} "
            f"{decision.kind.value:<11} {decision.reason.value:<20} {decision.state.value}"
        )
    lines.append(f"final state: {guard.state.value}")
    lines.append(f"final loss: {guard.current_loss()}")
    lines.append(f"open positions: {len(guard.open_positions())}")
    output = "\n".join(lines)
    if args.json:
        payload = {
            "generated_at": generated_at,
            "events": len(events),
            "final_state": guard.state.value,
            "final_loss": str(guard.current_loss()),
            "open_positions": {s: str(q) for s, q in guard.open_positions().items()},
            "flatten_all": flatten,
            "state": guard.to_dict(),
        }
        output = f"Generated at {generated_at}\n" + json.dumps(payload, indent=2)
    print(output, file=out)
    return EXIT_FLATTEN if flatten else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
