# Decisions

Every ambiguity, gap or internal conflict found in the specification, the options
considered, the choice made, and why. Ordered roughly by area.

## 1. `tick_value` semantics (one unit vs one lot)

**Ambiguity.** "tick_value = account-currency value of one tick for ONE unit (1
lot / 1 contract)" mixes two conventions: forex quotes tick value per *lot*,
futures per *contract*.

**Decision.** Take the text literally: `tick_value` is the value of one tick for a
quantity of `1` in the same unit as `qty_step`/`min_qty`. One EURUSD "unit" is
therefore 0.01 lots = 1,000 currency units, and the shipped values
(`tick_value = 1.00` for EURUSD) reproduce the specification's acceptance numbers.

**Why.** The acceptance examples are the contract; any other reading breaks
example 1 (`qty 0.50`, `risk_actual 100.00`).

## 2. A session boundary falling inside a DST gap

**Option A.** Skip the boundary entirely for that date (the previous session runs
48 h).
**Option B.** Use the first instant after the gap (the transition instant).

**Decision.** Option B, per the specification. It is implemented as "the earliest
UTC instant whose local wall-clock time is at or past the reset wall time", which
also yields "first occurrence" for DST overlaps without special-casing.

**Why.** A session that silently lasts 48 hours would let a day's losses accumulate
across two trading days; the specification also requires the boundary to exist.

## 3. DST overlap: which occurrence is the boundary?

**Decision.** The first occurrence (the one with the *smaller* UTC timestamp, i.e.
the DST offset still in effect). Already implied by the definition above; a test
pins `2026-11-01 01:30 America/Chicago == 06:30Z`, and `07:30Z` (the second
01:30 wall time) is still the same session.

## 4. `risk_pct` included the permitted upper bound?

**Ambiguity.** "valid range (0, 5]" — inclusive or not at 5?

**Decision.** Exclusive at 0, inclusive at 5. `risk_pct == 5` is accepted,
`0` and negatives are rejected; a test asserts both ends.

## 5. Stop distance of exactly zero

**Ambiguity.** "|entry - stop| must be a positive whole multiple of tick_size" —
zero *is* a whole multiple of any tick size.

**Decision.** Rejected explicitly with the message "entry and stop must differ".
A zero-distance stop cannot express risk, so refusing is the safe reading of the
word "positive".

## 6. Fractional `slippage_ticks`

**Ambiguity.** The type is not stated; the parameter name says "ticks".

**Decision.** It must be a whole number (`Decimal` with zero fractional part) and
`>= 0`; fractional values raise `ValidationError`. Ticks are discrete, and
allowing fractions would silently change the risk model.

## 7. `qty` when the budget is smaller than one step

**Decision.** `qty = 0` with `SizeStatus.BELOW_MIN_QTY`, never bumped up to
`min_qty` (explicit in the specification). `risk_actual` is then `0`, and the
same rule is re-used when `max_qty` caps the size.

## 8. `risk_actual <= risk_budget` with a capped quantity

**Decision.** When the size is capped at `max_qty` the invariant still holds,
because the cap only ever *lowers* the computed quantity. A property test checks
it for 2,000 random inputs.

## 9. `max_trades_per_day` — what counts as a trade?

**Options.** Count (a) every `OrderRequest`, (b) every `ALLOW`, (c) every `Fill`.

**Decision.** Count only `ALLOW` decisions. The specification says a **rejected**
order must not mutate state, and counting fills would depend on broker latency.

**Limitation.** A subsequent `Fill` that is split into multiple partial fills
counts once per `ALLOW`, not once per fill — intentional, because the counter
guards *decisions*, not executions.

## 10. `max_open_positions` — does an existing symbol consume a new slot?

**Decision.** No. The check only applies when the requested symbol currently has
zero net quantity; increasing exposure to an already open symbol is allowed.
This matches how a trader reads "maximum open positions" (distinct instruments).
A test pins the behaviour.

## 11. FLATTEN_ALL emission "exactly once per session"

**Options.** Emit on every event that observes a breach, or once.

**Decision.** Once: the first event that observes a breach returns
`FLATTEN_ALL`; later events in the same session return `NONE` with reason
`LOCKED`. The state stays `LOCKED` (sticky) either way.

## 12. Does `WOULD_BREACH_LIMIT` use `>=` or `>`?

**Decision.** `current_loss + risk_amount >= limit` rejects, exactly as specified.
The consequence is that an order that would land *exactly* on the limit is
rejected; the guard prefers one currency unit of margin over an off-by-one.

## 13. Trailing drawdown in a recovering session

**Ambiguity.** The state is "LOCKED" but the specification only defines a breach
as `drawdown >= trailing_drawdown` at the moment of observation.

**Decision.** Once a trailing drawdown breaches, the session is locked for the
rest of the session (a flag is persisted and serialised), so an equity rebound
cannot unlock trading. Otherwise the user could recover equity after a breach and
immediately trade again, which defeats the guard.

## 14. `trailing_drawdown` without any equity baseline

**Decision.** The drawdown is only evaluated when a baseline and a current equity
exist. Before the first `EquityUpdate` no "session high-water mark" exists, so no
drawdown can be measured. `OrderRequest` events already become
`NO_EQUITY_BASELINE` in that state.

## 15. `daily_loss_limit_pct` and the baseline

**Decision.** The percentage is applied to the **session baseline equity** (the
first `EquityUpdate` of the session), not to the high-water mark and not to a
rolling average. It is evaluated lazily, so `loss_limit()` returns `None` until a
baseline exists, and a percentage config can still answer
`NO_EQUITY_BASELINE` for the first order.

## 16. Warning/lock thresholds when a percentage limit is used

