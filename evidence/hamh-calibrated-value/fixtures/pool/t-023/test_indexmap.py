"""Tests for indexmap (task fixture t-023)."""

import pytest

from indexmap import window_items

L = [0, 1, 2, 3, 4, 5]


def test_basic_window():
    assert window_items(L, 1, 4) == [1, 2, 3]


def test_end_exclusive():
    assert window_items(L, 0, 2) == [0, 1]


def test_negative_start_from_end():
    assert window_items(L, -3, 5) == [3, 4]


def test_negative_start_and_default_end():
    assert window_items(L, -2, 6) == [4, 5]


def test_end_beyond_length_clamped():
    assert window_items(L, 3, 99) == [3, 4, 5]


def test_negative_start_clamped_to_zero():
    assert window_items(L, -99, 3) == [0, 1, 2]


def test_start_equal_end_empty():
    assert window_items(L, 2, 2) == []


def test_start_greater_than_end_empty():
    assert window_items(L, 4, 2) == []


def test_start_beyond_length_empty():
    assert window_items(L, 9, 12) == []


def test_negative_end():
    assert window_items(L, 1, -1) == [1, 2, 3, 4]


def test_full_range():
    assert window_items(L, 0, 6) == [0, 1, 2, 3, 4, 5]


def test_empty_list():
    assert window_items([], 0, 5) == []
    assert window_items([], -2, 5) == []


def test_single_element():
    assert window_items([42], 0, 1) == [42]
    assert window_items([42], -1, 1) == [42]
    assert window_items([42], 0, 0) == []
