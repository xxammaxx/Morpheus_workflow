"""Tests for scheduler (task fixture t-018)."""

import pytest

from scheduler import next_due


def T(name, due, prio=0, created="2026-08-20T00:00:00Z"):
    return {"name": name, "due_at": due, "priority": prio, "created_at": created}


NOW = "2026-08-21T12:00:00Z"


def test_earliest_due_wins():
    tasks = [
        T("late", "2026-08-21T15:00:00Z"),
        T("soon", "2026-08-21T13:00:00Z"),
        T("later", "2026-08-21T18:00:00Z"),
    ]
    assert next_due(tasks, NOW)["name"] == "soon"


def test_past_due_excluded():
    tasks = [
        T("past1", "2026-08-21T11:59:00Z"),
        T("past2", "2026-08-20T10:00:00Z"),
        T("future", "2026-08-21T13:00:00Z"),
    ]
    assert next_due(tasks, NOW)["name"] == "future"


def test_due_exactly_now_included():
    tasks = [T("exact", "2026-08-21T12:00:00Z"), T("later", "2026-08-21T14:00:00Z")]
    assert next_due(tasks, NOW)["name"] == "exact"


def test_priority_tiebreak_same_due():
    tasks = [
        T("low", "2026-08-21T13:00:00Z", prio=1),
        T("high", "2026-08-21T13:00:00Z", prio=9),
    ]
    assert next_due(tasks, NOW)["name"] == "high"


def test_created_at_tiebreak_same_due_same_priority():
    tasks = [
        T("older", "2026-08-21T13:00:00Z", prio=5, created="2026-08-19T00:00:00Z"),
        T("newer", "2026-08-21T13:00:00Z", prio=5, created="2026-08-20T00:00:00Z"),
    ]
    assert next_due(tasks, NOW)["name"] == "older"


def test_stability_across_three_ties():
    tasks = [
        T("b", "2026-08-21T13:00:00Z", prio=2, created="2026-08-21T00:00:00Z"),
        T("a", "2026-08-21T13:00:00Z", prio=2, created="2026-08-20T00:00:00Z"),
        T("c", "2026-08-21T13:00:00Z", prio=2, created="2026-08-22T00:00:00Z"),
    ]
    assert next_due(tasks, NOW)["name"] == "a"


def test_no_future_task_returns_none():
    tasks = [T("past", "2026-08-21T10:00:00Z"), T("older", "2026-08-20T00:00:00Z")]
    assert next_due(tasks, NOW) is None


def test_empty_list():
    assert next_due([], NOW) is None


def test_higher_priority_does_not_beat_earlier_due():
    tasks = [
        T("urgent_but_later", "2026-08-21T16:00:00Z", prio=99),
        T("calm_but_earlier", "2026-08-21T12:30:00Z", prio=1),
    ]
    assert next_due(tasks, NOW)["name"] == "calm_but_earlier"
