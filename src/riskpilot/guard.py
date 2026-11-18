"""Daily risk guard.

A stateful, pure (no I/O, no clock, no randomness) evaluator that turns a stream
of trading events into allow/reject/flatten decisions and enforces a daily loss
limit, an optional trailing drawdown, and optional position/trade caps.

Sessions are defined in a caller-supplied IANA timezone; each session begins at
``session_reset_time`` local time and the guard resets its daily counters then.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from decimal import Decimal
from enum import Enum
from zoneinfo import ZoneInfo

from riskpilot._decimal import to_decimal
from riskpilot._session import session_start_utc
from riskpilot.errors import OutOfOrderEventError, ValidationError

__all__ = [
    "DailyRiskGuard",
    "Decision",
    "DecisionKind",
    "EquityUpdate",
    "Fill",
    "GuardConfig",
    "GuardState",
    "OrderRequest",
    "Reason",
]

_UTC = UTC
_HUNDRED = Decimal(100)


class DecisionKind(Enum):
    """What the caller should do with an event."""

    NONE = "NONE"
    ALLOW = "ALLOW"
    REJECT = "REJECT"
    FLATTEN_ALL = "FLATTEN_ALL"


class GuardState(Enum):
    """Current risk state of the session."""

    ACTIVE = "ACTIVE"
    WARNING = "WARNING"
    LOCKED = "LOCKED"


class Reason(Enum):
    """Machine-readable explanation attached to a :class:`Decision`."""

    NONE = "NONE"
    OK = "OK"
    LOCKED = "LOCKED"
    WOULD_BREACH_LIMIT = "WOULD_BREACH_LIMIT"
    NO_EQUITY_BASELINE = "NO_EQUITY_BASELINE"
    MAX_OPEN_POSITIONS = "MAX_OPEN_POSITIONS"
    MAX_TRADES = "MAX_TRADES"


@dataclass(frozen=True, slots=True)
class Decision:
    """Outcome of evaluating one event."""

    kind: DecisionKind
    reason: Reason
    state: GuardState


@dataclass(frozen=True, slots=True)
class EquityUpdate:
    """A new account-equity observation (unrealized P&L included)."""

    ts: datetime
    equity: Decimal


@dataclass(frozen=True, slots=True)
class OrderRequest:
    """A request to open or extend a position."""

    ts: datetime
    symbol: str
    qty: Decimal
    risk_amount: Decimal


@dataclass(frozen=True, slots=True)
class Fill:
    """A fill; ``qty_delta`` is signed (positive to open/lengthen, negative to close)."""

    ts: datetime
    symbol: str
    qty_delta: Decimal


@dataclass(frozen=True, slots=True)
class GuardConfig:
    """Immutable, self-validating configuration for :class:`DailyRiskGuard`."""

    daily_loss_limit: Decimal | None = None
    daily_loss_limit_pct: Decimal | None = None
    warning_ratio: Decimal = Decimal("0.7")
    trailing_drawdown: Decimal | None = None
    max_open_positions: int | None = None
    max_trades_per_day: int | None = None
    session_reset_time: time = time(0, 0)
    session_tz: str = "UTC"

    def __post_init__(self) -> None:
        if (self.daily_loss_limit is None) == (self.daily_loss_limit_pct is None):
            raise ValidationError(
                "exactly one of daily_loss_limit or daily_loss_limit_pct must be set"
            )
        if self.daily_loss_limit is not None:
            limit = to_decimal(self.daily_loss_limit, "daily_loss_limit")
            if limit <= 0:
                raise ValidationError(f"daily_loss_limit must be positive, got {limit}")
            object.__setattr__(self, "daily_loss_limit", limit)
        if self.daily_loss_limit_pct is not None:
            pct = to_decimal(self.daily_loss_limit_pct, "daily_loss_limit_pct")
            if pct <= 0 or pct > _HUNDRED:
                raise ValidationError(f"daily_loss_limit_pct must be in (0, 100], got {pct}")
            object.__setattr__(self, "daily_loss_limit_pct", pct)

        ratio = to_decimal(self.warning_ratio, "warning_ratio")
        if ratio <= 0 or ratio >= 1:
            raise ValidationError(f"warning_ratio must be in (0, 1), got {ratio}")
        object.__setattr__(self, "warning_ratio", ratio)

        if self.trailing_drawdown is not None:
            drawdown = to_decimal(self.trailing_drawdown, "trailing_drawdown")
            if drawdown <= 0:
                raise ValidationError(f"trailing_drawdown must be positive, got {drawdown}")
            object.__setattr__(self, "trailing_drawdown", drawdown)

        for name in ("max_open_positions", "max_trades_per_day"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 1
            ):
                raise ValidationError(f"{name} must be an int >= 1, got {value!r}")

        if not isinstance(self.session_reset_time, time):
            raise ValidationError("session_reset_time must be a datetime.time")
        if self.session_reset_time.tzinfo is not None:
            raise ValidationError(
                "session_reset_time must be naive (timezone comes from session_tz)"
            )
        if not isinstance(self.session_tz, str):
            raise ValidationError("session_tz must be an IANA timezone name")
        try:
            ZoneInfo(self.session_tz)
        except Exception as exc:
            raise ValidationError(f"unknown IANA timezone: {self.session_tz!r}") from exc


@dataclass
class _GuardData:
    """Mutable session state (kept private; exposed only via to_dict/from_dict)."""

    session_start: datetime | None = None
    last_ts: datetime | None = None
    baseline: Decimal | None = None
    equity: Decimal | None = None
    high_water: Decimal | None = None
    state: GuardState = GuardState.ACTIVE
    locked_announced: bool = False
    trades_today: int = 0
    net_qty: dict[str, Decimal] = field(default_factory=dict)


class DailyRiskGuard:
    """Evaluate trading events against a :class:`GuardConfig`."""

    def __init__(self, config: GuardConfig) -> None:
        if not isinstance(config, GuardConfig):
            raise TypeError("config must be a GuardConfig")
        self._config = config
        self._tz = ZoneInfo(config.session_tz)
        self._reset = config.session_reset_time
        self._data = _GuardData()

    @property
    def state(self) -> GuardState:
        """Current :class:`GuardState`."""
        return self._data.state

    def on_event(self, event: EquityUpdate | OrderRequest | Fill) -> Decision:
        """Process one event and return the resulting :class:`Decision`."""
        ts = getattr(event, "ts", None)
        if not isinstance(ts, datetime):
            raise TypeError("event must be an EquityUpdate, OrderRequest or Fill")
        if ts.tzinfo is None or ts.utcoffset() is None:
            raise ValidationError("event timestamp must be timezone-aware")
        ts_utc = ts.astimezone(_UTC)

        data = self._data
        if data.last_ts is not None and ts_utc < data.last_ts:
            previous = data.last_ts.isoformat()
            raise OutOfOrderEventError(
                f"event timestamp {ts.isoformat()} is older than previous {previous}"
            )

        start = session_start_utc(ts_utc, self._reset, self._tz)
        if data.session_start is None or start != data.session_start:
            self._start_session(start)
        data.last_ts = ts_utc

        if isinstance(event, EquityUpdate):
            return self._on_equity(event)
        if isinstance(event, OrderRequest):
            return self._on_order(event)
        if isinstance(event, Fill):
            return self._on_fill(event)
        raise TypeError("event must be an EquityUpdate, OrderRequest or Fill")

    def _start_session(self, start_utc: datetime) -> None:
        data = self._data
        data.session_start = start_utc
        data.baseline = None
        data.equity = None
        data.high_water = None
        data.state = GuardState.ACTIVE
        data.locked_announced = False
        data.trades_today = 0

    def _limit(self) -> Decimal:
        config = self._config
        if config.daily_loss_limit is not None:
            return config.daily_loss_limit
        assert config.daily_loss_limit_pct is not None
        assert self._data.baseline is not None
        return self._data.baseline * config.daily_loss_limit_pct / _HUNDRED

    def _loss(self) -> Decimal | None:
        data = self._data
        if data.baseline is None or data.equity is None:
            return None
        return data.baseline - data.equity

    def _lock_triggered(self) -> bool:
        loss = self._loss()
        if loss is None:
            return False
        if loss >= self._limit():
            return True
        data = self._data
        drawdown = self._config.trailing_drawdown
        if drawdown is None or data.high_water is None or data.equity is None:
            return False
        return data.high_water - data.equity >= drawdown

    def _evaluate_after_state_change(self) -> Decision:
        data = self._data
        if data.state is not GuardState.LOCKED and self._lock_triggered():
            data.state = GuardState.LOCKED
            data.locked_announced = True
            return Decision(DecisionKind.FLATTEN_ALL, Reason.LOCKED, data.state)
        if data.state is not GuardState.LOCKED:
            loss = self._loss()
            if loss is not None and loss >= self._config.warning_ratio * self._limit():
                data.state = GuardState.WARNING
            else:
                data.state = GuardState.ACTIVE
        return Decision(DecisionKind.NONE, Reason.NONE, data.state)

    def _on_equity(self, event: EquityUpdate) -> Decision:
        equity = to_decimal(event.equity, "equity")
        data = self._data
        if data.baseline is None:
            data.baseline = equity
            data.high_water = equity
        elif data.high_water is None or equity > data.high_water:
            data.high_water = equity
        data.equity = equity
        return self._evaluate_after_state_change()

    def _on_fill(self, event: Fill) -> Decision:
        qty_delta = to_decimal(event.qty_delta, "qty_delta")
        data = self._data
        net = data.net_qty.get(event.symbol, Decimal(0)) + qty_delta
        if net == 0:
            data.net_qty.pop(event.symbol, None)
        else:
            data.net_qty[event.symbol] = net
        return self._evaluate_after_state_change()

    def _on_order(self, event: OrderRequest) -> Decision:
        data = self._data
        if data.state is GuardState.LOCKED:
            return Decision(DecisionKind.REJECT, Reason.LOCKED, data.state)

        loss = self._loss()
        if loss is None:
            return Decision(DecisionKind.REJECT, Reason.NO_EQUITY_BASELINE, data.state)

        risk_amount = to_decimal(event.risk_amount, "risk_amount")
        if risk_amount < 0:
            raise ValidationError(f"risk_amount must be >= 0, got {risk_amount}")
        if loss + risk_amount >= self._limit():
            return Decision(DecisionKind.REJECT, Reason.WOULD_BREACH_LIMIT, data.state)

        qty = to_decimal(event.qty, "qty")
        config = self._config
        already_open = data.net_qty.get(event.symbol, Decimal(0)) != 0
        if (
            config.max_open_positions is not None
            and not already_open
            and qty != 0
            and len(data.net_qty) + 1 > config.max_open_positions
        ):
            return Decision(DecisionKind.REJECT, Reason.MAX_OPEN_POSITIONS, data.state)

        if config.max_trades_per_day is not None and data.trades_today >= config.max_trades_per_day:
            return Decision(DecisionKind.REJECT, Reason.MAX_TRADES, data.state)

        data.trades_today += 1
        return Decision(DecisionKind.ALLOW, Reason.OK, data.state)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable snapshot (Decimals encoded as strings)."""
        data = self._data
        return {
            "session_start": None if data.session_start is None else data.session_start.isoformat(),
            "last_ts": None if data.last_ts is None else data.last_ts.isoformat(),
            "baseline": None if data.baseline is None else str(data.baseline),
            "equity": None if data.equity is None else str(data.equity),
            "high_water": None if data.high_water is None else str(data.high_water),
            "state": data.state.value,
            "locked_announced": data.locked_announced,
            "trades_today": data.trades_today,
            "net_qty": {symbol: str(qty) for symbol, qty in data.net_qty.items()},
        }

    @classmethod
    def from_dict(cls, config: GuardConfig, data: dict[str, object]) -> DailyRiskGuard:
        """Rebuild a guard from :meth:`to_dict` output (config is supplied separately)."""
        guard = cls(config)

        def _dt(key: str) -> datetime | None:
            raw = data.get(key)
            if raw is None:
                return None
            if not isinstance(raw, str):
                raise ValidationError(f"field {key!r} must be an ISO-8601 string or null")
            return datetime.fromisoformat(raw)

        def _dec(key: str) -> Decimal | None:
            raw = data.get(key)
            if raw is None:
                return None
            if not isinstance(raw, str):
                raise ValidationError(f"field {key!r} must be a decimal string or null")
            return Decimal(raw)

        state_raw = data.get("state")
        net_raw = data.get("net_qty")
        trades_raw = data.get("trades_today")
        announced_raw = data.get("locked_announced")
        if not isinstance(net_raw, dict):
            raise ValidationError("field 'net_qty' must be a mapping")
        if isinstance(trades_raw, bool) or not isinstance(trades_raw, int):
            raise ValidationError("field 'trades_today' must be an int")
        if not isinstance(announced_raw, bool):
            raise ValidationError("field 'locked_announced' must be a bool")

        guard._data = _GuardData(
            session_start=_dt("session_start"),
            last_ts=_dt("last_ts"),
            baseline=_dec("baseline"),
            equity=_dec("equity"),
            high_water=_dec("high_water"),
            state=GuardState(state_raw),
            locked_announced=announced_raw,
            trades_today=trades_raw,
            net_qty={str(k): Decimal(str(v)) for k, v in net_raw.items()},
        )
        return guard
