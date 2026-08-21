"""Booking conflict check (task fixture t-021)."""

from datetime import datetime


def _parse(iso: str) -> datetime:
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")


def check_conflicts(bookings) -> bool:
    """True if any two bookings of the same resource overlap ([start, end))."""
    by_resource = {}
    for resource, start, end in bookings:
        by_resource.setdefault(resource, []).append((_parse(start), _parse(end)))
    for resource, spans in by_resource.items():
        spans.sort()
        for i in range(len(spans) - 1):
            for j in range(i + 1, len(spans)):
                a_start, a_end = spans[i]
                b_start, b_end = spans[j]
                if b_start <= a_end and a_start <= b_end:
                    return True
    return False
