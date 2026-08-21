"""Legacy parser (task fixture t-020)."""


def normalize_line(line: str) -> str:
    """Normalize one line: trim + collapse whitespace runs."""
    return " ".join(line.split())


def parse_csv(text: str) -> list:
    """CSV: comma-separated, empty lines skipped, fields trimmed."""
    rows = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = normalize_line(line)
        rows.append([f.strip() for f in line.split(",")])
    return rows


def parse_tsv(text: str) -> list:
    """TSV: tab-separated, empty fields become None."""
    rows = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = normalize_line(line)
        fields = line.split("\t")
        rows.append([f if f != "" else None for f in fields])
    return rows
