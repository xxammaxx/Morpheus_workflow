"""Reproducible benchmark records and hard-gated comparisons."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

UNKNOWN = "UNKNOWN"
HARD_GATES = ("security_gate_pass", "holdout_isolation_pass")
METRICS = (
    "task_success", "verification_pass", "acceptance_criteria_pass",
    "security_gate_pass", "correctness_review", "quality_review",
    "tool_call_success", "structured_output_success", "invalid_output_rate",
    "retry_count", "transport_failures", "semantic_failures",
    "context_tokens_in", "context_tokens_out", "tool_calls", "wall_clock_ms",
    "provider", "model", "actual_model", "cost", "zero_cost_proven",
    "failure_signature", "strategy_delta",
)


def canonical_hash(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()


def _bool(value: Any) -> bool:
    return value is True


@dataclass(frozen=True)
class TaskSet:
    split: str
    task_ids: tuple[str, ...]
    task_set_hash: str

    @classmethod
    def from_tasks(cls, split: str, tasks: Iterable[dict[str, Any]]) -> "TaskSet":
        if split not in {"development", "validation", "holdout"}:
            raise ValueError("invalid benchmark split")
        normalized = []
        for task in tasks:
            if not task.get("task_id") or task.get("split") != split:
                raise ValueError("task_id and matching split are required")
            normalized.append(copy.deepcopy(task))
        normalized.sort(key=lambda item: item["task_id"])
        return cls(split, tuple(item["task_id"] for item in normalized), canonical_hash(normalized))


def load_task_set(directory: str | Path, split: str) -> TaskSet:
    root = Path(directory)
    tasks = [json.loads(path.read_text()) for path in sorted(root.glob("*.json"))]
    return TaskSet.from_tasks(split, tasks)


def assert_holdout_isolated(optimizer_task_ids: Iterable[str], holdout_task_ids: Iterable[str]) -> None:
    overlap = set(optimizer_task_ids) & set(holdout_task_ids)
    if overlap:
        raise ValueError("HOLDOUT_LEAKAGE: " + ",".join(sorted(overlap)))


def freeze_baseline(*, baseline_id: str, code_head: str, harness_version: str,
                    context_policy: str, router_policy: str, model_pool: list[str],
                    task_set_hash: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "contract": "autodev.benchmark-baseline.v1", "version": "v1",
        "baseline_id": baseline_id, "baseline_head": code_head,
        "harness_version": harness_version, "context_policy": context_policy,
        "router_policy": router_policy, "model_pool": sorted(model_pool),
        "task_set_hash": task_set_hash, "result_hash": canonical_hash(results),
    }


def normalize_result(raw: dict[str, Any]) -> dict[str, Any]:
    """Preserve measured values; missing values are explicitly UNKNOWN."""
    result = {key: raw.get(key, UNKNOWN) for key in METRICS}
    result.update({key: raw[key] for key in raw if key not in result})
    return result


def summarize(results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    values = [normalize_result(r) for r in results]
    def rate(field: str):
        known = [r[field] for r in values if isinstance(r[field], bool)]
        return (sum(known) / len(known)) if known else UNKNOWN
    return {
        "runs": len(values),
        "task_success_rate": rate("task_success"),
        "verification_pass_rate": rate("verification_pass"),
        "security_gate_pass_rate": rate("security_gate_pass"),
        "structured_output_success_rate": rate("structured_output_success"),
        "avg_context_tokens_in": _average(values, "context_tokens_in"),
        "avg_latency_ms": _average(values, "wall_clock_ms"),
        "avg_tool_calls": _average(values, "tool_calls"),
        "avg_cost": _average(values, "cost"),
    }


def _average(values: list[dict[str, Any]], field: str):
    known = [r[field] for r in values if isinstance(r[field], (int, float)) and not isinstance(r[field], bool)]
    return sum(known) / len(known) if known else UNKNOWN


def compare(baseline: dict[str, Any], candidate: dict[str, Any], *, holdout: bool = False) -> dict[str, Any]:
    """Compare independently measured summaries; hard failures always reject."""
    hard_failures = []
    if candidate.get("security_gate_pass") is False:
        hard_failures.append("SECURITY_REGRESSION")
    if candidate.get("holdout_isolation_pass") is False:
        hard_failures.append("HOLDOUT_ISOLATION_FAILED")
    primary_a = baseline.get("task_success_rate", UNKNOWN)
    primary_b = candidate.get("task_success_rate", UNKNOWN)
    improvement = isinstance(primary_a, (int, float)) and isinstance(primary_b, (int, float)) and primary_b > primary_a
    return {
        "contract": "autodev.benchmark-comparison.v1", "version": "v1",
        "baseline": copy.deepcopy(baseline), "candidate": copy.deepcopy(candidate),
        "holdout": holdout, "hard_failures": hard_failures,
        "improvement_proven": bool(improvement and not hard_failures),
        "classification": "PROMOTE_RECOMMENDATION" if improvement and not hard_failures else "IMPROVEMENT_NOT_PROVEN",
    }
