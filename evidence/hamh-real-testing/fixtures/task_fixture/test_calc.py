"""Test suite for calc.py — one test is failing by design (fixture)."""

import pytest

from calc import add, divide, multiply, power, subtract


def test_add():
    assert add(2, 3) == 5
    assert add(-1, 1) == 0


def test_subtract():
    assert subtract(5, 3) == 2
    assert subtract(0, 4) == -4


def test_multiply():
    assert multiply(3, 4) == 12
    assert multiply(-2, 5) == -10
    assert multiply(0, 9) == 0


def test_divide():
    assert divide(10, 2) == 5
    assert divide(1, 4) == 0.25


def test_divide_by_zero():
    with pytest.raises(ValueError):
        divide(1, 0)


def test_power():
    assert power(2, 3) == 8
    assert power(5, 0) == 1
