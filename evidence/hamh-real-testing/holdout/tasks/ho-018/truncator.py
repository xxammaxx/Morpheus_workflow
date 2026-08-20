"""Truncate text to max_chars with an ellipsis."""


def truncate(text, max_chars):
    if text is None:
        return ""
    if len(text) <= max_chars:
        return text
    # BUG: for max_chars <= 3 the slice index goes negative
    # and keeps too many characters
    return text[:max_chars - 3] + "..."

