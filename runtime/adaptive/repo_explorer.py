"""Read-only repository evidence extraction."""

from __future__ import annotations

import hashlib
from pathlib import Path


def explore(root: str | Path, *, patterns: tuple[str, ...] = ("*.py", "*.js", "*.json"), query: str = "") -> dict:
    base = Path(root).resolve()
    items = []
    for pattern in patterns:
        for path in sorted(base.rglob(pattern)):
            if any(part in {".git", "node_modules", "__pycache__"} for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if query and query.lower() not in text.lower():
                continue
            lines = text.splitlines()
            end = min(len(lines), 80)
            rel = path.relative_to(base).as_posix()
            items.append({"path": rel, "start_line": 1, "end_line": end,
                          "reason": "query match" if query else "repository evidence",
                          "sha": hashlib.sha256(text.encode()).hexdigest(), "confidence": 0.5})
    return {"contract": "autodev.repo-evidence.v1", "items": items}
