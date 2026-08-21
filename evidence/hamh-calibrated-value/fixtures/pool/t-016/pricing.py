"""Pricing module (task fixture t-016)."""


def discount_for(quantity: int) -> float:
    """Discount FACTOR for a quantity: 0.0 = none, 0.1 = 10%."""
    if quantity >= 100:
        return 0.15
    if quantity >= 50:
        return 0.10
    if quantity >= 10:
        return 0.05
    return 0.0
