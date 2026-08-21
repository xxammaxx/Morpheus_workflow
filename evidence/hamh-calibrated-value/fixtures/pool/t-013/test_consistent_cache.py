"""Tests for consistent_cache (task fixture t-013)."""

import pytest

from consistent_cache import TtlCache


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def test_basic_set_get():
    clock = FakeClock()
    c = TtlCache(5, 60.0, clock)
    c.set("a", 1)
    assert c.get("a") == 1


def test_expiry():
    clock = FakeClock()
    c = TtlCache(5, 60.0, clock)
    c.set("a", 1)
    clock.advance(59.0)
    assert c.get("a") == 1
    clock.advance(1.01)
    assert c.get("a") is None


def test_expiry_exact_boundary():
    # entry expires EXACTLY at now == expires_at
    clock = FakeClock()
    c = TtlCache(5, 60.0, clock)
    c.set("a", 1)
    clock.advance(60.0)
    assert c.get("a") is None


def test_expired_entry_removed():
    clock = FakeClock()
    c = TtlCache(5, 60.0, clock)
    c.set("a", 1)
    clock.advance(61.0)
    assert c.get("a") is None
    assert c.get("a") is None  # size must not grow again
    # capacity check: expired entries must be gone before eviction
    c.set("b", 2)
    c.set("c", 3)
    assert c.get("b") == 2


def test_capacity_evicts_oldest_expiry():
    clock = FakeClock()
    c = TtlCache(2, 60.0, clock)
    c.set("a", 1)  # expires t+60
    clock.advance(10.0)
    c.set("b", 2)  # expires t+70
    clock.advance(10.0)
    c.set("c", 3)  # capacity 2 -> evict "a" (earliest expiry)
    assert c.get("a") is None
    assert c.get("b") == 2
    assert c.get("c") == 3


def test_set_updates_existing_key():
    clock = FakeClock()
    c = TtlCache(2, 60.0, clock)
    c.set("a", 1)
    c.set("a", 2)
    assert c.get("a") == 2
    assert len(c._store) == 1


def test_no_ttl_refresh_on_get():
    clock = FakeClock()
    c = TtlCache(5, 60.0, clock)
    c.set("a", 1)
    clock.advance(30.0)
    assert c.get("a") == 1
    clock.advance(30.01)
    assert c.get("a") is None  # read must not extend lifetime


def test_returned_value_is_copy():
    clock = FakeClock()
    c = TtlCache(5, 60.0, clock)
    c.set("a", {"x": [1, 2]})
    out = c.get("a")
    out["x"].append(3)
    assert c.get("a")["x"] == [1, 2]


def test_eviction_after_expiry_does_not_remove_live_entries():
    clock = FakeClock()
    c = TtlCache(2, 60.0, clock)
    c.set("a", 1)
    c.set("b", 2)
    clock.advance(61.0)  # both expired
    c.set("c", 3)  # must evict one expired entry, keep the other slot free
    assert c.get("a") is None
    assert c.get("b") is None
    assert c.get("c") == 3
