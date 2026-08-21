"""Tests for cart + pricing contract (task fixture t-016)."""

import pytest

from cart import calculate_total
from pricing import discount_for


def test_discount_for_quantity_based():
    assert discount_for(1) == 0.0
    assert discount_for(9) == 0.0
    assert discount_for(10) == 0.05
    assert discount_for(49) == 0.05
    assert discount_for(50) == 0.10
    assert discount_for(99) == 0.10
    assert discount_for(100) == 0.15


def test_single_item_no_discount():
    assert calculate_total([("a", 10.0, 1)]) == 10.0


def test_single_item_with_discount():
    # 10 x 10.00 at 5% -> 95.00
    assert calculate_total([("a", 10.0, 10)]) == 95.0


def test_discount_depends_on_quantity_not_price():
    # expensive single item: no discount despite high price
    assert calculate_total([("a", 1000.0, 1)]) == 1000.0
    # cheap bulk item: discount applies
    assert calculate_total([("a", 0.1, 100)]) == pytest.approx(8.5, abs=0.001)


def test_discount_per_item_not_on_total():
    # mixed: one discounted, one not
    items = [("a", 10.0, 10), ("b", 5.0, 1)]
    assert calculate_total(items) == 100.0  # 95.0 + 5.0


def test_rounding_per_position():
    # 3 x 3.33 at 0% -> 9.99
    assert calculate_total([("a", 3.33, 3)]) == 9.99


def test_bulk_tier_100():
    assert calculate_total([("a", 10.0, 100)]) == 850.0  # 15% off
