from counter import word_count


def test_word_count_basic():
    assert word_count("hello world") == 2
    assert word_count("  a   b  ") == 2

def test_word_count_punctuation():
    assert word_count("Hello, world!") == 2
    assert word_count("a b c") == 3

def test_word_count_hyphen():
    assert word_count("one-two") == 1

def test_word_count_unicode():
    assert word_count("grüße welt") == 2
    assert word_count("über") == 1

def test_word_count_empty():
    assert word_count("") == 0
    assert word_count(None) == 0

