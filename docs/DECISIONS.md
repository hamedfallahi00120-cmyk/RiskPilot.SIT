# Decisions

This file records every ambiguity or conflict noticed in the specification, the
options considered, the choice made, and why. It is deliberately non-empty: a
spec of this size has holes, and silent guesses are worse than written ones.

## D1. Where does the version string live, and how is it read?

- **Spec tension:** H8 says `pyproject.toml` is the single source of truth and the
  package reads it at runtime via `importlib.metadata`, while a test must fail if
  the version is duplicated anywhere else.
- **Options:** (a) hard-code `__version__ = "0.1.0"` in `_version.py`; (b) read
  `importlib.metadata.version("riskpilot-core")` at import time.
- **Choice:** (b). `_version.py` reads the installed distribution metadata. The
  literal `"0.1.0"` appears only in `pyproject.toml`, so
  `test_version_string_not_duplicated_in_source` can scan `src/` for the literal
  and pass. When the package is not installed, a `0.0.0+unknown` fallback is used.
- **Consequence:** `pip install -e .` (or an equivalent install) is required for
  `riskpilot --version` to print the real version; the fallback keeps imports
  working otherwise.

## D2. What is `tick_value` exactly?

- **Spec tension:** "account-currency value of one tick for ONE unit" is
  unambiguous, but "unit" differs between forex (1 lot = 100,000 base units) and
  futures (1 contract). The acceptance examples disambiguate it: for EURUSD a
  one-tick move on `min_qty = 0.01` must be worth `0.01 * 1.00`.
- **Choice:** `tick_value` is the value of one tick for one *quantity unit* as
  measured by `qty_step`/`min_qty`. No lot-size conversion is applied. This is the
  only reading consistent with all five acceptance examples.

## D3. `risk_per_unit` with slippage and commission.

- **Spec:** `risk_per_unit = (distance / tick_size + slippage_ticks) * tick_value +
  commission_per_unit`, commission is round-turn per unit.
- **Ambiguity:** whether slippage applies to the tick count before or after the
  division, and whether `commission_per_unit` is per side or round turn.
- **Choice:** implemented literally as written; `commission_per_unit` is a single
  round-turn number (not doubled). Acceptance example 2 confirms this: with
  commission 7, `risk_per_unit = 200 + 7 = 207` and `qty = 0.48`.

## D4. Rounding of the tick distance.

- **Spec:** `|entry - stop|` must be a positive whole multiple of `tick_size`,
  otherwise a validation error, never silently rounded.
- **Ambiguity:** exact `Decimal` division by `tick_size` can produce a non-integer
  if the operands carry differing exponents (for example `0.2 / 0.00001`).
- **Choice:** compare with exact arithmetic (scaled integers / `Fraction`), so a
  mathematically whole multiple is accepted regardless of representation, and a
  genuinely non-multiple is rejected. No rounding is ever performed.

## D5. Which decimal operations are safe?

- **Ambiguity:** `Decimal` division rounds to the context precision (28 digits by
  default), which could in principle make `risk_actual` slightly exceed
  `risk_budget` and violate "NEVER round up".
- **Choice:** all quantity math goes through `exact_floor_div`, which computes the
  floor of a chain of divisions using integer arithmetic on the scaled
  significands. The property test over 2000 seeded random inputs asserts
  `risk_actual <= risk_budget` and that `qty` is a multiple of `qty_step`.

## D6. What does the DST-gap boundary mean exactly?

- **Spec:** "If the reset time does not exist on a date (DST gap) the boundary is
  the first instant after the gap."
- **Ambiguity:** the first instant after the gap is the *transition instant*
  (03:00 local on 2026-03-08 in Chicago), not the same wall-clock time shifted
  into the new offset (03:30).
- **Choice:** return the transition instant, found by binary search within the
  local day. On 2026-03-08 a 02:30 reset resolves to `08:00Z`. For the fall-back
  overlap, the first occurrence (`fold=0`) is used, so a 01:30 reset resolves to
  `06:30Z`.

## D7. Session boundary detection without a stored clock.

- **Spec:** a session is the interval between consecutive reset boundaries, but
  the guard may only see events and must not read the clock (H4).
- **Choice:** the guard computes the session start for each event's timestamp from
  the config alone (reset time + timezone) and compares it with the stored session
  start. A change means a new session: baseline and daily counters reset, state
  returns to ACTIVE, but open positions are preserved.

## D8. Ordering of rules when several would apply.

- **Ambiguity:** an order may be simultaneously over the trade cap and pushing the
  loss over the limit; an equity update may breach both the daily limit and the
  trailing drawdown.
- **Choice:** for orders, `LOCKED` is checked first, then `WOULD_BREACH_LIMIT`,
  then the position cap, then the trade cap. For equity, reaching the daily limit
  and reaching the trailing drawdown both produce a single `FLATTEN_ALL` with
  reason `LOCKED`, announced exactly once per session.

