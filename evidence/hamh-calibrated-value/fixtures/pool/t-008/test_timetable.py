"""Tests for timetable (task fixture t-008)."""

import pytest

from timetable import find_free_slot

D = "2026-08-21T"
DAY = "2026-08-21"


@pytest.mark.parametrize(
    "busy,duration,start,end,expected",
    [
        # basic free gap
        (
            [("2026-08-21T09:00:00Z", "2026-08-21T10:00:00Z")],
            30,
            f"{D}08:00:00Z",
            f"{D}12:00:00Z",
            f"{D}08:00:00Z",
        ),
        # slot directly after a busy block
        (
            [("2026-08-21T09:00:00Z", "2026-08-21T10:00:00Z")],
            30,
            f"{D}09:30:00Z",
            f"{D}12:00:00Z",
            f"{D}10:00:00Z",
        ),
        # exact-fit gap: duration == distance to busy start (boundary!)
        (
            [("2026-08-21T10:00:00Z", "2026-08-21T11:00:00Z")],
            60,
            f"{D}08:00:00Z",
            f"{D}12:00:00Z",
            f"{D}09:00:00Z",
        ),
        # exact-fit at window end: slot ends exactly at end (boundary!)
        (
            [("2026-08-21T08:00:00Z", "2026-08-21T09:00:00Z")],
            60,
            f"{D}08:00:00Z",
            f"{D}11:00:00Z",
            f"{D}10:00:00Z",
        ),
        # no slot: too short gap
        (
            [("2026-08-21T08:00:00Z", "2026-08-21T10:00:00Z")],
            90,
            f"{D}08:00:00Z",
            f"{D}11:30:00Z",
            None,
        ),
        # overlapping + unsorted busy blocks are merged
        (
            [
                ("2026-08-21T10:00:00Z", "2026-08-21T11:00:00Z"),
                ("2026-08-21T09:00:00Z", "2026-08-21T09:30:00Z"),
            ],
            30,
            f"{D}08:00:00Z",
            f"{D}12:00:00Z",
            f"{D}09:30:00Z",
        ),
        # busy block reaches beyond window end
        (
            [("2026-08-21T08:00:00Z", "2026-08-21T13:00:00Z")],
            30,
            f"{D}08:00:00Z",
            f"{D}12:00:00Z",
            None,
        ),
        # busy starts before window, ends inside
        (
            [("2026-08-21T07:00:00Z", "2026-08-21T09:00:00Z")],
            60,
            f"{D}08:00:00Z",
            f"{D}11:00:00Z",
            f"{D}09:00:00Z",
        ),
        # start == busy start (window opens exactly when busy begins)
        (
            [("2026-08-21T08:00:00Z", "2026-08-21T09:00:00Z")],
            30,
            f"{D}08:00:00Z",
            f"{D}10:00:00Z",
            f"{D}09:00:00Z",
        ),
        # adjacent busy blocks (no gap between them)
        (
            [
                ("2026-08-21T09:00:00Z", "2026-08-21T10:00:00Z"),
                ("2026-08-21T10:00:00Z", "2026-08-21T11:00:00Z"),
            ],
            30,
            f"{D}08:00:00Z",
            f"{D}12:00:00Z",
            f"{D}11:00:00Z",
        ),
    ],
)
def test_find_free_slot(busy, duration, start, end, expected):
    assert find_free_slot(busy, duration, start, end) == expected
