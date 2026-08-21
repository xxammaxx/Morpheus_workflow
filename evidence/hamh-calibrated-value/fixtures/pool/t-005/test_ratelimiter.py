"""Tests for ratelimiter (task fixture t-005)."""

import pytest

from ratelimiter import TokenBucket


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def test_full_at_start():
    clock = FakeClock()
    b = TokenBucket(rate=10.0, capacity=5.0, now=clock)
    assert b.consume(5) is True
    assert b.consume(1) is False


def test_refill_over_time():
    clock = FakeClock()
    b = TokenBucket(rate=10.0, capacity=5.0, now=clock)
    assert b.consume(5) is True
    clock.advance(0.5)
    assert b.consume(5) is True  # 0.5s * 10/s = 5 tokens
    assert b.consume(1) is False


def test_capacity_caps_tokens():
    clock = FakeClock()
    b = TokenBucket(rate=1.0, capacity=3.0, now=clock)
    assert b.consume(3) is True
    clock.advance(60.0)
    # 60 tokens would accrue but capacity is 3
    assert b.consume(3) is True
    assert b.consume(1) is False


def test_partial_consumption():
    clock = FakeClock()
    b = TokenBucket(rate=10.0, capacity=10.0, now=clock)
    assert b.consume(4) is True
    assert b.consume(4) is True
    assert b.consume(4) is False
    clock.advance(0.2)  # 2 tokens refilled
    assert b.consume(2) is True


def test_no_time_advance_no_refill():
    clock = FakeClock()
    b = TokenBucket(rate=100.0, capacity=2.0, now=clock)
    assert b.consume(2) is True
    assert b.consume(1) is False
    assert b.consume(1) is False  # no refill without time
