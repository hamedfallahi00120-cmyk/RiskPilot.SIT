"""Session boundary arithmetic (DST-safe, pure).

A *session* is the interval between two consecutive reset boundaries in the
configured timezone. A boundary is defined as the **earliest UTC instant whose
local wall-clock time is at or past the reset wall time** for that local date.
That single definition gives all three behaviours the spec asks for:

* normal day: the boundary is the reset wall time itself;
* DST gap (wall time never happens): the boundary is the first instant after
  the gap, i.e. the transition instant;
* DST overlap (wall time happens twice): the boundary is the first occurrence.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, tzinfo

_UTC = UTC
_ONE_MICROSECOND = timedelta(microseconds=1)


def _offset_at(instant: datetime, tz: tzinfo) -> timedelta:
    """Return the UTC offset in effect at ``instant`` in timezone ``tz``."""
    return instant.astimezone(tz).utcoffset() or timedelta(0)


def _find_transition(lo: datetime, hi: datetime, tz: tzinfo) -> datetime:
    """Bisect the first instant in ``(lo, hi]`` where the offset changes."""
    target = _offset_at(hi, tz)
    while hi - lo > _ONE_MICROSECOND:
        mid = lo + (hi - lo) / 2
        if _offset_at(mid, tz) == target:
            hi = mid
        else:
            lo = mid
    return hi


def boundary_utc(local_date: date, reset_time: time, tz: tzinfo) -> datetime:
    """Return the session boundary for ``local_date`` as an aware UTC datetime.

    Parameters
    ----------
    local_date:
        The local calendar date the reset belongs to.
    reset_time:
        Naive local wall-clock reset time.
    tz:
        A ``tzinfo`` (normally a :class:`zoneinfo.ZoneInfo`).

    """
    naive = datetime.combine(local_date, reset_time)
    first = naive.replace(tzinfo=tz, fold=0)
    second = naive.replace(tzinfo=tz, fold=1)
    first_utc = first.astimezone(_UTC)
    second_utc = second.astimezone(_UTC)
    if first_utc == second_utc:
        return first_utc
    existing = [
        candidate
        for candidate in (first_utc, second_utc)
        if candidate.astimezone(tz).replace(tzinfo=None) == naive
    ]
    if existing:
        return min(existing)
    low, high = min(first_utc, second_utc), max(first_utc, second_utc)
    return _find_transition(low, high, tz)


def session_start(instant: datetime, reset_time: time, tz: tzinfo) -> datetime:
    """Return the start boundary of the session containing ``instant``."""
    local_date = instant.astimezone(tz).date()
    candidate = boundary_utc(local_date, reset_time, tz)
    if candidate <= instant:
        return candidate
    return boundary_utc(local_date - timedelta(days=1), reset_time, tz)
