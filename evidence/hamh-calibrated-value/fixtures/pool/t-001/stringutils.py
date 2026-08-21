"""String utilities (task fixture t-001)."""


def is_palindrome(s: str) -> bool:
    """Return True if s is a palindrome (case-insensitive, alphanumeric only)."""
    cleaned = "".join(c for c in s if c.isalnum())
    cleaned = cleaned.lower()
    return cleaned == reversed(cleaned)
