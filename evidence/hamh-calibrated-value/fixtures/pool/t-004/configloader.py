"""Config loader (task fixture t-004)."""


def load_config(text: str) -> dict:
    """Parse an INI-like config text into {section: {option: value}}."""
    config = {}
    section = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("["):
            if stripped.endswith("]"):
                section = stripped[1:-1]
                config.setdefault(section, {})
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            if section is not None:
                config[section][key] = value
    return config
