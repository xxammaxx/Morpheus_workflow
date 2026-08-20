"""Convert text to a lowercase URL slug with accent transliteration."""

import re


def slugify(text):
    if text is None:
        return ""
    mapping = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
    # BUG: accented Latin characters (é, è, à, ç, ñ, ô, û) are
    # dropped instead of transliterated
    lowered = str(text).lower()
    for s, d in mapping.items():
        lowered = lowered.replace(s, d)
    out = re.sub(r"[^a-z0-9-]+", "-", lowered)
    return re.sub(r"-{2,}", "-", out).strip("-")

