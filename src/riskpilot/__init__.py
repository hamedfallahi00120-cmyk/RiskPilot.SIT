"""riskpilot-core: broker-agnostic position sizing and daily-risk guarding.

The public surface is intentionally small and stable. See ``docs/ARCHITECTURE.md``
for the module map and the import-direction rule that the test-suite enforces.
"""

from __future__ import annotations

from riskpilot._version import __version__
from riskpilot.config import AppConfig, load_config, load_instruments
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

__all__ = [
    "AppConfig",
    "DailyRiskGuard",
    "Decision",
    "DecisionKind",
    "EquityUpdate",
    "Fill",
    "GuardConfig",
    "GuardState",
    "InstrumentSpec",
    "OrderRequest",
    "Reason",
    "SizeResult",
    "SizeStatus",
    "__version__",
    "load_config",
    "load_instruments",
    "size_position",
]
