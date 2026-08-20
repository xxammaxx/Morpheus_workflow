"""Test suite for text_utils.py — one test is failing by design (fixture v2)."""

import pytest

from text_utils import extract_numbers, slugify, word_count


def test_word_count():
    assert word_count("hello world") == 2
    assert word_count("") == 0
    assert word_count("  a   b  c  ") == 3


def test_slugify_basic():
    assert slugify("Hello World") == "hello-world"
    assert slugify("  spaced   out  ") == "spaced-out"
    assert slugify("Python & JavaScript") == "python-javascript"
    assert slugify(None) == ""


def test_slugify_umlauts():
    assert slugify("München") == "muenchen"
    assert slugify("Straße") == "strasse"
    assert slugify("Größe überall") == "groesse-ueberall"


def test_slugify_accented():
    assert slugify("café") == "cafe"
    assert slugify("crème brûlée") == "creme-brulee"
    assert slugify("jalapeño") == "jalapeno"
    assert slugify("français") == "francais"


def test_slugify_edge_cases():
    assert slugify("A--B") == "a-b"
    assert slugify("---") == ""
    assert slugify("123 abc") == "123-abc"


def test_extract_numbers():
    assert extract_numbers("a1b22c333") == [1, 22, 333]
    assert extract_numbers("no digits") == []
    assert extract_numbers("") == []
