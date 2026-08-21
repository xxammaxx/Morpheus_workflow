"""Tests for deepmerge (task fixture t-006)."""

import pytest

from deepmerge import merge


def test_flat_override():
    assert merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}
    assert merge({"a": 1}, {"a": 2}) == {"a": 2}


def test_nested_dicts_merge_recursively():
    base = {"db": {"host": "x", "port": 1}}
    ov = {"db": {"port": 2, "user": "u"}}
    assert merge(base, ov) == {"db": {"host": "x", "port": 2, "user": "u"}}


def test_deeply_nested():
    base = {"a": {"b": {"c": {"d": 1, "e": 2}}}}
    ov = {"a": {"b": {"c": {"d": 9}}}}
    assert merge(base, ov) == {"a": {"b": {"c": {"d": 9, "e": 2}}}}


def test_lists_concatenate():
    base = {"tags": ["a", "b"]}
    ov = {"tags": ["c"]}
    assert merge(base, ov) == {"tags": ["a", "b", "c"]}


def test_scalars_replaced():
    assert merge({"x": "old", "n": 1, "f": True, "z": None}, {"x": "new"}) == {
        "x": "new",
        "n": 1,
        "f": True,
        "z": None,
    }


def test_base_not_mutated():
    base = {"a": {"b": [1, 2], "c": 3}}
    import copy

    snapshot = copy.deepcopy(base)
    merge(base, {"a": {"b": [3], "c": 4}})
    assert base == snapshot


def test_list_elements_not_aliased():
    base = {"l": [{"x": 1}]}
    ov = {"l": [{"y": 2}]}
    out = merge(base, ov)
    out["l"][0]["x"] = 99
    assert base["l"][0]["x"] == 1


def test_mixed_types():
    base = {"a": {"b": [1], "c": {"d": 1}}}
    ov = {"a": {"b": [2], "c": "scalar"}}
    assert merge(base, ov) == {"a": {"b": [1, 2], "c": "scalar"}}
