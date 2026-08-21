"""Tests for rangevalidator (task fixture t-022)."""

import pytest

from rangevalidator import validate_ranges


def test_all_valid():
    assert validate_ranges([(1, 10), (5, 5)], 1, 10) == []


def test_below_lo_invalid():
    assert validate_ranges([(0, 10)], 1, 10) == [(0, 10)]


def test_above_hi_invalid():
    assert validate_ranges([(1, 11)], 1, 10) == [(1, 11)]


def test_partially_outside_invalid():
    assert validate_ranges([(8, 12)], 1, 10) == [(8, 12)]


def test_boundary_touching_valid():
    # end == hi and start == lo are valid (inclusive window)
    assert validate_ranges([(1, 10), (5, 10), (1, 7)], 1, 10) == []


def test_single_point_valid():
    assert validate_ranges([(3, 3), (10, 10)], 1, 10) == []


def test_start_greater_end_invalid():
    assert validate_ranges([(7, 3)], 1, 10) == [(7, 3)]


def test_mixed():
    ranges = [(1, 10), (0, 9), (2, 11), (5, 6), (9, 10)]
    assert validate_ranges(ranges, 1, 10) == [(0, 9), (2, 11)]


def test_overlap_allowed():
    ranges = [(1, 5), (4, 8), (7, 10)]
    assert validate_ranges(ranges, 1, 10) == []


def test_empty():
    assert validate_ranges([], 1, 10) == []
