"""Order summary (task fixture t-011)."""


def _round2(value: float) -> float:
    return round(value, 2)


def _discount(qty: int) -> float:
    if qty >= 50:
        return 0.10
    if qty >= 10:
        return 0.05
    return 0.0


def summarize(items) -> dict:
    """Return {subtotal, tax, total} for the order."""
    subtotal = 0.0
    tax = 0.0
    for name, price, qty in items:
        net = price * qty * (1 - _discount(qty))
        subtotal += _round2(net)
        tax += _round2(price * qty * 0.19)
    subtotal = _round2(subtotal)
    tax = _round2(tax)
    return {"subtotal": subtotal, "tax": tax, "total": _round2(subtotal + tax)}
