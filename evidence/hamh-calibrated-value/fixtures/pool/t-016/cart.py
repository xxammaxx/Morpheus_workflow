"""Cart module (task fixture t-016)."""

from pricing import discount_for


def calculate_total(items) -> float:
    """Total for items [(name, unit_price, quantity)] with per-item discount."""
    total = 0.0
    for name, price, qty in items:
        factor = discount_for(price)
        total += round(price * qty * (1 - factor), 2)
    return round(total, 2)
