"""Tests for legacy parser refactor (task fixture t-020)."""

import pytest

import legacy_parser as mod


def test_csv_basic():
    assert mod.parse_csv("a,b\nc,d") == [["a", "b"], ["c", "d"]]


def test_csv_empty_lines_skipped():
    assert mod.parse_csv("a,b\n\n\nc,d\n") == [["a", "b"], ["c", "d"]]


def test_csv_fields_trimmed():
    assert mod.parse_csv(" a , b \n x,y ") == [["a", "b"], ["x", "y"]]


def test_csv_whitespace_collapsed():
    assert mod.parse_csv("a  b,c") == [["a b", "c"]]


def test_tsv_basic():
    assert mod.parse_tsv("a\tb\nc\td") == [["a", "b"], ["c", "d"]]


def test_tsv_empty_fields_become_none():
    assert mod.parse_tsv("a\t\tc") == [["a", None, "c"]]


def test_tsv_trailing_empty_field():
    assert mod.parse_tsv("a\tb\t") == [["a", "b", None]]


def test_tsv_empty_lines_skipped():
    assert mod.parse_tsv("a\tb\n\n") == [["a", "b"]]


def test_shared_helper_exists():
    assert callable(getattr(mod, "_parse_delimited", None))


def test_normalize_line_called_for_each_line(monkeypatch):
    calls = []
    original = mod.normalize_line

    def spy(line):
        calls.append(line)
        return original(line)

    monkeypatch.setattr(mod, "normalize_line", spy)
    mod.parse_csv("a,b\nc,d\n\n")
    mod.parse_tsv("x\ty\n\n")
    assert len(calls) == 4  # 2 csv lines + 2 tsv lines


def test_normalize_line_called_with_raw_line(monkeypatch):
    calls = []
    original = mod.normalize_line

    def spy(line):
        calls.append(line)
        return original(line)

    monkeypatch.setattr(mod, "normalize_line", spy)
    mod.parse_csv("  a,b  ")
    assert calls[0] == "  a,b  "  # raw line, not pre-trimmed


def test_behavior_identical_after_refactor():
    csv_in = " name ,age \n  alice  smith ,30 \n"
    assert mod.parse_csv(csv_in) == [["name", "age"], ["alice smith", "30"]]
    tsv_in = "a\tb\t\nc\t\tz\n"
    assert mod.parse_tsv(tsv_in) == [["a", "b", None], ["c", None, "z"]]
