"""Extract integers from a string, preserving sign."""

import re


def extract_numbers(text):
    if text is None:
        return []
    # BUG: sign is dropped (negative numbers come back positive)
    return [int(m) for m in re.findall(r"\d+", str(text))]

