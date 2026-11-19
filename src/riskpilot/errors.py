"""Exception hierarchy for riskpilot-core."""

from __future__ import annotations


class RiskPilotError(Exception):
    """Base class for every error raised by riskpilot-core."""


class ValidationError(RiskPilotError, ValueError):
    """A value is invalid (bad range, wrong multiple, non-positive quantity, ...)."""


class ConfigError(RiskPilotError):
    """A configuration file or mapping is malformed.

    The message always carries the dotted key path and the expected type or
    allowed range.
    """


class InstrumentError(ValidationError, ConfigError):
    """An instrument definition is inconsistent (for example, zero tick size)."""


class OutOfOrderEventError(RiskPilotError):
    """An event carries a timestamp older than the previous event."""
