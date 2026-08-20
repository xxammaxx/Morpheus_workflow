from capitalizer import title_case


def test_title_case_basic():
    assert title_case("hello world") == "Hello World"

def test_title_case_small_words():
    assert title_case("the lord of the rings") == "The Lord of the Rings"

def test_title_case_more_small():
    assert title_case("Deep Learning") == "Deep Learning"
    assert title_case("Open Source") == "Open Source"

def test_title_case_unicode():
    assert title_case("über alles") == "Über Alles"

def test_title_case_empty():
    assert title_case("") == ""
    assert title_case(None) == ""
    assert title_case("   ") == ""

