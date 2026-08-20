"""Convert camelCase to snake_case (acronyms handled)."""

import re


def camel_to_snake(text):
    if text is None:
        return ""
    # BUG: consecutive capitals (acronyms) get an extra
    # underscore between each letter
    out = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", str(text))
    return out.lower()

