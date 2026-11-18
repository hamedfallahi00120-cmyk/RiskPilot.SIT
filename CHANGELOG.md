# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-11-18

### Added

- Position sizing (`size_position`, `InstrumentSpec`, `SizeResult`, `SizeStatus`)
  with strict `Decimal` arithmetic that never rounds up.
- Daily risk guard (`DailyRiskGuard`, `GuardConfig`, `Decision`, `DecisionKind`,
  `GuardState`, `Reason`, `EquityUpdate`, `OrderRequest`, `Fill`) with daily loss
  limits (absolute or percent), a trailing drawdown, position and trade caps, and
  session boundaries that handle daylight-saving transitions.
- State serialisation (`to_dict`/`from_dict`) so a guard survives a restart.
- TOML configuration loading (`load_config`, `load_instruments`, `AppConfig`) with
  dotted-path validation errors.
- Command-line interface (`riskpilot`) with `size`, `simulate`, `validate-config`
  and `--version`, and documented exit codes.
- Example configuration, instrument catalogue and event CSVs under `examples/`.
- Documentation: README, architecture, configuration reference and decisions.
- Test-suite (190+ tests) with seeded randomized property tests, DST tests and a
  90 percent coverage gate.

[0.1.0]: https://github.com/hamedfallahi00120-cmyk/RiskPilot.SIT/releases/tag/v0.1.0
