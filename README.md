# riskpilot-core

Broker-agnostic **position sizing** and **daily risk guarding** for trading accounts
(forex and futures), as a pure Python library plus a thin CLI.

* `size_position` turns an equity, a risk percentage and a stop distance into the
  largest position that **never** risks more than the budget.
* `DailyRiskGuard` tracks session baselines, daily loss limits, trailing drawdown,
  open positions and trade counts, and answers `ALLOW` / `REJECT` / `FLATTEN_ALL`.
* All money, price and quantity maths is exact `decimal.Decimal` arithmetic.
  Passing a `float` to any public function raises `TypeError`.
* Runtime dependencies: **none** (standard library only).
* The core is pure: no file I/O, no clock reads, no printing, no global state.

Modules: `errors` (exception hierarchy), `instruments` (`InstrumentSpec`), `sizing`
(`size_position`, `SizeResult`, `SizeStatus`), `guard` (`DailyRiskGuard`,
`GuardConfig`, events, `Decision`), `config` (`load_config`, `load_instruments`,
`AppConfig`) and `cli` (`main`).

## Install

```console
python -m pip install .
# development setup
python -m pip install -e '.[dev]'
```

Python 3.11 or newer is required.

## Library quickstart

```python
from decimal import Decimal

from riskpilot import InstrumentSpec, size_position

eurusd = InstrumentSpec(
    symbol="EURUSD",
    tick_size=Decimal("0.00001"),
    tick_value=Decimal("1.00"),
    min_qty=Decimal("0.01"),
    qty_step=Decimal("0.01"),
    max_qty=Decimal("100"),
)
result = size_position(
    equity=Decimal("10000"),
    risk_pct=Decimal("1"),  # 1 %
    entry=Decimal("1.10000"),
    stop=Decimal("1.09800"),
    spec=eurusd,
)
print(result.qty, result.risk_actual, result.status.value)
# 0.50 100.0000 OK
```

Guarding a session:

```python
from datetime import UTC, datetime
from decimal import Decimal

from riskpilot import DailyRiskGuard, DecisionKind, EquityUpdate, GuardConfig, OrderRequest

guard = DailyRiskGuard(GuardConfig(daily_loss_limit=Decimal("1000"), session_tz="UTC"))
guard.on_event(EquityUpdate(ts=datetime(2026, 5, 4, 13, 0, tzinfo=UTC), equity=Decimal("10000")))
decision = guard.on_event(
    OrderRequest(
        ts=datetime(2026, 5, 4, 13, 1, tzinfo=UTC),
        symbol="EURUSD",
        qty=Decimal("0.5"),
        risk_amount=Decimal("250"),
    )
)
assert decision.kind is DecisionKind.ALLOW
```

## CLI

Everything below is executed by `tests/test_readme.py`; the expected output is
compared **byte for byte**.

### Sizing a position

```console
$ riskpilot size --equity 10000 --risk-pct 1 --entry 1.10000 --stop 1.09800 --instruments examples/instruments.toml --symbol EURUSD
Symbol:         EURUSD
Quantity:       0.50
Risk budget:    100.00
Risk per unit:  200.00
Risk actual:    100.00
Status:         OK
```

Add `--json` for machine-readable output:

```console
$ riskpilot size --equity 50000 --risk-pct 0.5 --entry 20000.00 --stop 19990.00 --instruments examples/instruments.toml --symbol MNQ --json
{
  "symbol": "MNQ",
  "qty": "12",
  "risk_budget": "250.00",
  "risk_per_unit": "20.00",
  "risk_actual": "240.00",
  "status": "OK"
}
```

### Validating a configuration

```console
$ riskpilot validate-config examples/config.toml
examples/config.toml: OK
daily loss limit: 2000 absolute
session: 17:00 America/New_York
default risk: 1%
```

### Replaying an event day

```console
$ riskpilot simulate --config examples/config.toml --events examples/day_breach.csv
```

The simulate output always starts with a `Generated at <UTC timestamp>` header,
followed by one line per event and a summary. Its exit code is `3` when the day
ended in a `FLATTEN_ALL` decision. `examples/dst_day.csv` with
`examples/config_chicago.toml` uses a `02:30 America/Chicago` reset to exercise
both DST transitions.

### Exit codes

| Code | Meaning                                                              |
|------|----------------------------------------------------------------------|
| `0`  | success                                                              |
| `2`  | usage, validation or configuration error (message on stderr)         |
| `3`  | `simulate` finished with a `FLATTEN_ALL` decision                    |

`riskpilot --version` prints the distribution version, e.g.:

```console
$ riskpilot --version
riskpilot-core <version>
```

(The version is read from the installed distribution metadata; `pyproject.toml`
is the single source of truth.)

## Documentation

* [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — module map and the dependency rule.
* [docs/CONFIG.md](docs/CONFIG.md) — every configuration key with type, default and range.
* [docs/DECISIONS.md](docs/DECISIONS.md) — ambiguities in the specification and how they were resolved.
* [CHANGELOG.md](CHANGELOG.md) — release history.

## Development

```console
ruff check . && ruff format --check . && mypy && pytest
```

The test-suite enforces the import direction (`cli -> core -> errors`) by
parsing module imports with `ast`, enforces a single source of truth for the
version, and fails if `docs/CONFIG.md` drifts from the dataclasses.

## Licence

No `LICENSE` file is shipped in this repository by the owner's decision.
