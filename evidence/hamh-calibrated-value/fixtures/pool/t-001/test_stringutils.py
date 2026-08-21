"""Tests for stringutils (task fixture t-001)."""

import pytest

from stringutils import is_palindrome


@pytest.mark.parametrize(
    "value,expected",
    [
        ("racecar", True),
        ("Racecar", True),
        ("A man, a plan, a canal: Panama", True),
        ("Never odd or even", True),
        ("hello", False),
        ("hello world", False),
        ("", True),
        ("!!! ???", True),
        ("ülü", True),
        ("Ärger", False),
        ("Rats live on no evil star", True),
        ("Was it a car or a cat I saw?", True),
        ("No lemon, no melon", True),
    ],
)
def test_is_palindrome(value, expected):
    assert is_palindrome(value) is expected
