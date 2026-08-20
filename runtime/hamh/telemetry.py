#!/usr/bin/env python3
"""HAMH trajectory telemetry (ADR H11) — metadata-first, privacy by default.

Every harness run must be reconstructable (order section 14):

    run_id, model, provider, model_revision, harness_id, harness_version,
    harness_fingerprint, task_class, runtime_mode, context_volume, tool_calls,
    tool_failures, retry_count, escalation, token_usage, cache_hit_tokens,
    cache_miss_tokens, latency, verification_result, failure_class,
    final_result

No sensitive reasoning content is persisted. Existing privacy/logging/
security rules take precedence over completeness.
"""

TRAJECTORY_FIELDS = (
    "run_id",
    "model",
    "provider",
    "model_revision",
    "harness_id",
    "harness_version",
    "harness_fingerprint",
    "task_class",
    "runtime_mode",
    "context_volume",
    "tool_calls",
    "tool_failures",
    "retry_count",
    "escalation",
    "token_usage",
    "cache_hit_tokens",
    "cache_miss_tokens",
    "latency",
    "verification_result",
    "failure_class",
    "final_result",
)

# Privacy sentinel: these keys must never appear in a trajectory record.
DENIED_KEYS = (
    "reasoning_content",
    "prompt",
    "prompts",
    "messages",
    "blob",
    "blobs",
    "secret",
    "secrets",
    "full_response",
)


def build_trajectory(run_id, **fields):
    """Build a trajectory record. Raises ValueError if any denied key is
    passed (privacy sentinel — deterministic, testable). The final record
    is passed through sanitize() so nested sensitive content is stripped at
    ANY depth (top-level checks alone are bypassable)."""
    for denied in DENIED_KEYS:
        if denied in fields:
            raise ValueError("trajectory must not contain %r (privacy)" % denied)
    rec = {"run_id": run_id}
    for field in TRAJECTORY_FIELDS:
        if field == "run_id":
            continue
        rec[field] = fields.get(field)
    # always allow metadata extras that are safe (e.g. attempt_id)
    for key, value in fields.items():
        if key not in rec:
            rec[key] = value
    return sanitize(rec)


def sanitize(record):
    """Defensive sanitizer: strips denied keys if present in any dict."""
    if isinstance(record, dict):
        return {k: sanitize(v) for k, v in record.items() if k not in DENIED_KEYS}
    if isinstance(record, list):
        return [sanitize(v) for v in record]
    return record
