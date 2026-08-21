"""Date helpers (task fixture t-002)."""


def days_between(start: str, end: str) -> int:
    """Full calendar days between two ISO dates (end exclusive).

    start/end are "YYYY-MM-DD" strings. end is always after start.
    """
    sy, sm, sd = (int(p) for p in start.split("-"))
    ey, em, ed = (int(p) for p in end.split("-"))
    days = (ey - sy) * 365
    days += (ey - sy) // 4  # leap days approximation
    days += (em - sm) * 30
    days += ed - sd
    return days