## D9. "Returned exactly once per session" for FLATTEN_ALL.

- **Ambiguity:** does the guard emit `FLATTEN_ALL` only on the event that causes
  the breach, or on every event while locked?
- **Choice:** only on the event that causes the breach. After that the state stays
  LOCKED and further events return `NONE` (equity) or `REJECT` with reason
  `LOCKED` (orders). A `locked_announced` flag, serialised in `to_dict`, enforces
  this across restarts.

## D10. Is `risk_amount` in an OrderRequest required to be non-negative?

- **Ambiguity:** the spec does not say. A negative risk amount is meaningless.
- **Choice:** reject it with a `ValidationError`. The alternative (silently
  treating it as zero) would let a malformed order slip through the breach check.

## D11. What counts as an open position?

- **Spec:** "number of symbols with non-zero net quantity from Fill events".
- **Choice:** maintain a per-symbol net quantity, updated by the signed
  `qty_delta` of each `Fill`. A symbol whose net quantity returns to zero is no
  longer open. The map is preserved across session resets.

## D12. Where do the numbers for "no equity baseline" sit relative to locking?

- **Ambiguity:** an `OrderRequest` before any `EquityUpdate` cannot be checked
  against a limit, because there is no baseline.
- **Choice:** reject with `NO_EQUITY_BASELINE`. This is checked before the locked
  check only when there is genuinely no baseline; once locked, `LOCKED` wins
  because a session that locked must have had a baseline.

## D13. CLI: bytes on stdout and the volatile header line.

- **Ambiguity:** the spec requires the README examples to be reproduced
  byte-for-byte, but `simulate` prints a `Generated at <now>` header.
- **Choice:** only the deterministic examples (`size`, `validate-config`,
  `--version`) are placed in ````console`` blocks and executed by
  `tests/test_readme.py`. The `simulate` invocation is shown as a bash block with
  illustrative output, and the header requirement is tested separately
  (`test_simulate_breach_returns_three` asserts the output starts with
  `Generated at `).

## D14. Exit codes and tracebacks.

- **Spec:** exit 0 ok, 2 usage/validation/config error, 3 simulate ended with
  FLATTEN_ALL, no traceback for expected errors.
- **Choice:** `main` catches `_CliError`, `RiskPilotError` and `OSError`, prints a
  single `error: ...` line to stderr and returns 2. Unexpected exceptions are not
  caught, so genuine bugs still surface with a traceback (and a non-zero exit).

## D15. `simulate` return code when locked but no flatten was emitted this run.

- **Ambiguity:** if a guard is restored already locked and no `FLATTEN_ALL` is
  emitted, is the run "clean"?
- **Choice:** exit 3 is driven solely by the number of `FLATTEN_ALL` decisions
  emitted during the run, matching the spec wording "simulate ended with a
  FLATTEN_ALL". A run that starts locked but emits none returns 0.

## D16. Files kept, changed or deleted from the original repository.

- **Original contents:** two tutorial MP4s, one English SRT, one `ابزار .zip`, and
  an empty `ai-work/input/README.md`.
- **Choice:** keep them untouched. They are unrelated to the library but the spec
  does not authorise deleting the owner's media. Nothing in the build, tests or CI
  reads them. `ai-work/` is left as-is.

## D17. H4 says `config` is pure, but C requires it to read a file.

- **Spec conflict:** H4 lists `config` among the modules that must do "no file
  I/O", yet C mandates `load_config(path)` and `load_instruments(path)`.
- **Options:** (a) put the file reading in `cli.py` and have `config` accept an
  already-parsed mapping; (b) keep `path`-taking loaders in `config` as C requires.
- **Choice:** (b), because C explicitly specifies `load_config(path)` /
  `load_instruments(path)` as the public API, and the README/CLI depend on it.
  The purity spirit of H4 is preserved: `config` holds no module-level state,
  prints nothing, reads no clock and does no I/O except the single `open` on the
  caller-supplied path. `test_no_core_module_imports_io_or_printing` permits
  `open` in `config` only and forbids printing anywhere outside `cli`.

## D18. `config` imports `guard` and `instruments`.

- **Spec:** H5 states the direction `cli -> {config, guard, sizing, instruments} ->
  errors`, which some readers take to mean the four middle modules may import
  **only** `errors`.
- **Choice:** `config` additionally imports `guard` and `instruments`, because
  `load_config` must construct a `GuardConfig` and `load_instruments` must
  construct `InstrumentSpec`. The arrow is read as "these four depend on errors",
  not "these four depend on nothing else". `guard`, `sizing` and `instruments`
  import only `errors` (and private leaves), so no cycle is possible; the `ast`
  test encodes a layer index that still forbids any core module from importing
  `cli`.

