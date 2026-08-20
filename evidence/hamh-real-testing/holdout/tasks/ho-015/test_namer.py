from namer import camel_to_snake


def test_camel_to_snake_basic():
    assert camel_to_snake("helloWorld") == "hello_world"

def test_camel_to_snake_acronym():
    assert camel_to_snake("HTTPServer") == "http_server"

def test_camel_to_snake_multi():
    assert camel_to_snake("helloWorld") == "hello_world"
    assert camel_to_snake("already_snake") == "already_snake"

def test_camel_to_snake_unicode():
    assert camel_to_snake("größeWert") == "größe_wert"

def test_camel_to_snake_empty():
    assert camel_to_snake("") == ""
    assert camel_to_snake(None) == ""
    assert camel_to_snake("X") == "x"

