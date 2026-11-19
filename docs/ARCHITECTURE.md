# Architecture

`riskpilot-core` is a small, deliberately boring library: a pure core plus a thin
command-line shell.

## Module map

| Module | Responsibility | I/O | Clock |
|--------|----------------|-----|-------|
| `riskpilot.errors` | Exception hierarchy rooted at `RiskPilotError` | none | no |
| `riskpilot._decimal` | Strict `Decimal` coercion (`to_decimal`, `to_positive_decimal`) | none | no |
| `riskpilot._session` | DST-safe session boundary arithmetic | none | no |
| `riskpilot.instruments` | `InstrumentSpec` (tick size/value, quantity ladder) | none | no |
| `riskpilot.sizing` | `size_position`, `SizeResult`, `SizeStatus` | none | no |
| `riskpilot._guard_types` | Value objects: `GuardConfig`, events, `Decision`, enums | none | no |
| `riskpilot.guard` | `DailyRiskGuard` state machine and serialisation (re-exports the value objects) | none | no |
| `riskpilot.config` | `load_config`, `load_instruments`, `AppConfig` (TOML) | reads files | no |
| `riskpilot.cli` | `main(argv)`, argparse, CSV replay, exit codes | reads files, writes stdout/stderr, reads the clock | yes |
| `riskpilot.__init__` | Public re-exports and `__version__` | metadata read | no |

`config` is the only core module that reads files (that is its entire purpose);
`cli` is the only module allowed to print, read the clock, or decide exit codes.

## Dependency rule

```
cli  ->  {config, guard, sizing, instruments}  ->  errors
```

* No core module imports `riskpilot.cli`, and nothing outside `cli` imports it.
* `errors` is a leaf: it imports nothing from the package.
* `_decimal`, `_session` and `_guard_types` are private helpers imported only by
  core modules; `guard` re-exports the value objects so the public API is
  `riskpilot.guard`/`riskpilot` only.

`tests/test_imports.py` parses every module with `ast` and fails if an edge exists
that is not in the allowed set above, so the rule cannot rot.

## Data flow

1. `config.load_config` / `config.load_instruments` parse TOML into frozen
   dataclasses. Every numeric value is a TOML **string** converted with `Decimal`,
   so no binary float can enter through a file.
2. `sizing.size_position` computes the risk budget and the per-unit risk inside a
   wide local `decimal` context (60 digits) and floors the quotient to a whole
   number of `qty_step` increments. It never rounds up.
3. `guard.DailyRiskGuard.on_event` is a deterministic state machine. Each event
   carries a timezone-aware timestamp; the guard derives the session start from
   the timestamp, `session_reset_time` and `session_tz`, and never reads the
   clock itself.
4. `cli` glues the two together: it parses arguments as `Decimal`, replays a CSV
   through the guard, and maps failures onto documented exit codes.

## Session arithmetic

`_session.boundary_utc` defines the boundary for a local date as *the earliest UTC
instant whose local wall-clock time is at or past the reset time*. Consequences:

* normal day — the boundary is the reset wall time;
* DST gap (the wall time does not exist) — the boundary is the transition instant,
  i.e. the first instant after the gap;
* DST overlap (the wall time exists twice) — the boundary is the first occurrence.

The transition instant is located by bisecting UTC on the offset change, to
microsecond resolution. All comparisons happen in UTC, which is why the guard is
immune to ambiguous local times.

## Serialisation

`DailyRiskGuard.to_dict()` emits plain JSON-serialisable data: Decimals become
strings, timestamps become ISO-8601. `DailyRiskGuard.from_dict(config, data)`
rebuilds a guard that produces identical decisions for identical subsequent
events (proved by a test and by a seeded property test).

## Testing strategy

* Unit tests per module, including every error path.
* Acceptance numbers from the specification as literal assertions.
* Seeded property tests (`random.Random(fixed_seed)`) for the invariants that
  matter: `risk_actual <= risk_budget`, quantity is a multiple of `qty_step`,
  the next step would exceed the budget, and guard round-trips are lossless.
* Meta tests that enforce *process* requirements: import direction, the absence
  of float literals in `src/`, single source of truth for the version,
  docs/config parity, README examples executed byte-for-byte, and repository
  hygiene (no leftover work markers, no committed artifacts, no suppression
  comments at all, no file over 400 lines).
