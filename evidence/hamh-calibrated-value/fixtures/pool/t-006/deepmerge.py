"""Deep merge helper (task fixture t-006)."""


def merge(base, override):
    """Deep merge override into base; returns a NEW structure.

    - nested dicts merge recursively
    - lists CONCATENATE (project convention)
    - other types are replaced by override
    - base is never mutated
    """
    if isinstance(base, dict) and isinstance(override, dict):
        result = base
        for key, value in override.items():
            if key in result:
                result[key] = merge(result[key], value)
            else:
                result[key] = value
        return result
    if isinstance(base, list) and isinstance(override, list):
        return override + base
    return override
