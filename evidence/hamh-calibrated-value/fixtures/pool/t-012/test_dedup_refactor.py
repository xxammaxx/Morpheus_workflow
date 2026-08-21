"""Tests for dedup_refactor (task fixture t-012)."""

import pytest

import dedup_refactor as mod


def test_normalize_exists_and_is_callable():
    assert callable(mod.normalize)


def test_normalize_basics():
    assert isinstance(mod.normalize({"a": 1, "b": 2}), str)
    assert isinstance(mod.normalize("x"), str)
    assert mod.normalize("  a   b  ") == "a b"


def test_format_short_behavior():
    assert mod.format_short("hello world") == "hello world"
    assert mod.format_short({"k": "v", "x": 1}) == "k=v, x=1"
    assert mod.format_short("x" * 30) == "x" * 17 + "..."


def test_format_long_behavior():
    assert mod.format_long("hello world") == "hello world"
    assert mod.format_long({"k": "v", "x": 1}) == "k=v\nx=1"
    assert mod.format_long("y" * 80) == "y" * 57 + "..."


def test_both_use_normalize(monkeypatch):
    calls = []
    original = mod.normalize

    def spy(value):
        calls.append(value)
        return original(value)

    monkeypatch.setattr(mod, "normalize", spy)
    mod.format_short({"a": 1})
    mod.format_long("some value")
    assert len(calls) == 2


def test_normalize_called_with_raw_value(monkeypatch):
    calls = []
    original = mod.normalize

    def spy(value):
        calls.append(value)
        return original(value)

    monkeypatch.setattr(mod, "normalize", spy)
    raw = {"z": 9, "y": 8}
    mod.format_short(raw)
    assert calls[0] is raw  # raw object, not a pre-formatted string


def test_normalize_handles_dict_and_scalar():
    assert "=" in mod.normalize({"a": 1})
    assert mod.normalize("plain") == "plain"
