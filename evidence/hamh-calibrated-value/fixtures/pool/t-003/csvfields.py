"""Mini CSV parser (task fixture t-003)."""


def parse_csv_line(line: str) -> list:
    """Split a CSV line into fields.

    - fields separated by commas
    - double-quoted fields may contain commas
    - "" inside a quoted field is an escaped quote
    - whitespace outside quotes is trimmed; inside quotes preserved
    - empty fields are preserved
    """
    fields = []
    current = ""
    in_quotes = False
    for ch in line:
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == "," and not in_quotes:
            fields.append(current.strip())
            current = ""
        else:
            current += ch
    fields.append(current.strip())
    return fields
