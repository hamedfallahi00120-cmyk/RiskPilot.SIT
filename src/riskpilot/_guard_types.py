"""Guard value objects: config, events, decisions and enums (pure).

These are re-exported by :mod:`riskpilot.guard` so that the public API is
unchanged; they live in their own module to keep each file small.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from riskpilot._decimal import to_decimal
from riskpilot.errors import ConfigError, ValidationError

__all__ = [
    "Decision",
    "DecisionKind",
    "EquityUpdate",
    "Event",
    "Fill",
    "GuardConfig",
    "GuardState",
    "OrderRequest",
    "Reason",
    "Session",
    "validate_reset_time",
]

_ZERO = Decimal(0)
_HUNDRED = Decimal(100)
_ONE = Decimal(1)


class DecisionKind(Enum):
    """Kind of decision returned by :meth:`DailyRiskGuard.on_event`."""

    NONE = "NONE"
    ALLOW = "ALLOW"
    REJECT = "REJECT"
    FLATTEN_ALL = "FLATTEN_ALL"


class GuardState(Enum):
    """Risk state of the current session."""

    ACTIVE = "ACTIVE"
    WARNING = "WARNING"
    LOCKED = "LOCKED"


class Reason(Enum):
    """Machine-readable reason for every non-``NONE`` decision."""

    EQUITY_UPDATE = "EQUITY_UPDATE"
    FILL_RECORDED = "FILL_RECORDED"
    SESSION_RESET = "SESSION_RESET"
    TRAILING_DRAWDOWN = "TRAILING_DRAWDOWN"
    LOCKED = "LOCKED"
    WOULD_BREACH_LIMIT = "WOULD_BREACH_LIMIT"
    NO_EQUITY_BASELINE = "NO_EQUITY_BASELINE"
    MAX_OPEN_POSITIONS = "MAX_OPEN_POSITIONS"
    MAX_TRADES = "MAX_TRADES"
    ORDER_ALLOWED = "ORDER_ALLOWED"


@dataclass(frozen=True)
class GuardConfig:
    """Configuration of :class:`DailyRiskGuard`.

    Exactly one of ``daily_loss_limit`` and ``daily_loss_limit_pct`` must be set.
    See ``docs/CONFIG.md`` for the full key reference.
    """

    daily_loss_limit: Decimal | None = None
    daily_loss_limit_pct: Decimal | None = None
    warning_ratio: Decimal = Decimal("0.7")
    trailing_drawdown: Decimal | None = None
    max_open_positions: int | None = None
    max_trades_per_day: int | None = None
    session_reset_time: time = time(0, 0)
    session_tz: str = "UTC"

    def __post_init__(self) -> None:
        """Validate every field and normalise decimals."""
        if self.daily_loss_limit is not None:
            limit = to_decimal(self.daily_loss_limit, field="daily_loss_limit")
            if limit <= _ZERO:
                msg = f"daily_loss_limit must be > 0, got {limit}"
                raise ValidationError(msg)
            object.__setattr__(self, "daily_loss_limit", limit)
        if self.daily_loss_limit_pct is not None:
            pct = to_decimal(self.daily_loss_limit_pct, field="daily_loss_limit_pct")
            if not (_ZERO < pct <= _HUNDRED):
                msg = f"daily_loss_limit_pct must be in (0, 100] percent, got {pct}"
                raise ValidationError(msg)
            object.__setattr__(self, "daily_loss_limit_pct", pct)
        if (self.daily_loss_limit is None) == (self.daily_loss_limit_pct is None):
            msg = "exactly one of daily_loss_limit or daily_loss_limit_pct must be set"
            raise ValidationError(msg)

        ratio = to_decimal(self.warning_ratio, field="warning_ratio")
        if not (_ZERO < ratio < _ONE):
            msg = f"warning_ratio must be in (0, 1) exclusive, got {ratio}"
            raise ValidationError(msg)
        object.__setattr__(self, "warning_ratio", ratio)

        if self.trailing_drawdown is not None:
            drawdown = to_decimal(self.trailing_drawdown, field="trailing_drawdown")
            if drawdown <= _ZERO:
                msg = f"trailing_drawdown must be > 0, got {drawdown}"
                raise ValidationError(msg)
            object.__setattr__(self, "trailing_drawdown", drawdown)
        for name in ("max_open_positions", "max_trades_per_day"):
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                msg = f"{name} must be an int or None, got {type(value).__name__}"
                raise ValidationError(msg)
            if value < 1:
                msg = f"{name} must be >= 1, got {value}"
                raise ValidationError(msg)
        object.__setattr__(self, "session_reset_time", validate_reset_time(self.session_reset_time))
        self.zoneinfo()

    @property
    def is_percentage_limit(self) -> bool:
        """True when the daily loss limit is expressed as a percentage."""
        return self.daily_loss_limit_pct is not None

    def zoneinfo(self) -> ZoneInfo:
        """Return the parsed ``session_tz``.

        Raises
        ------
        ConfigError
            If ``session_tz`` is not a known IANA timezone name.

        """
        if not isinstance(self.session_tz, str) or not self.session_tz:
            msg = "session_tz must be a non-empty IANA timezone name"
            raise ConfigError(msg)
        try:
            return ZoneInfo(self.session_tz)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            msg = f"session_tz {self.session_tz!r} is not a known IANA timezone"
            raise ConfigError(msg) from exc


@dataclass(frozen=True)
class EquityUpdate:
    """Mark-to-market equity snapshot (realised + unrealised)."""

    ts: datetime
    equity: Decimal


@dataclass(frozen=True)
class OrderRequest:
    """A request to open a position worth ``risk_amount`` of account currency."""

    ts: datetime
    symbol: str
    qty: Decimal
    risk_amount: Decimal


@dataclass(frozen=True)
class Fill:
    """Execution report; ``qty_delta`` is signed (positive opens, negative closes)."""

    ts: datetime
    symbol: str
    qty_delta: Decimal


Event = EquityUpdate | OrderRequest | Fill


@dataclass(frozen=True)
class Decision:
    """Result of feeding one event to the guard."""

    kind: DecisionKind
    reason: Reason
    state: GuardState


@dataclass
class Session:
    """Mutable per-session bookkeeping (never exposed outside the guard)."""

    start: datetime
    baseline: Decimal | None = None
    equity: Decimal | None = None
    high_water: Decimal | None = None
    trades: int = 0
    flatten_emitted: bool = False
    trailing_breached: bool = False


def validate_reset_time(value: object) -> time:
    """Validate the session reset time (a naive local ``datetime.time``)."""
    if not isinstance(value, time):
        msg = f"session_reset_time must be a datetime.time, got {type(value).__name__}"
        raise ValidationError(msg)
    if value.tzinfo is not None:
        msg = "session_reset_time must be a naive local time (timezone comes from session_tz)"
        raise ValidationError(msg)
    return value
