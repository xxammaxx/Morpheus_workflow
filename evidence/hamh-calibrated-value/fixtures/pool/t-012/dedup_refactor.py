"""Formatting helpers with duplicated logic (task fixture t-012)."""


def format_short(value) -> str:
    """Compact one-line summary (max ~20 chars)."""
    if isinstance(value, dict):
        pairs = ", ".join("%s=%s" % (k, v) for k, v in value.items())
        text = pairs
    else:
        text = str(value)
    text = text.replace("\n", " ")
    text = " ".join(text.split())
    if len(text) > 20:
        text = text[:17] + "..."
    return text


def format_long(value) -> str:
    """Multi-line detailed summary (max ~60 chars per value)."""
    if isinstance(value, dict):
        pairs = "\n".join("%s=%s" % (k, v) for k, v in value.items())
        text = pairs
    else:
        text = str(value)
    text = text.replace("\n", " ")
    text = " ".join(text.split())
    if len(text) > 60:
        text = text[:57] + "..."
    return text
