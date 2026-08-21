"""Tests for session (task fixture t-015)."""

import pytest

from session import SessionError, SessionManager


def test_basic_sequence():
    s = SessionManager()
    s.connect()
    assert s.request("a") == 1
    assert s.request("b") == 2
    assert s.close() is True


def test_request_without_connect_raises():
    s = SessionManager()
    with pytest.raises(SessionError):
        s.request("x")


def test_request_after_close_raises():
    s = SessionManager()
    s.connect()
    s.close()
    with pytest.raises(SessionError):
        s.request("x")


def test_double_connect_raises():
    s = SessionManager()
    s.connect()
    with pytest.raises(SessionError):
        s.connect()


def test_close_idempotent():
    s = SessionManager()
    assert s.close() is False
    s.connect()
    assert s.close() is True
    assert s.close() is False


def test_reconnect_resets_counter():
    s = SessionManager()
    s.connect()
    s.request("a")
    s.request("b")
    s.close()
    s.connect()
    assert s.request("c") == 1  # counter must reset per session


def test_requests_do_not_survive_close():
    s = SessionManager()
    s.connect()
    s.request("a")
    s.close()
    s.connect()
    assert s.request("b") == 1
    s.close()


def test_connect_after_error_recovery():
    s = SessionManager()
    with pytest.raises(SessionError):
        s.request("x")
    s.connect()
    assert s.request("y") == 1
    s.close()
