"""Tests for retrywrapper (task fixture t-017)."""

import pytest

from retrywrapper import execute_with_retry


class CustomError(Exception):
    pass


class SubTimeout(TimeoutError):
    pass


def test_success_first_try():
    calls = []
    result = execute_with_retry(lambda: calls.append(1) or "ok", 3, [TimeoutError])
    assert result == "ok"
    assert len(calls) == 1


def test_retry_then_success():
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise TimeoutError("again")
        return "done"

    assert execute_with_retry(fn, 3, [TimeoutError]) == "done"
    assert len(calls) == 3


def test_max_retries_exact_count():
    calls = []

    def fn():
        calls.append(1)
        raise TimeoutError("always")

    with pytest.raises(TimeoutError):
        execute_with_retry(fn, 2, [TimeoutError])
    assert len(calls) == 3  # 1 initial + 2 retries


def test_non_retryable_exception_propagates_immediately():
    calls = []

    def fn():
        calls.append(1)
        raise ValueError("no retry")

    with pytest.raises(ValueError):
        execute_with_retry(fn, 5, [TimeoutError])
    assert len(calls) == 1  # no retry


def test_subclass_counts_as_retryable():
    calls = []

    def fn():
        calls.append(1)
        if len(calls) == 1:
            raise SubTimeout("sub")
        return 7

    assert execute_with_retry(fn, 2, [TimeoutError]) == 7
    assert len(calls) == 2


def test_zero_retries_single_attempt():
    calls = []

    def fn():
        calls.append(1)
        raise TimeoutError("always")

    with pytest.raises(TimeoutError):
        execute_with_retry(fn, 0, [TimeoutError])
    assert len(calls) == 1  # initial attempt only


def test_last_exception_is_raised():
    class FirstError(Exception):
        pass

    class SecondError(Exception):
        pass

    calls = []

    def fn():
        calls.append(1)
        if len(calls) == 1:
            raise FirstError("first")
        raise SecondError("second")

    with pytest.raises(SecondError):
        execute_with_retry(fn, 3, [FirstError, SecondError])
