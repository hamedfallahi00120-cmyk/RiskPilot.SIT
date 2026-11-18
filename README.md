# riskpilot-core

Broker-agnostic position sizing and daily-risk guarding for trading accounts
(forex and futures).

`riskpilot-core` is a small, dependency-free Python library plus a command-line
interface. It answers two questions for a trading account:

1. **How big should this position be?** Given an account equity, a per-trade risk
   budget, an entry and a stop, and an instrument's contract specification,
   `size_position` returns the largest whole number of contracts (or lots) whose
   worst-case loss stays inside the budget. It never rounds up.
2. **Should this order be allowed right now?** `DailyRiskGuard` tracks the day's
   equity, a loss limit, a trailing drawdown and simple caps, and returns a
   decision for every equity update, order request and fill. When a limit is
   breached it locks the session and asks for a full flatten.

All money, price and quantity arithmetic uses `decimal.Decimal`; floating point
never enters the library. The core is pure: no file I/O, no printing, no clock
reads, no randomness, no module-level mutable state. Only `cli.py` touches files,
standard output or the clock.

## Requirements

- Python >= 3.11
- No runtime dependencies (standard library only)

## Install

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

## Quickstart (library)

```python
from decimal import Decimal
from riskpilot import load_instruments, size_position

specs = load_instruments("examples/instruments.toml")
result = size_position(
    equity=Decimal("10000"),
    risk_pct=Decimal("1"),        # 1 percent
    entry=Decimal("1.10000"),
    stop=Decimal("1.09800"),
    spec=specs["EURUSD"],
)
print(result.qty)          # 0.50
print(result.risk_actual)  # 100.0000
```

Guarding a session:

```python
from datetime import UTC, datetime, time
from decimal import Decimal
from riskpilot import DailyRiskGuard, EquityUpdate, GuardConfig

guard = DailyRiskGuard(
    GuardConfig(
        daily_loss_limit=Decimal("1000"),
        session_reset_time=time(0, 0),
        session_tz="America/Chicago",
    )
)
guard.on_event(EquityUpdate(datetime(2026, 5, 4, 5, 0, tzinfo=UTC), Decimal("10000")))
decision = guard.on_event(EquityUpdate(datetime(2026, 5, 4, 5, 3, tzinfo=UTC), Decimal("9000")))
print(decision.kind)    # DecisionKind.FLATTEN_ALL
print(decision.state)   # GuardState.LOCKED
```

## CLI examples

The blocks below are executed by the test-suite and their output is compared
byte-for-byte.

```console
$ riskpilot size --equity 10000 --risk-pct 1 --entry 1.10000 --stop 1.09800 --instruments examples/instruments.toml --symbol EURUSD
symbol: EURUSD
qty: 0.50
status: OK
risk_budget: 100
risk_per_unit: 200.00
risk_actual: 100.0000
```

```console
$ riskpilot size --equity 10000 --risk-pct 1 --entry 1.10000 --stop 1.09800 --instruments examples/instruments.toml --symbol EURUSD --commission 7 --json
{
  "symbol": "EURUSD",
  "qty": "0.48",
  "status": "OK",
  "risk_budget": "100",
  "risk_per_unit": "207.00",
  "risk_actual": "99.3600"
}
```

```console
$ riskpilot validate-config examples/config.toml
OK: examples/config.toml is a valid application config
```

```console
$ riskpilot validate-config examples/instruments.toml
OK: examples/instruments.toml is a valid instruments file (3 symbols)
```

```console
$ riskpilot --version
riskpilot 0.1.0
```

Replaying an events CSV is illustrated below. The first line always starts with
`Generated at ` followed by a UTC timestamp, so its exact text varies per run and
is not part of the byte-for-byte examples.

```bash
riskpilot simulate --config examples/config.toml --events examples/day_breach.csv
# Generated at 2026-05-04T12:00:00+00:00
# 2026-05-04T05:00:00+00:00 EquityUpdate NONE NONE ACTIVE
# 2026-05-04T05:01:00+00:00 OrderRequest ALLOW OK ACTIVE
# 2026-05-04T05:02:00+00:00 Fill NONE NONE ACTIVE
# 2026-05-04T05:03:00+00:00 EquityUpdate FLATTEN_ALL LOCKED LOCKED
# 2026-05-04T05:04:00+00:00 OrderRequest REJECT LOCKED LOCKED
# events: 5
# flatten_all: 1
# final_state: LOCKED
```

`examples/day_breach.csv` breaches the daily limit (exit code 3).
`examples/dst_day.csv` crosses the spring-forward change in America/Chicago
(exit code 0).

## Exit codes

| Code | Meaning |
| ---- | ------- |
| 0 | Success. |
| 2 | Usage, validation or configuration error. A message is written to stderr; no traceback is shown for expected errors. |
| 3 | `simulate` finished with at least one `FLATTEN_ALL` decision. |

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - module map and the import rule.
- [docs/CONFIG.md](docs/CONFIG.md) - every configuration key.
- [docs/DECISIONS.md](docs/DECISIONS.md) - spec ambiguities and the decisions taken.
- [CHANGELOG.md](CHANGELOG.md) - release history.

## License

No license file is shipped. This is the repository owner's decision; see the
pull request description.
