# Architecture

## Module map

```
src/riskpilot/
  errors.py       Exception hierarchy (leaf). RiskPilotError and subclasses.
  _decimal.py     Decimal coercion + exact floor division (leaf, private).
  _version.py     Reads the version from distribution metadata (leaf, private).
  _session.py     Session-boundary arithmetic incl. DST handling (leaf, private).
  instruments.py  InstrumentSpec: validated contract specification.
  sizing.py       size_position: position sizing.
  guard.py        DailyRiskGuard + config/events/decisions.
  config.py       TOML loading into validated dataclasses.
  cli.py          argparse entry point; the only I/O boundary.
  __init__.py     Public re-exports.
```

## Dependency rule

The import direction is strictly one way:

```
cli -> {config, guard, sizing, instruments} -> errors
```

- `errors` is the leaf and imports nothing from the package.
- `_decimal`, `_version` and `_session` are private leaves used by the layers above.
- Core modules (`instruments`, `sizing`, `guard`, `config`) never import `cli`.
- Only `cli.py` performs file I/O, prints, or reads the clock. `config.py` reads a
  file but does so only when `load_config`/`load_instruments` is called with an
  explicit path; it holds no module-level state and prints nothing.

`tests/test_meta.py::test_import_direction_is_respected` parses every module with
`ast` and asserts that each import points at a module in the same or a lower
layer, so a bad import fails CI rather than a code review.

## Purity

The core is pure: no printing, no clock reads, no randomness, no module-level
mutable state. `test_no_core_module_imports_io_or_printing` enforces the absence
of `print`/`input`/`open` outside `cli.py` and `config.py`.

## Decimal discipline

`decimal.Decimal` is used everywhere money, price or quantity appears. The
helpers in `_decimal.py` coerce `int` and `str` inputs to `Decimal` and reject
`float` (and `bool`) with `TypeError`. TOML and CSV parsing preserve decimals as
strings so a binary float never enters the pipeline.

`exact_floor_div` computes `floor(numerator / d1 / d2 / ...)` using integer
arithmetic on the scaled significands, avoiding the rounding error that
`Decimal` division can introduce. This is what guarantees `risk_actual <=
risk_budget` for every valid input.

## Session boundaries

`_session.py` turns a wall-clock reset time in an IANA timezone into a UTC
instant. Two daylight-saving edge cases are handled explicitly:

- **Spring-forward gap** (a wall-clock time that does not exist): the boundary is
  the first instant after the gap (the transition instant), found by binary search.
- **Fall-back overlap** (a wall-clock time that occurs twice): the first
  occurrence (`fold=0`) is used.

## Testing strategy

Tests are organised by concern:

- `test_errors.py` - exception hierarchy.
- `test_instruments.py`, `test_sizing.py` - validation and sizing, including the
  five spec acceptance examples and seeded randomized property tests.
- `test_guard_config.py`, `test_guard_rules.py` - guard configuration and rules.
- `test_guard_dst.py` - America/Chicago transitions on 2026-03-08 and 2026-11-01.
- `test_guard_serialization.py` - `to_dict`/`from_dict` round-trips.
- `test_config.py` - TOML loading and every config error path.
- `test_cli.py`, `test_readme.py` - the CLI and the README examples.
- `test_meta.py` - project invariants (import direction, version single-source,
  suppression budget, file length, no markers).
