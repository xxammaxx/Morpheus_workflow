"""Timetable slot finder (task fixture t-008)."""

from datetime import datetime, timedelta


def _parse(iso: str) -> datetime:
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")


def find_free_slot(busy, duration_min: int, start: str, end: str):
    """First free slot of duration_min fully inside [start, end]. UTC.

    Returns ISO start string or None.
    """
    start_dt = _parse(start)
    end_dt = _parse(end)
    blocks = sorted((_parse(s), _parse(e)) for s, e in busy)
    # merge overlapping blocks
    merged = []
    for s, e in blocks:
        if merged and s < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    cursor = start_dt
    for s, e in merged:
        if s > cursor and (s - cursor) > timedelta(minutes=duration_min):
            return cursor.strftime("%Y-%m-%dT%H:%M:%SZ")
        cursor = max(cursor, e)
    if (end_dt - cursor) > timedelta(minutes=duration_min):
        return cursor.strftime("%Y-%m-%dT%H:%M:%SZ")
    return None
