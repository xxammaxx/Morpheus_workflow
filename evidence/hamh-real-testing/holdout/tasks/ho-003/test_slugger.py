from slugger import slugify


def test_slugify_basic():
    assert slugify("Hello World") == "hello-world"
    assert slugify("A--B") == "a-b"

def test_slugify_edge():
    assert slugify("Python & JavaScript") == "python-javascript"
    assert slugify("  spaced   out  ") == "spaced-out"

def test_slugify_umlauts():
    assert slugify("München") == "muenchen"
    assert slugify("Straße") == "strasse"

def test_slugify_accented():
    assert slugify("café") == "cafe"
    assert slugify("crème brûlée") == "creme-brulee"
    assert slugify("jalapeño") == "jalapeno"

def test_slugify_empty():
    assert slugify(None) == ""
    assert slugify("") == ""
    assert slugify("---") == ""

