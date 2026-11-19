"""riskpilot-core: broker-agnostic position sizing and daily-risk guarding.

The public API is re-exported here. Import direction is strictly
``cli -> {config, guard, sizing, instruments} -> errors``; core modules never
import :mod:`riskpilot.cli`.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _distribution_version

from riskpilot.errors import (
    ConfigError,
    InstrumentError,
    OutOfOrderEventError,
    RiskPilotError,
    ValidationError,
)
from riskpilot.guard import (
    DailyRiskGuard,
    Decision,
    DecisionKind,
    EquityUpdate,
    Fill,
    GuardConfig,
    GuardState,
    OrderRequest,
    Reason,
)
from riskpilot.instruments import InstrumentSpec
from riskpilot.sizing import SizeResult, SizeStatus, size_position

_DISTRIBUTION_NAME = "riskpilot-core"


def _read_version() -> str:
    """Return the installed distribution version (single source: pyproject.toml)."""
    try:
        return _distribution_version(_DISTRIBUTION_NAME)
    except PackageNotFoundError:  # pragma: no cover - only when running uninstalled
        return "0+unknown"


__version__: str = _read_version()

__all__ = [
    "ConfigError",
    "DailyRiskGuard",
    "Decision",
    "DecisionKind",
    "EquityUpdate",
    "Fill",
    "GuardConfig",
    "GuardState",
    "InstrumentError",
    "InstrumentSpec",
    "OrderRequest",
    "OutOfOrderEventError",
    "Reason",
    "RiskPilotError",
    "SizeResult",
    "SizeStatus",
    "ValidationError",
    "__version__",
    "size_position",
]
