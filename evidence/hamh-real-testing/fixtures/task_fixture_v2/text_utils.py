"""Text utilities with an intentionally introduced bug (task fixture v2)."""

import re


def word_count(text):
    if not text:
        return 0
    return len(text.split())


def slugify(text):
    """Convert text to a URL-safe slug.

    Rules:
      - lowercase
      - replace spaces with hyphens
      - remove characters that are not a-z, 0-9, or hyphen
      - umlauts and accented characters MUST be transliterated:
        ä->ae, ö->oe, ü->ue, ß->ss, é->e, è->e, à->a, ç->c, ñ->n
    """
    if text is None:
        return ""
    mapping = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
    # BUG (intentional): the accented-characters mapping below is MISSING
    # (é, è, à, ç, ñ are dropped instead of transliterated). Only the
    # German umlauts are handled. Tests expect full transliteration.
    lowered = str(text).lower()
    for src, dst in mapping.items():
        lowered = lowered.replace(src, dst)
    slug = re.sub(r"[^a-z0-9\-]+", "-", lowered)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug


def extract_numbers(text):
    if not text:
        return []
    return [int(m) for m in re.findall(r"\d+", text)]
