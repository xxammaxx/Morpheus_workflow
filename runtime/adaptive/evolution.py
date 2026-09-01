"""Candidate hypotheses and promotion recommendations, never promotion."""

from __future__ import annotations

from .benchmark import compare

ALLOWED_COMPONENTS = frozenset({"prompt", "context_policy", "tool_policy", "routing_weight", "retry_policy", "formatter", "verifier"})


def candidate(*, candidate_id: str, baseline_head: str, component: str, delta: dict, hypothesis: str, task_set_hash: str, holdout_hash: str) -> dict:
    if component not in ALLOWED_COMPONENTS or not delta or not hypothesis:
        raise ValueError("one non-empty allowed component and hypothesis required")
    return {"contract": "autodev.harness-candidate.v1", "version": "v1", "candidate_id": candidate_id, "baseline_head": baseline_head, "changed_component": component, "delta": dict(delta), "hypothesis": hypothesis, "task_set_hash": task_set_hash, "holdout_hash": holdout_hash, "promotion_state": "EVALUATION_PENDING"}


def evaluate(candidate_record: dict, *, development: dict, validation: dict, security_pass: bool, regression_pass: bool, holdout: dict | None = None) -> dict:
    holdout = holdout or {"task_success_rate": "UNKNOWN"}
    comparison = compare(development, validation)
    holdout_pass = holdout.get("task_success_rate") != "UNKNOWN" and holdout.get("security_gate_pass") is not False
    gates = {"development": comparison["improvement_proven"], "validation": validation.get("security_gate_pass") is not False, "security": security_pass, "regression": regression_pass, "holdout": holdout_pass}
    passed = all(gates.values())
    return {"contract": "autodev.harness-comparison.v1", "version": "v1", "candidate_id": candidate_record["candidate_id"], "gates": gates, "holdout": holdout, "recommendation": "PROMOTE_RECOMMENDATION" if passed else "REJECT", "comparison": comparison}
