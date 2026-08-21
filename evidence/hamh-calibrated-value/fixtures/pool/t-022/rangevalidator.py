"""Range validator (task fixture t-022)."""


def validate_ranges(ranges, lo: int, hi: int) -> list:
    """Invalid ranges from ranges (start, end) against window [lo, hi]."""
    invalid = []
    for start, end in ranges:
        if start > lo or end < hi:
            invalid.append((start, end))
    return invalid
