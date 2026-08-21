"""Tests for eventpipeline (task fixture t-014)."""

import pytest

from eventpipeline import process_events


def ev(event_id, seq):
    return {"event_id": event_id, "seq": seq}


def test_empty():
    assert process_events([], lambda e: None) == {"processed": 0, "failed": []}


def test_in_order():
    events = [ev("a", 1), ev("b", 2), ev("c", 3)]
    seen = []
    r = process_events(events, lambda e: seen.append(e["event_id"]))
    assert seen == ["a", "b", "c"]
    assert r == {"processed": 3, "failed": []}


def test_out_of_order_sorted_by_seq():
    events = [ev("c", 3), ev("a", 1), ev("b", 2)]
    seen = []
    process_events(events, lambda e: seen.append(e["event_id"]))
    assert seen == ["a", "b", "c"]


def test_duplicates_processed_once():
    events = [ev("a", 1), ev("a", 1), ev("b", 2), ev("a", 1)]
    seen = []
    r = process_events(events, lambda e: seen.append(e["event_id"]))
    assert seen == ["a", "b"]
    assert r["processed"] == 2


def test_error_isolation():
    def handle(e):
        if e["event_id"] == "b":
            raise RuntimeError("boom")
        return None

    events = [ev("a", 1), ev("b", 2), ev("c", 3)]
    r = process_events(events, handle)
    assert r["processed"] == 2
    assert r["failed"] == ["b"]


def test_failed_event_not_reprocessed_as_duplicate():
    calls = []

    def handle(e):
        calls.append(e["event_id"])
        if e["event_id"] == "x":
            return "some error"

    events = [ev("x", 1), ev("x", 1), ev("y", 2)]
    r = process_events(events, handle)
    assert calls == ["x", "y"]  # x failed once, y still processed
    assert r["failed"] == ["x"]


def test_exception_in_one_does_not_stop_others():
    def handle(e):
        if e["event_id"] == "boom":
            raise ValueError("bad")
        return None

    events = [ev("boom", 2), ev("ok1", 1), ev("ok2", 3)]
    r = process_events(events, handle)
    assert r["processed"] == 2
    assert r["failed"] == ["boom"]


def test_mixed_error_types():
    def handle(e):
        if e["event_id"] == "e1":
            raise RuntimeError("x")
        if e["event_id"] == "e2":
            return "nope"

    events = [ev("e1", 1), ev("e2", 2), ev("ok", 3)]
    r = process_events(events, handle)
    assert r["processed"] == 1
    assert sorted(r["failed"]) == ["e1", "e2"]
