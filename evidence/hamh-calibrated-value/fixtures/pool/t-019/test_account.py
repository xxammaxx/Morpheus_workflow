"""Tests for account invariants (task fixture t-019)."""

import pytest

from account import Account


def test_deposit_and_balance():
    a = Account(10)
    a.deposit(5)
    assert a.balance() == 15


def test_withdraw():
    a = Account(10)
    a.withdraw(4)
    assert a.balance() == 6


def test_withdraw_insufficient_raises_and_unchanged():
    a = Account(10)
    with pytest.raises(ValueError):
        a.withdraw(11)
    assert a.balance() == 10


def test_transfer_moves_money():
    a = Account(50)
    b = Account(0)
    a.transfer(b, 20)
    assert a.balance() == 30
    assert b.balance() == 20


def test_transfer_insufficient_raises_both_unchanged():
    a = Account(10)
    b = Account(10)
    with pytest.raises(ValueError):
        a.transfer(b, 20)
    assert a.balance() == 10
    assert b.balance() == 10


def test_invariant_total_constant_across_transfers():
    a = Account(100)
    b = Account(50)
    c = Account(25)
    total_before = a.balance() + b.balance() + c.balance()
    a.transfer(b, 30)
    b.transfer(c, 12)
    c.transfer(a, 5)
    total_after = a.balance() + b.balance() + c.balance()
    assert total_after == total_before


def test_negative_amounts_rejected():
    a = Account(10)
    b = Account(10)
    with pytest.raises(ValueError):
        a.deposit(-1)
    with pytest.raises(ValueError):
        a.withdraw(-1)
    with pytest.raises(ValueError):
        a.transfer(b, -1)


def test_ledger_records_operations():
    a = Account(10)
    b = Account(0)
    a.deposit(5)
    a.withdraw(3)
    a.transfer(b, 4)
    ops = a.ledger()
    assert ops == [("deposit", 5), ("withdraw", 3), ("transfer", 4)]
    assert b.ledger() == [("transfer", 4)]


def test_ledger_transfer_consistency():
    # sum of transfers out of an account equals its net outflow
    a = Account(100)
    b = Account(0)
    c = Account(0)
    a.transfer(b, 10)
    a.transfer(c, 15)
    transfers_out = sum(amt for op, amt in a.ledger() if op == "transfer")
    assert transfers_out == 25
    assert a.balance() == 100 - 25
    assert b.balance() == 10
    assert c.balance() == 15
