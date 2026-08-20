from numextract import extract_numbers


def test_extract_numbers_basic():
    assert extract_numbers("a1b22c333") == [1, 22, 333]

def test_extract_numbers_negative():
    assert extract_numbers("temp -5 and 10") == [-5, 10]

def test_extract_numbers_mixed():
    assert extract_numbers("+8 and 9") == [8, 9]
    assert extract_numbers("x7y") == [7]

def test_extract_numbers_versions():
    assert extract_numbers("v1.2.3") == [1, 2, 3]

def test_extract_numbers_empty():
    assert extract_numbers("") == []
    assert extract_numbers(None) == []
    assert extract_numbers("abc") == []

