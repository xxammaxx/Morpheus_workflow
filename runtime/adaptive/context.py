"""Bounded, provenance-first context compilation."""

from __future__ import annotations

import hashlib
from typing import Any


def _tokens(text: str) -> int:
    return max(1, (len(text.encode("utf-8")) + 3) // 4) if text else 0


def _bounded(text: str, budget: int) -> str:
    if _tokens(text) <= budget:
        return text
    return text[: max(0, budget * 4 - 3)] + "..."


def compile_context(*, control_core: str, task_state: str, repository: list[dict[str, Any]],
                    recent_history: list[str], experiences: list[dict[str, Any]],
                    budgets: dict[str, int]) -> dict[str, Any]:
    """Compile deterministic blocks in priority order; no LLM summarization."""
    if _tokens(control_core) > int(budgets.get("CONTROL_CORE", 0)):
        raise ValueError("CONTROL_CORE exceeds its budget")
    if _tokens(control_core) + _tokens(task_state) > int(budgets.get("TOTAL_CONTEXT", 0)):
        raise ValueError("TOTAL_CONTEXT cannot fit mandatory control and task state")
    blocks = []
    sources = [
        ("CONTROL_CORE", control_core, "SYSTEM_CONTROL", "immutable"),
        ("CURRENT_TASK_STATE", task_state, "TASK_STATE", "current"),
        ("REPOSITORY_EVIDENCE", "\n".join(_evidence_line(x) for x in repository), "REPOSITORY", "untrusted_reference"),
        ("RECENT_EXECUTION", "\n".join(recent_history), "RUN_TELEMETRY", "observed"),
        ("EXPERIENCE_RETRIEVAL", "\n".join(_experience_line(x) for x in experiences), "EXPERIENCE_BANK", "derived"),
    ]
    for name, content, source, trust in sources:
        value = _bounded(str(content), int(budgets.get(name, budgets.get("TOTAL_CONTEXT", 0))))
        blocks.append({"name": name, "content": value, "provenance": {
            "source": source, "trust_class": trust, "created_at": "UNKNOWN",
            "source_run": "UNKNOWN", "source_hash": hashlib.sha256(str(content).encode()).hexdigest(),
            "retrieval_reason": "deterministic policy selection", "token_count": _tokens(value),
        }})
    total = sum(item["provenance"]["token_count"] for item in blocks)
    total_max = int(budgets.get("TOTAL_CONTEXT", total))
    if total > total_max:
        # Preserve the control core and task state; trim only lower-priority blocks.
        remaining = max(0, total_max - sum(x["provenance"]["token_count"] for x in blocks[:2]))
        for item in blocks[2:]:
            item["content"] = _bounded(item["content"], remaining)
            item["provenance"]["token_count"] = _tokens(item["content"]) if item["content"] else 0
            remaining = max(0, remaining - item["provenance"]["token_count"])
    return {"contract": "autodev.context-pack.v1", "version": "v1", "blocks": blocks,
            "total_tokens": sum(x["provenance"]["token_count"] for x in blocks), "budgets": dict(budgets)}


def _evidence_line(item: dict[str, Any]) -> str:
    required = ("path", "start_line", "end_line", "reason", "sha")
    if any(key not in item for key in required):
        raise ValueError("repository evidence requires path, lines, reason and sha")
    return "{path}:{start_line}-{end_line} [{reason}] sha={sha}".format(**item)


def _experience_line(item: dict[str, Any]) -> str:
    if item.get("trust_class") not in {"VERIFIED_EPISODE", "DERIVED_LESSON", "REPEATED_PATTERN", "VALIDATED_HEURISTIC"}:
        return ""
    return "lesson={}; failure={}; evidence={}".format(item.get("lesson", ""), item.get("failure_signature", ""), item.get("evidence_refs", []))