**Decision.** Warning state is entered at `loss >= warning_ratio * limit`, where
`limit` is the resolved absolute limit for the session. This keeps the semantics
identical for absolute and percentage configurations.

## 17. What does `GuardState` mean before the first event?

**Decision.** `ACTIVE`, with `session_start`, `baseline_equity` and
`high_water_equity` returning `None`. Serialising such a guard produces
`{"state": "ACTIVE", ..., "session": null}` and round-trips losslessly.

## 18. `Reason` for ordinary events

**Ambiguity.** `Reason` is required to contain at least the five listed members;
`Decision` always needs a reason, including for `NONE`.

**Decision.** `Reason` additionally contains `EQUITY_UPDATE`, `FILL_RECORDED`,
`SESSION_RESET`, `ORDER_ALLOWED` and `TRAILING_DRAWDOWN`. `Reason.SESSION_RESET`
wins over `EQUITY_UPDATE` for the first event of a session so callers can detect
a roll. `TRAILING_DRAWDOWN` lets callers distinguish which limit fired.

## 19. Timestamps: strict ordering and clock

**Decision.** Events must be timezone-aware (`ValidationError` otherwise) and must
never be older than the previous event (`OutOfOrderEventError`). Equal timestamps
are accepted (allows several fills at the same instant). The guard never reads the
clock; only `cli.simulate` stamps its header.

## 20. Serialised event history

**Ambiguity.** "State survives restarts" — is the event history part of the state?

**Decision.** No: only the derived state (state, session, open positions, trade
counter, last timestamp) is serialised. Replaying the full history is the caller's
job (the CLI does exactly that). The restored guard produces identical decisions
for identical subsequent events — proven by a test.

**Limitation.** The serialised payload is not authenticated; a tampered payload is
accepted as long as it parses.

## 21. TOML numbers as strings

**Ambiguity.** TOML has no decimal type, only floats and integers.

**Decision.** Every decimal is a TOML **string** parsed with `Decimal`; integers
use TOML integers. A TOML float is rejected with a `ConfigError` naming the key.
This is the only way to honour "no float anywhere, including TOML parsing".

## 22. `default_risk_pct` validation

**Decision.** `load_config` only requires a finite Decimal. The `(0, 5]` rule
belongs to `size_position` and is enforced there, so changing the default risk in
a config cannot bypass the sizing invariant; `size_position` rejects an
out-of-range value at call time.

## 23. Instrument tables nested or top level?

**Decision.** Accept both `[EURUSD]` at top level and a single `[instruments]`
table containing them. Neither is required to match a particular broker export,
and rejecting one of them would be gratuitous. Unknown fields are rejected either
way.

## 24. Exit codes and argparse

**Ambiguity.** argparse exits with `SystemExit(2)` itself, and `--version` with 0.

**Decision.** `main()` catches `SystemExit` and returns its code, so `main()` is
always testable in process and never raises for expected usage errors. `--version`
therefore returns `0` and prints to stdout; usage errors return `2` and print to
stderr. Unexpected programming errors are *not* caught: they surface as
`RiskPilotError` subclasses handled with exit code 2 and a one-line message, while
genuine bugs still raise (no silent traceback swallowing).

## 25. Money formatting in the CLI

**Ambiguity.** "Output must match byte for byte" — at which precision?

**Decision.** The CLI is a *display* layer: it renders money with exactly two
decimals (`100.0000` from a 4-dp risk per unit becomes `100.00`) and quantities in
plain notation via `format(qty, "f")` (never scientific, never rounded). The
library itself keeps the exact `Decimal`, so display rounding cannot affect
decisions. `str()` of a `Decimal` in scientific notation (`5E+1`) is explicitly
avoided in the CLI output.

## 26. The version string

**Decision.** `pyproject.toml` is the single source. `riskpilot.__version__` is
read at import time with `importlib.metadata.version("riskpilot-core")`. When the
distribution is not installed (running straight from `src/`), the fallback is
`0+unknown`; no version literal is duplicated. A test scans every file for a
concrete version literal outside `pyproject.toml`/`CHANGELOG.md` and fails if
one appears.

## 27. Repository history: pre-existing files

**Ambiguity.** The repository already contained two `.mp4` files, a `.srt` file,
a `.zip` archive (non-ASCII filename) and an empty `ai-work/input/README.md`.

**Decision.** Leave them untouched. They are the owner's media and removing them
would be destructive; they are binary artefacts, not code, so they do not affect
the quality gates. This is stated explicitly in the pull request.

## 28. `#[type: ignore]` / `# noqa` budget

**Decision.** The budget is three, each with a written justification. The final
count is zero in `src/` and a small number in `tests/` (where deliberate type
violations are the point of the test); a meta test fails the build above the
budget. Tests may not be weakened to satisfy a linter.

## 29. Timezone database availability

**Ambiguity.** `zoneinfo` needs a system tzdata (or the `tzdata` package, which is
not a stdlib module and would violate the runtime dependency rule).

**Decision.** Rely on the system tzdata (present on all CI images and every
common Linux/macOS install) and fail with a `ConfigError` if the zone is unknown.
No dependency is added; the README documents the requirement. (`America/Chicago`
is used by the DST tests, and GitHub's `ubuntu-latest` images ship the IANA data.)

## 30. Types at the boundary: `Any` vs `object`

**Ambiguity.** The public API must accept `Decimal`/`int`/`str` but reject
`float`; annotating with `Any` weakens `mypy --strict` for callers.

**Decision.** Public parameters are annotated with the `NumericInput` alias
(`Decimal | int | str`). The strictness is enforced *at runtime* by `to_decimal`,
which rejects `float` and `bool`, so a static type checker and the runtime agree
and no `Any` leaks into the public API.
