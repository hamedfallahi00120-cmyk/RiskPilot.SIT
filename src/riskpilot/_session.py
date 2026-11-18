"""Session-boundary arithmetic for the daily risk guard.

Turns a wall-clock reset time in an IANA timezone into a UTC instant, handling
the two daylight-saving edge cases: a time inside the spring-forward gap and a
time inside the fall-back overlap. This module is a pure leaf (stdlib only).
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

__all__ = ["resolve_boundary", "session_start_utc"]

_UTC = UTC


def resolve_boundary(naive: datetime, tz: ZoneInfo) -> datetime:
    """Return the timezone-aware local boundary for ``naive`` wall-clock time.

    A normal time resolves to itself; a time in a DST gap resolves to the first
    instant after the gap (the transition instant); a time that occurs twice
    resolves to the first occurrence (``fold=0``).
    """
    candidate = naive.replace(tzinfo=tz, fold=0)
    roundtrip = candidate.astimezone(_UTC).astimezone(tz).replace(tzinfo=None)
    if roundtrip == naive:
        return candidate

    # Gap (spring forward): ``naive`` does not exist locally. The boundary is the
    # first instant after the gap, i.e. the transition instant. US transitions
    # occur after local midnight, so a binary search within the local day finds
    # the first UTC instant whose offset differs from the pre-transition offset.
    day_start = datetime.combine(naive.date(), time(0, 0), tzinfo=tz).astimezone(_UTC)
    offset_before = day_start.astimezone(tz).utcoffset()
    low = day_start
    high = day_start + timedelta(days=1, hours=3)
    while high - low > timedelta(microseconds=1):
        mid = low + (high - low) / 2
        if mid.astimezone(tz).utcoffset() == offset_before:
            low = mid
        else:
            high = mid
    return high.astimezone(tz)


def session_start_utc(ts_utc: datetime, reset: time, tz: ZoneInfo) -> datetime:
    """Return the UTC instant of the most recent session boundary at or before ``ts_utc``."""
    local = ts_utc.astimezone(tz)
    boundary = resolve_boundary(datetime.combine(local.date(), reset), tz)
    if boundary > local:
        boundary = resolve_boundary(datetime.combine(local.date() - timedelta(days=1), reset), tz)
    return boundary.astimezone(_UTC)
