"""Daily risk guard: session baselines, loss limits and order gating.

The guard is a deterministic state machine. It never reads the clock: every
event carries its own timezone-aware timestamp, which decides the session.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from riskpilot._decimal import to_decimal
from riskpilot._session import session_start
from riskpilot.errors import ConfigError, OutOfOrderEventError, ValidationError

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
        if self.session_reset_time.tzinfo is not None:
            msg = "session_reset_time must be a naive local time (timezone comes from session_tz)"
            raise ValidationError(msg)
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
class _Session:
    """Mutable per-session bookkeeping (never exposed outside the guard)."""

    start: datetime
    baseline: Decimal | None = None
    equity: Decimal | None = None
    high_water: Decimal | None = None
    trades: int = 0
    flatten_emitted: bool = False
    trailing_breached: bool = False


@dataclass
class DailyRiskGuard:
    """Session-scoped daily risk guard.

    Feed every event to :meth:`on_event` in timestamp order and honour the
    returned :class:`Decision`.
    """

    config: GuardConfig
    _open_qty: dict[str, Decimal] = field(default_factory=dict, init=False, repr=False)
    _session: _Session | None = field(default=None, init=False, repr=False)
    _last_ts: datetime | None = field(default=None, init=False, repr=False)
    _state: GuardState = field(default=GuardState.ACTIVE, init=False, repr=False)

    # ------------------------------------------------------------------ state
    @property
    def state(self) -> GuardState:
        """Current :class:`GuardState`."""
        return self._state

    @property
    def session_start(self) -> datetime | None:
        """Start boundary of the current session, or ``None`` before the first event."""
        return None if self._session is None else self._session.start

    @property
    def baseline_equity(self) -> Decimal | None:
        """Session baseline equity, or ``None`` when no equity snapshot was seen."""
        return None if self._session is None else self._session.baseline

    @property
    def high_water_equity(self) -> Decimal | None:
        """Session equity high-water mark, or ``None``."""
        return None if self._session is None else self._session.high_water

    @property
    def trades_today(self) -> int:
        """Number of allowed order requests in the current session."""
        return 0 if self._session is None else self._session.trades

    def open_positions(self) -> dict[str, Decimal]:
        """Return a copy of the net non-zero quantity per symbol."""
        return dict(self._open_qty.items())

    def current_loss(self) -> Decimal:
        """Return the session loss (``baseline - current equity``, floored at 0)."""
        session = self._session
        if session is None or session.baseline is None or session.equity is None:
            return _ZERO
        return max(_ZERO, session.baseline - session.equity)

    def loss_limit(self) -> Decimal | None:
        """Return the absolute loss limit for the current session, if known."""
        if self.config.daily_loss_limit is not None:
            return self.config.daily_loss_limit
        if self._session is None or self._session.baseline is None:
            return None
        pct = self.config.daily_loss_limit_pct
        assert pct is not None  # nosec
        return self._session.baseline * pct / _HUNDRED

    # ----------------------------------------------------------------- events
    def on_event(self, event: Event) -> Decision:
        """Process one event and return the resulting :class:`Decision`."""
        self._check_ts(event.ts, event_name=type(event).__name__)
        reset = self._roll_session(event.ts)
        if isinstance(event, EquityUpdate):
            decision = self._on_equity(event)
        elif isinstance(event, Fill):
            decision = self._on_fill(event)
        else:
            decision = self._on_order(event)
        if reset and decision.kind is DecisionKind.NONE:
            return Decision(DecisionKind.NONE, Reason.SESSION_RESET, self._state)
        return decision

    def _check_ts(self, ts: datetime, *, event_name: str) -> None:
        if ts.tzinfo is None or ts.utcoffset() is None:
            msg = f"{event_name}.ts must be timezone-aware"
            raise ValidationError(msg)
        if self._last_ts is not None and ts < self._last_ts:
            msg = f"{event_name}.ts {ts.isoformat()} is older than the previous event"
            raise OutOfOrderEventError(msg)
        self._last_ts = ts

    def _roll_session(self, ts: datetime) -> bool:
        tz = self.config.zoneinfo()
        start = session_start(ts, self.config.session_reset_time, tz)
        if self._session is not None and start == self._session.start:
            return False
        self._session = _Session(start=start)
        self._state = GuardState.ACTIVE
        return True

    def _on_equity(self, event: EquityUpdate) -> Decision:
        equity = to_decimal(event.equity, field="equity")
        session = self._session
        if session is None:  # pragma: no cover - always set by _roll_session
            msg = "guard has no active session"
            raise RuntimeError(msg)
        if session.baseline is None:
            session.baseline = equity
            session.high_water = equity
            session.equity = equity
            return Decision(DecisionKind.NONE, Reason.EQUITY_UPDATE, self._state)
        session.equity = equity
        if session.high_water is None or equity > session.high_water:
            session.high_water = equity
        return self._evaluate_breach()

    def _on_fill(self, event: Fill) -> Decision:
        delta = to_decimal(event.qty_delta, field="qty_delta")
        if not isinstance(event.symbol, str) or not event.symbol:
            msg = "Fill.symbol must be a non-empty string"
            raise ValidationError(msg)
        net = self._open_qty.get(event.symbol, _ZERO) + delta
        if net == _ZERO:
            self._open_qty.pop(event.symbol, None)
        else:
            self._open_qty[event.symbol] = net
        return Decision(DecisionKind.NONE, Reason.FILL_RECORDED, self._state)

    def _on_order(self, event: OrderRequest) -> Decision:
        session = self._session
        if session is None:  # pragma: no cover - always set by _roll_session
            msg = "guard has no active session"
            raise RuntimeError(msg)
        if session.baseline is None:
            return self._reject(Reason.NO_EQUITY_BASELINE)
        if self._state is GuardState.LOCKED:
            return self._reject(Reason.LOCKED)

        risk_amount = to_decimal(event.risk_amount, field="risk_amount")
        if risk_amount <= _ZERO:
            msg = f"OrderRequest.risk_amount must be > 0, got {risk_amount}"
            raise ValidationError(msg)

        limit = self.loss_limit()
        if limit is not None and self.current_loss() + risk_amount >= limit:
            return self._reject(Reason.WOULD_BREACH_LIMIT)
        max_positions = self.config.max_open_positions
        new_symbol = event.symbol not in self._open_qty
        if max_positions is not None and new_symbol and len(self._open_qty) + 1 > max_positions:
            return self._reject(Reason.MAX_OPEN_POSITIONS)
        max_trades = self.config.max_trades_per_day
        if max_trades is not None and session.trades + 1 > max_trades:
            return self._reject(Reason.MAX_TRADES)

        session.trades += 1
        return Decision(DecisionKind.ALLOW, Reason.ORDER_ALLOWED, self._state)

    def _reject(self, reason: Reason) -> Decision:
        return Decision(DecisionKind.REJECT, reason, self._state)

    def _evaluate_breach(self) -> Decision:
        session = self._session
        if session is None:  # pragma: no cover - always set by _roll_session
            msg = "guard has no active session"
            raise RuntimeError(msg)
        loss = self.current_loss()
        limit = self.loss_limit()
        drawdown_limit = self.config.trailing_drawdown
        if (
            drawdown_limit is not None
            and session.high_water is not None
            and session.equity is not None
            and session.high_water - session.equity >= drawdown_limit
        ):
            session.trailing_breached = True

        if session.trailing_breached or (limit is not None and loss >= limit):
            if self._state is not GuardState.LOCKED:
                self._state = GuardState.LOCKED
                reason = Reason.TRAILING_DRAWDOWN if session.trailing_breached else Reason.LOCKED
                if session.flatten_emitted:
                    return Decision(DecisionKind.NONE, reason, self._state)
                session.flatten_emitted = True
                return Decision(DecisionKind.FLATTEN_ALL, reason, self._state)
            return Decision(DecisionKind.NONE, Reason.LOCKED, self._state)

        if limit is not None:
            if loss >= limit * self.config.warning_ratio:
                self._state = GuardState.WARNING
            else:
                self._state = GuardState.ACTIVE
        return Decision(DecisionKind.NONE, Reason.EQUITY_UPDATE, self._state)

    # ---------------------------------------------------------- serialisation
    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serialisable state (Decimals become strings)."""
        session = self._session
        session_data: dict[str, Any] | None = None
        if session is not None:

            def text(value: Decimal | None) -> str | None:
                return None if value is None else str(value)

            session_data = {
                "start": session.start.isoformat(),
                "baseline": text(session.baseline),
                "equity": text(session.equity),
                "high_water": text(session.high_water),
                "trades": session.trades,
                "flatten_emitted": session.flatten_emitted,
                "trailing_breached": session.trailing_breached,
            }
        return {
            "state": self._state.value,
            "last_ts": None if self._last_ts is None else self._last_ts.isoformat(),
            "session": session_data,
            "open_positions": {s: str(q) for s, q in self._open_qty.items()},
        }

    @classmethod
    def from_dict(cls, config: GuardConfig, data: dict[str, Any]) -> DailyRiskGuard:
        """Rebuild a guard from :meth:`to_dict` output.

        Raises
        ------
        ConfigError
            If the payload is malformed.

        """
        guard = cls(config=config)
        try:
            guard._state = GuardState(data["state"])
            last_ts = data.get("last_ts")
            if last_ts is not None:
                guard._last_ts = datetime.fromisoformat(last_ts)
            open_positions = data.get("open_positions") or {}
            guard._open_qty = {
                str(symbol): Decimal(str(qty)) for symbol, qty in open_positions.items()
            }
            session = data.get("session")
            if session is not None:
                guard._session = _Session(
                    start=datetime.fromisoformat(session["start"]),
                    baseline=_opt_decimal(session.get("baseline")),
                    equity=_opt_decimal(session.get("equity")),
                    high_water=_opt_decimal(session.get("high_water")),
                    trades=int(session.get("trades", 0)),
                    flatten_emitted=bool(session.get("flatten_emitted", False)),
                    trailing_breached=bool(session.get("trailing_breached", False)),
                )
        except (KeyError, ValueError, ArithmeticError) as exc:
            msg = f"invalid guard state payload: {exc}"
            raise ConfigError(msg) from exc
        return guard


def _opt_decimal(value: object) -> Decimal | None:
    """Convert an optional serialised Decimal back to ``Decimal``."""
    return None if value is None else Decimal(str(value))
