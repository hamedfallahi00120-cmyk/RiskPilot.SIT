"""Exception hierarchy for riskpilot-core.

Every error raised by the library derives from :class:`RiskPilotError` so that
callers can catch a single base class. The modules never import from each other
in a way that creates cycles: this module has no intra-package imports.
"""

from __future__ import annotations

__all__ = [
    "ConfigError",
    "OutOfOrderEventError",
    "RiskPilotError",
    "ValidationError",
]


class RiskPilotError(Exception):
    """Base class for all errors raised by riskpilot-core."""


class ValidationError(RiskPilotError):
    """A value failed a semantic or structural validation rule."""


class ConfigError(RiskPilotError):
    """A configuration file is malformed or holds an invalid value."""


class OutOfOrderEventError(RiskPilotError):
    """An event was submitted with a timestamp older than the previous event."""
