"""Tests for csvfields (task fixture t-003)."""

import pytest

from csvfields import parse_csv_line


@pytest.mark.parametrize(
    "line,expected",
    [
        ("a,b,c", ["a", "b", "c"]),
        ("a, b ,c", ["a", "b", "c"]),
        ('"a,b",c', ["a,b", "c"]),
        ('a,"b,c"', ["a", "b,c"]),
        ('"he said ""hi""",x', ['he said "hi"', "x"]),
        ('" leading space ",x', [" leading space ", "x"]),
        ("a,,c", ["a", "", "c"]),
        ("", [""]),
        ('"",x', ["", "x"]),
        ('"a""b",c', ['a"b', "c"]),
        (" plain , field ", ["plain", "field"]),
    ],
)
def test_parse_csv_line(line, expected):
    assert parse_csv_line(line) == expected
