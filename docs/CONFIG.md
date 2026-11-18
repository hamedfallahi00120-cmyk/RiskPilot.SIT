# Configuration reference

Two files are read by the library and the CLI:

- an **application config** (loaded by `load_config`), used by `riskpilot simulate`
  and `riskpilot validate-config`;
- an **instruments file** (loaded by `load_instruments`), used by
  `riskpilot size` and `riskpilot validate-config`.

Both are TOML. Every decimal value must be a **quoted string**; a bare TOML float
is rejected so a binary float never enters the library.

Unknown keys, missing keys, wrong types and out-of-range values raise
`ConfigError`. The message contains the dotted key path and the expected type or
allowed range.

## Application config

The top-level table holds `default_risk_pct` and a `[guard]` table.

| Key | Type | Default | Range / allowed values | Meaning |
| --- | ---- | ------- | ---------------------- | ------- |
| `default_risk_pct` | decimal string | none (required) | `(0, 5]` | Default per-trade risk in percent, used when a caller does not override it. |
| `guard.daily_loss_limit` | decimal string | none | `> 0` | Absolute daily loss limit in account currency. Exactly one of this and `guard.daily_loss_limit_pct` must be set. |
| `guard.daily_loss_limit_pct` | decimal string | none | `(0, 100]` | Daily loss limit as a percent of the session-start equity. Exactly one of this and `guard.daily_loss_limit` must be set. |
| `guard.warning_ratio` | decimal string | `"0.7"` | `(0, 1)` | Fraction of the limit at which the state moves from ACTIVE to WARNING. |
| `guard.trailing_drawdown` | decimal string | none (disabled) | `> 0` | Absolute drawdown from the session equity high-water mark that locks the session. |
| `guard.max_open_positions` | integer | none (unlimited) | `>= 1` | Maximum number of symbols with a non-zero net quantity. |
| `guard.max_trades_per_day` | integer | none (unlimited) | `>= 1` | Maximum number of allowed orders per session. |
| `guard.session_reset_time` | string | `"00:00"` | `HH:MM` or `HH:MM:SS` (naive) | Wall-clock time at which a new session begins, interpreted in `guard.session_tz`. |
| `guard.session_tz` | string | `"UTC"` | any valid IANA name | Timezone for the session boundary and the reset time. |

Example:

```toml
default_risk_pct = "1.0"

[guard]
daily_loss_limit_pct = "2.0"
warning_ratio = "0.7"
trailing_drawdown = "1500.00"
max_open_positions = 3
max_trades_per_day = 10
session_reset_time = "00:00"
session_tz = "America/Chicago"
```

## Instruments file

One TOML table per symbol. The table name is the symbol. All five keys are
required and must be decimal strings (except as noted). `tick_value` is the
account-currency value of one tick for **one unit** (one lot or one contract).

| Key | Type | Default | Range / allowed values | Meaning |
| --- | ---- | ------- | ---------------------- | ------- |
| `instruments.<symbol>.tick_size` | decimal string | none (required) | `> 0` | Minimum price increment. |
| `instruments.<symbol>.tick_value` | decimal string | none (required) | `> 0` | Account-currency value of one tick for one unit. |
| `instruments.<symbol>.min_qty` | decimal string | none (required) | `> 0`, a multiple of `qty_step`, `<= max_qty` | Smallest tradable quantity. |
| `instruments.<symbol>.qty_step` | decimal string | none (required) | `> 0` | Quantity increment. |
| `instruments.<symbol>.max_qty` | decimal string | none (required) | `> 0`, a multiple of `qty_step`, `>= min_qty` | Largest tradable quantity. |

Example:

```toml
[EURUSD]
tick_size = "0.00001"
tick_value = "1.00"
min_qty = "0.01"
qty_step = "0.01"
max_qty = "100"
```

## Events CSV

`riskpilot simulate` reads a CSV whose header is exactly:

```
ts,type,symbol,qty,equity,risk_amount
```

- `ts` is ISO-8601 with a UTC offset (for example `2026-05-04T05:00:00+00:00`).
- `type` is one of `EQUITY`, `ORDER` or `FILL`.
- `EQUITY` rows use `equity`; `ORDER` rows use `symbol`, `qty` and `risk_amount`;
  `FILL` rows use `symbol` and a signed `qty` (the quantity delta).
