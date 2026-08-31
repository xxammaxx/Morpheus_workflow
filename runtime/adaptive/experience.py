"""Controlled, provenance-bound experience bank; never a policy authority."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

TRUST = ("UNTRUSTED_OBSERVATION", "VERIFIED_EPISODE", "DERIVED_LESSON", "REPEATED_PATTERN", "VALIDATED_HEURISTIC")
DENIED = re.compile(r"ignore (?:system|previous) instructions|paid provider|deepseek|sudo |rm -rf|shell command|verifier pass", re.I)


def _safe(item: dict[str, Any]) -> bool:
    return not DENIED.search(json.dumps(item, ensure_ascii=False)) and "secret" not in json.dumps(item).lower()


class ExperienceBank:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def add(self, item: dict[str, Any]) -> dict[str, Any]:
        required = ("experience_id", "source_run_id", "project_id", "task_class", "failure_signature", "strategy_delta", "outcome", "lesson", "evidence_refs", "trust_class")
        if any(not item.get(key) for key in required) or item["trust_class"] not in TRUST:
            return {"ok": False, "code": "SCHEMA_INVALID"}
        if not _safe(item):
            return {"ok": False, "code": "MEMORY_POISONING_REJECTED"}
        current = self._load()
        if any(x.get("experience_id") == item["experience_id"] for x in current):
            return {"ok": False, "code": "DUPLICATE_EXPERIENCE"}
        current.append(dict(item, invalidated=False, created_at=item.get("created_at", dt.datetime.now(dt.timezone.utc).isoformat()), last_validated_at=item.get("last_validated_at", "UNKNOWN"), expires_at=item.get("expires_at", "UNKNOWN")))
        self._save(current)
        return {"ok": True, "experience_id": item["experience_id"]}

    def retrieve(self, *, task_class: str, failure_signature: str | None = None, limit: int = 3) -> list[dict[str, Any]]:
        if limit < 0 or limit > 5:
            raise ValueError("bounded retrieval limit must be 0..5")
        candidates = [x for x in self._load() if not x.get("invalidated") and x.get("trust_class") in TRUST[1:] and x.get("task_class") == task_class]
        if failure_signature:
            candidates.sort(key=lambda x: (x.get("failure_signature") != failure_signature, x.get("experience_id", "")))
        else:
            candidates.sort(key=lambda x: x.get("experience_id", ""))
        return candidates[:limit]

    def invalidate(self, experience_id: str, reason: str) -> bool:
        current = self._load()
        changed = False
        for item in current:
            if item.get("experience_id") == experience_id:
                item["invalidated"] = True; item["invalidation_reason"] = reason; changed = True
        if changed: self._save(current)
        return changed

    def _load(self):
        if not self.path.exists(): return []
        data = json.loads(self.path.read_text())
        return data if isinstance(data, list) else []

    def _save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix="experience-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(data, handle, indent=2, sort_keys=True); handle.flush(); os.fsync(handle.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name): os.unlink(name)


def distill(verified_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Only terminal, verified, non-sensitive observations become episodes."""
    output = []
    for run in verified_runs:
        if run.get("verification_pass") is not True or run.get("terminal") is not True:
            continue
        output.append({"contract": "autodev.experience.v1", "version": "v1", "experience_id": "exp-" + str(run["run_id"]), "source_run_id": run["run_id"], "project_id": run.get("project_id", "UNKNOWN"), "task_class": run.get("task_class", "UNKNOWN"), "failure_signature": run.get("failure_signature", "NONE"), "strategy_delta": run.get("strategy_delta", "NONE"), "outcome": "VERIFIED", "lesson": run.get("lesson", "verified outcome without inferred rule"), "applicability": run.get("applicability", "UNKNOWN"), "counterexamples": run.get("counterexamples", []), "evidence_refs": run.get("evidence_refs", []), "trust_class": "VERIFIED_EPISODE"})
    return output
