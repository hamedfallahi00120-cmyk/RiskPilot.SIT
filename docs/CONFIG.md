# Configuration reference

Configuration is TOML. Every numeric value is written as a **string** and parsed
with `decimal.Decimal`, so no binary floating point can enter the engine. A TOML
float (`warning_ratio = 0.7`) is rejected with a `ConfigError`.

Errors always name the dotted key path and the expected type or range, for example
`guard.warning_ratio: expected a decimal string (Decimal), got float`.

## `load_config(path)` — application config

| Key | Type | Default | Allowed range |
|-----|------|---------|---------------|
| `default_risk_pct` | decimal string | none (required) | any finite decimal; the CLI/consumer applies the `(0, 5]` sizing rule |
| `guard` | table | none (required) | see below |

Unknown top-level keys are rejected.

## `[guard]` — `GuardConfig`

| Key | Type | Default | Allowed range |
|-----|------|---------|---------------|
| `daily_loss_limit` | decimal string or absent | `None` | `> 0`, account currency; exactly one of the two limits must be set |
| `daily_loss_limit_pct` | decimal string or absent | `None` | `(0, 100]` percent of session-start equity; exactly one of the two limits must be set |
| `warning_ratio` | decimal string | `"0.7"` | `(0, 1)` exclusive |
| `trailing_drawdown` | decimal string or absent | `None` | `> 0`, account currency, measured from the session equity high-water mark |
| `max_open_positions` | integer or absent | `None` | `>= 1` |
| `max_trades_per_day` | integer or absent | `None` | `>= 1` |
| `session_reset_time` | `"HH:MM"` or `"HH:MM:SS"` string | `"00:00"` | `00:00:00` – `23:59:59`, a **naive local** time |
| `session_tz` | string | `"UTC"` | a known IANA timezone name (`America/Chicago`, `Europe/Amsterdam`, ...) |

Notes:

* `session_reset_time` must be naive: the timezone always comes from `session_tz`.
* The timezone name is validated when the `GuardConfig` is constructed, so a typo
  fails at load time rather than at the first event.
* Unknown keys inside `[guard]` are rejected.

## `load_instruments(path)` — instrument map

Each top-level table is one instrument, keyed by symbol (a single nested
`[instruments]` table is also accepted). Unknown fields are rejected.

| Key | Type | Default | Allowed range |
|-----|------|---------|---------------|
| `tick_size` | decimal string | none (required) | `> 0` |
| `tick_value` | decimal string | none (required) | `> 0`; account-currency value of one tick for **one unit** (1 lot / 1 contract) |
| `min_qty` | decimal string | none (required) | `> 0` and an exact multiple of `qty_step` |
| `qty_step` | decimal string | none (required) | `> 0` |
| `max_qty` | decimal string | none (required) | `>= min_qty` and an exact multiple of `qty_step` |

The shipped example (`examples/instruments.toml`) defines:

| Symbol | tick_size | tick_value | min_qty | qty_step | max_qty |
|--------|-----------|------------|---------|----------|---------|
| EURUSD | `"0.00001"` | `"1.00"` | `"0.01"` | `"0.01"` | `"100"` |
| NQ | `"0.25"` | `"5.00"` | `"1"` | `"1"` | `"50"` |
| MNQ | `"0.25"` | `"0.50"` | `"1"` | `"1"` | `"200"` |

## Event CSV (`riskpilot simulate --events`)

The header is mandatory, in this exact order:

```text
ts,type,symbol,qty,equity,risk_amount
```

| Column | Used by | Meaning |
|--------|---------|---------|
| `ts` | all | ISO-8601 timestamp **with** a UTC offset (`2026-05-04T13:30:00Z` or `...+02:00`) |
| `type` | all | `EQUITY`, `ORDER` or `FILL` |
| `symbol` | `ORDER`, `FILL` | instrument symbol |
| `qty` | `FILL`, `ORDER` | signed quantity delta (FILL) or requested quantity (ORDER) |
| `equity` | `EQUITY` | account equity including unrealised P&L |
| `risk_amount` | `ORDER` | currency amount at risk if the order's stop is hit |

Unused columns stay empty. Rows must be in non-decreasing timestamp order.
