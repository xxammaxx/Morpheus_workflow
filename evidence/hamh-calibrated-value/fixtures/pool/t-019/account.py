"""Account module (task fixture t-019)."""


class Account:
    def __init__(self, balance: float):
        self._balance = balance
        self._ledger = []

    def balance(self) -> float:
        return self._balance

    def deposit(self, amount: float):
        if amount < 0:
            raise ValueError("negative deposit")
        self._balance += amount
        self._ledger.append(("deposit", amount))

    def withdraw(self, amount: float):
        if amount < 0:
            raise ValueError("negative withdraw")
        if amount > self._balance:
            raise ValueError("insufficient funds")
        self._balance -= amount
        self._ledger.append(("withdraw", amount))

    def transfer(self, other, amount: float):
        if amount < 0:
            raise ValueError("negative transfer")
        self._balance -= amount
        self._ledger.append(("transfer", amount))

    def ledger(self) -> list:
        return list(self._ledger)
