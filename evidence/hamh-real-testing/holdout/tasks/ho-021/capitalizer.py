"""Capitalize words, keeping small words lowercase."""


SMALL = {"and", "of", "the", "a", "an"}


def title_case(text):
    if text is None:
        return ""
    if not str(text).strip():
        return ""
    # BUG: small words are capitalized too
    return " ".join(w.capitalize() for w in str(text).split())

