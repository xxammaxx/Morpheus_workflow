"""Tests for luhn (task fixture t-007)."""

import pytest

from luhn import compute_check_digit, validate_card


@pytest.mark.parametrize(
    "partial,expected",
    [
        ("7992739871", 3),  # classic Luhn example
        ("123456789", 7),
        ("424242424242424", 2),  # Visa-style
        ("0", 0),
        ("1", 8),
        ("555555555555444", 4),  # Mastercard-style
        ("37828224631000", 5),  # Amex-style
    ],
)
def test_compute_check_digit(partial, expected):
    assert compute_check_digit(partial) == expected


@pytest.mark.parametrize(
    "number,expected",
    [
        ("79927398713", True),
        ("4242424242424242", True),
        ("5555555555554444", True),
        ("378282246310005", True),
        ("79927398710", False),
        ("4242424242424241", False),
        ("1234567812345678", False),
        ("", False),
        ("1234abcd", False),
        ("4111 1111 1111 1111", False),  # no spaces allowed
    ],
)
def test_validate_card(number, expected):
    assert validate_card(number) is expected


def test_check_digit_roundtrip():
    partial = "401288888888188"
    d = compute_check_digit(partial)
    assert validate_card(partial + str(d)) is True


def test_check_digit_range():
    for partial in ["1", "12", "1234567", "7992739871", "555555555555444"]:
        d = compute_check_digit(partial)
        assert 0 <= d <= 9
