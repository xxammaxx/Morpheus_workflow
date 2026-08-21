"""Tests for ordersummary (task fixture t-011)."""

import pytest

from ordersummary import summarize


def test_single_item_no_discount():
    r = summarize([("a", 10.00, 1)])
    assert r == {"subtotal": 10.0, "tax": 1.9, "total": 11.9}


def test_quantity_discount_10():
    # 10 * 10.00 = 100.00 - 5% = 95.00; tax 18.05
    r = summarize([("a", 10.00, 10)])
    assert r["subtotal"] == 95.0
    assert r["tax"] == pytest.approx(18.05, abs=0.001)
    assert r["total"] == pytest.approx(113.05, abs=0.001)


def test_quantity_discount_50():
    # 50 * 10.00 = 500.00 - 10% = 450.00; tax 85.50
    r = summarize([("a", 10.00, 50)])
    assert r["subtotal"] == 450.0
    assert r["tax"] == pytest.approx(85.5, abs=0.001)
    assert r["total"] == pytest.approx(535.5, abs=0.001)


def test_discount_thresholds():
    assert summarize([("a", 1.00, 9)])["subtotal"] == 9.0
    assert summarize([("a", 1.00, 10)])["subtotal"] == 9.5
    assert summarize([("a", 1.00, 49)])["subtotal"] == 46.55
    assert summarize([("a", 1.00, 50)])["subtotal"] == 45.0


def test_multiple_items():
    r = summarize([("a", 10.00, 2), ("b", 3.33, 3)])
    # a: 20.00 net; b: 9.99 net; subtotal 29.99
    assert r["subtotal"] == 29.99
    assert r["tax"] == pytest.approx(5.70, abs=0.001)  # 3.80 + 1.90 (rounded per item)
    assert r["total"] == pytest.approx(35.69, abs=0.001)


def test_rounding_half_up():
    # 0.005 -> rounds up to 0.01 (commercial rounding)
    r = summarize([("a", 0.005, 1)])
    assert r["subtotal"] == 0.01
    assert r["total"] == pytest.approx(0.01 + round(0.005 * 0.19, 2), abs=0.001)


def test_zero_quantity():
    r = summarize([("a", 10.00, 0)])
    assert r == {"subtotal": 0.0, "tax": 0.0, "total": 0.0}


def test_empty_order():
    assert summarize([]) == {"subtotal": 0.0, "tax": 0.0, "total": 0.0}
