"""Tests for paginatestream (task fixture t-010)."""

import pytest

from paginatestream import fetch_all


def make_api(total, page_size):
    """Reference paginated API: returns items[offset:offset+limit]."""
    items = list(range(total))
    calls = []

    def fetch(offset, limit):
        calls.append(offset)
        page = items[offset : offset + limit]
        next_offset = offset + len(page)
        has_more = next_offset < total
        return page, next_offset, has_more

    return fetch, calls


def test_single_page():
    fetch, calls = make_api(3, 10)
    assert fetch_all(fetch, 10) == [0, 1, 2]
    assert calls == [0]


def test_multi_page_exact():
    fetch, calls = make_api(10, 5)
    assert fetch_all(fetch, 5) == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert calls == [0, 5]


def test_multi_page_uneven():
    fetch, calls = make_api(12, 5)
    assert fetch_all(fetch, 5) == list(range(12))
    assert calls == [0, 5, 10]


def test_empty_api():
    fetch, calls = make_api(0, 5)
    assert fetch_all(fetch, 5) == []


def test_empty_page_stops():
    def fetch(offset, limit):
        return [], offset, False  # empty page, no more

    assert fetch_all(fetch, 10) == []


def test_stale_has_more_terminates():
    # API keeps returning has_more=True with empty pages -> must not hang
    calls = {"n": 0}

    def fetch(offset, limit):
        calls["n"] += 1
        return [], offset, True

    assert fetch_all(fetch, 10) == []
    assert calls["n"] == 1000  # safety cap, no infinite loop


def test_no_duplicates_when_next_offset_overlaps():
    # API reports next_offset that overlaps current page
    data = [0, 1, 2, 3, 4, 5]

    def fetch(offset, limit):
        page = data[offset : offset + limit]
        next_offset = offset + max(limit - 1, 1)  # overlapping advance
        has_more = next_offset < len(data)
        return page, next_offset, has_more

    result = fetch_all(fetch, 3)
    assert len(result) == len(set(result))  # no duplicates
    assert result == [0, 1, 2, 3, 4, 5]


def test_order_preserved():
    fetch, _ = make_api(25, 7)
    result = fetch_all(fetch, 7)
    assert result == list(range(25))
