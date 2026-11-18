"""riskpilot-core: broker-agnostic position sizing and daily-risk guarding."""

from __future__ import annotations

from riskpilot._version import __version__
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
    "size_position",
]
