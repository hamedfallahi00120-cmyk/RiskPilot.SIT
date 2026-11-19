# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-19

### Added

* Position sizing with `InstrumentSpec` and `size_position`: exact `Decimal`
  maths, never rounds a quantity up, `BELOW_MIN_QTY` / `CAPPED_AT_MAX` statuses,
  round-turn commission and slippage in ticks.
* Daily risk guard with `DailyRiskGuard`, `GuardConfig`, `EquityUpdate`,
  `OrderRequest`, `Fill`, `Decision`, `DecisionKind`, `GuardState` and `Reason`:
  session baselines, absolute or percentage loss limits, warning threshold,
  trailing drawdown, open-position and trade-count caps, sticky lockout with a
  single `FLATTEN_ALL`, and JSON-serialisable state that survives restarts.
* DST-safe session boundaries with an explicit definition for gap and overlap
  days (`America/Chicago` tests on 2026-03-08 and 2026-11-01).
* Strict TOML configuration (`load_config`, `load_instruments`, `AppConfig`) with
  dotted-key error messages and no floating point anywhere.
* Command-line interface (`riskpilot size`, `riskpilot simulate`,
  `riskpilot validate-config`, `riskpilot --version`) with documented exit codes
  `0`, `2` and `3`.
* Examples: `examples/instruments.toml`, `examples/config.toml`,
  `examples/config_chicago.toml`, `examples/day_breach.csv`,
  `examples/dst_day.csv`.
* Documentation: `docs/ARCHITECTURE.md`, `docs/CONFIG.md`, `docs/DECISIONS.md`.
* CI workflow running ruff (lint + format), mypy `--strict` and pytest with a
  90 % line and branch coverage gate on Python 3.11, 3.12 and 3.13.

### Notes

* Runtime dependencies: none (standard library only).
* No `LICENSE` file is shipped, by the owner's decision.

[Unreleased]: https://github.com/hamedfallahi00120-cmyk/RiskPilot.SIT/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/hamedfallahi00120-cmyk/RiskPilot.SIT/releases/tag/v0.1.0
