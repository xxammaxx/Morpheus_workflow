"""Count words in text (hyphenated words count as one)."""

import re


def word_count(text):
    if text is None:
        return 0
    # BUG: \w+ splits hyphenated words (one-two -> 2)
    return len(re.findall(r"\w+", str(text)))

