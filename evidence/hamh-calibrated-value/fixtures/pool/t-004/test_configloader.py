"""Tests for configloader (task fixture t-004)."""

import pytest

from configloader import load_config

CONFIG = """# server settings
[server]
host = 0.0.0.0
port = 8080

[db]
# connection details
# max_conn = 100
url = postgres://localhost/app
pool_size = 10
timeout = 30

[server]
port = 9090
"""


def test_sections_and_values():
    cfg = load_config(CONFIG)
    assert set(cfg.keys()) == {"server", "db"}
    assert cfg["server"]["host"] == "0.0.0.0"
    assert cfg["db"]["url"] == "postgres://localhost/app"


def test_comments_ignored():
    cfg = load_config(CONFIG)
    assert "connection details" not in str(cfg)
    assert "# server settings" not in str(cfg)
    assert "max_conn" not in str(cfg)
    assert "100" not in str(cfg)


def test_values_trimmed():
    cfg = load_config(CONFIG)
    assert cfg["db"]["pool_size"] == "10"
    assert cfg["server"]["host"] == "0.0.0.0"
    assert cfg["db"]["timeout"] == "30"


def test_duplicate_option_last_wins():
    cfg = load_config(CONFIG)
    assert cfg["server"]["port"] == "9090"


def test_values_may_contain_spaces():
    cfg = load_config("[a]\nname = hello world\n")
    assert cfg["a"]["name"] == "hello world"


def test_options_before_first_section_ignored():
    cfg = load_config("orphan = 1\n[ok]\nx = 1\n")
    assert "orphan" not in cfg
    assert cfg["ok"]["x"] == "1"


def test_option_without_equals_ignored():
    cfg = load_config("[a]\njusttext\nx = 1\n")
    assert "justtext" not in cfg["a"]
    assert cfg["a"]["x"] == "1"


def test_malformed_section_header_ignored():
    cfg = load_config("[broken\nx = 1\n[ok]\ny = 2\n")
    assert "broken" not in cfg
    assert cfg["ok"]["y"] == "2"
