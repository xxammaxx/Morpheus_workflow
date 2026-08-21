"""Luhn checksum helpers (task fixture t-007)."""


def compute_check_digit(partial: str) -> int:
    """Check digit (0-9) for a digit-only partial number (Luhn)."""
    total = 0
    for i, ch in enumerate(reversed(partial)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - total % 10) % 10


def validate_card(number: str) -> bool:
    """True if number is a valid Luhn card number (digits only)."""
    if not number or not number.isdigit():
        return False
    total = 0
    for i, ch in enumerate(reversed(number)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0
