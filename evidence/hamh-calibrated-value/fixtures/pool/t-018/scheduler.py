"""Task scheduler (task fixture t-018)."""

from datetime import datetime


def _parse(iso: str) -> datetime:
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")


def next_due(tasks, now: str):
    """Next task with due_at >= now; earliest due, then priority, then created_at."""
    now_dt = _parse(now)
    candidates = [t for t in tasks if _parse(t["due_at"]) > now_dt]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda t: (
            _parse(t["due_at"]),
            _parse(t["created_at"]),
        ),
    )
