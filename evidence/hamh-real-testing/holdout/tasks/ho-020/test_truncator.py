from truncator import truncate


def test_truncate_basic():
    assert truncate("hello world", 5) == "he..."
    assert truncate("short", 10) == "short"

def test_truncate_exact():
    assert truncate("exactly", 7) == "exactly"
    assert truncate("abcdef", 6) == "abcdef"

def test_truncate_sentence():
    assert truncate("a very long sentence here", 8) == "a ver..."

def test_truncate_small_max():
    assert truncate("hello", 2) == "..."

def test_truncate_empty():
    assert truncate("", 5) == ""
    assert truncate(None, 5) == ""

