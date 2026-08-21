"""Window helper (task fixture t-023)."""


def window_items(items, start: int, end: int) -> list:
    """Items in index range [start, end) with Python-style negative start."""
    if not items:
        return []
    n = len(items)
    if start < 0:
        start = n + start
    if end < 0:
        end = n + end
    if end > n:
        end = n
    return items[start : end + 1]
