#!/usr/bin/env python3
"""HAMH harness resolver (ADR H3) — deterministic, single implementation.

Input:  provider, model, task_class, runtime_mode,
        requested_capabilities, runtime_constraints
Output: hamh.resolution.v1 payload (resolved_harness_id, harness_version,
        fingerprint, effective tool/context/reasoning profiles,
        fallback_profile).

Guarantees:
  - pure function of the inputs (identical inputs -> identical output,
    including fingerprint) — AC-9
  - unknown model / missing profile -> EXPLICIT baseline fallback,
    never a crash, never random selection — AC-5
  - RETIRED/REJECTED/DRAFT/CANDIDATE/SHADOW/CANARY harnesses are never
    resolved for execution; only ACTIVE — AC-6 (replay via resolve_replay)
  - effective_tools SUBSETEQ controller_allowed_tools — AC-4
  - the resolver NEVER changes backend routing (ROUTING_AUTHORITY)
"""

import copy

from contracts.fingerprint import fingerprint as _fp

from . import profiles as _profiles

BASELINE_HARNESS_ID = "baseline/shared/default"


def _norm(value, default=""):
    if value is None:
        return default
    return str(value).strip()


def resolve(
    provider,
    model,
    task_class,
    runtime_mode,
    model_revision=None,
    requested_capabilities=None,
    runtime_constraints=None,
    registry=None,
    controller_allowlist=None,
):
    """Deterministic harness resolution. Returns a hamh.resolution.v1 payload."""
    provider = _norm(provider)
    model = _norm(model)
    task_class = _norm(task_class, "baseline")
    runtime_mode = _norm(runtime_mode, "auto")
    model_revision = _norm(model_revision) or None
    requested_capabilities = list(requested_capabilities or [])
    runtime_constraints = copy.deepcopy(runtime_constraints or {})
    allowlist = controller_allowlist or _profiles.CONTROLLER_ALLOWED_TOOLS.get(
        task_class, _profiles.READONLY_TOOLS
    )

    entry = None
    if registry is not None and provider and model:
        entry = _lookup_active(
            registry, provider, model, model_revision, task_class, runtime_mode
        )

    if entry is None:
        return _baseline_resolution(
            provider,
            model,
            task_class,
            runtime_mode,
            model_revision,
            requested_capabilities,
            runtime_constraints,
            allowlist,
        )

    return _entry_resolution(
        entry, requested_capabilities, runtime_constraints, allowlist
    )


def _lookup_active(registry, provider, model, model_revision, task_class, runtime_mode):
    """Deterministic ACTIVE lookup: exact identity first, then progressively
    more general. Ordering is FIXED (sorted by harness_id/harness_version/
    created_at) — deterministic, never random. Revision ranking is
    intentionally NOT performed ("latest revision" guessing is avoided)."""
    candidates = [
        e
        for e in registry.active_entries()
        if e["provider"] == provider and e["model"] == model
    ]
    if not candidates:
        return None

    def sort_key(e):
        return (
            e["harness_id"],
            e.get("harness_version") or "",
            e.get("created_at") or "",
        )

    def match(e):
        if (
            e.get("model_revision")
            and model_revision
            and (e["model_revision"] != model_revision)
        ):
            return False
        if e["task_class"] != task_class:
            return False
        if e["runtime_mode"] != runtime_mode:
            return False
        return True

    exact = [e for e in candidates if match(e)]
    if exact:
        return sorted(exact, key=sort_key)[0]
    # general match ignoring model_revision (deterministic ordering)
    general = [
        e
        for e in candidates
        if e["task_class"] == task_class and e["runtime_mode"] == runtime_mode
    ]
    if general:
        return sorted(general, key=sort_key)[0]
    # task-class match ignoring runtime_mode
    loosest = [e for e in candidates if e["task_class"] == task_class]
    if loosest:
        return sorted(loosest, key=sort_key)[0]
    return None


def _effective_tools(entry, allowlist):
    task_profile = {
        "tool_profile": entry.get("tool_profile") or {},
        "context_profile": entry.get("context_profile") or {},
        "reasoning_profile": entry.get("prompt_profile") or {},
    }
    effective, restricted = _profiles.effective_tools(task_profile, allowlist)
    return effective, restricted


def _entry_resolution(entry, requested_capabilities, runtime_constraints, allowlist):
    effective_tools, restricted = _effective_tools(entry, allowlist)
    missing = [c for c in requested_capabilities if not effective_tools.get(c)]
    # Naming mapping (order section 8 registry field list): the registry
    # field `prompt_profile` carries the reasoning/prompt strategy cell and
    # is exposed as `effective_reasoning_profile` in the resolution.
    payload = {
        "contract": "hamh.resolution.v1",
        "version": "v1",
        "resolved_harness_id": entry["harness_id"],
        "harness_version": entry.get("harness_version") or "v1",
        "provider": entry["provider"],
        "model": entry["model"],
        "model_revision": entry.get("model_revision") or None,
        "task_class": entry["task_class"],
        "runtime_mode": entry["runtime_mode"],
        "is_fallback": False,
        "effective_tool_profile": {
            "capabilities": effective_tools,
            "presentation": _profiles.tool_presentation(
                {"tool_profile": entry.get("tool_profile") or {}}
            ),
            "restricted_by_controller": restricted,
        },
        "effective_context_profile": entry.get("context_profile")
        or _profiles.shared_baseline_task_profile()["context_profile"],
        "effective_reasoning_profile": entry.get("prompt_profile")
        or _profiles.shared_baseline_task_profile()["reasoning_profile"],
        "fallback_profile": None,
        "requested_capabilities": requested_capabilities,
        "missing_capabilities": missing,
        "runtime_constraints": runtime_constraints,
    }
    payload["fingerprint"] = _fp(payload)
    return payload


def _baseline_resolution(
    provider,
    model,
    task_class,
    runtime_mode,
    model_revision,
    requested_capabilities,
    runtime_constraints,
    allowlist,
):
    """Explicit deterministic fallback to the shared baseline (AC-5)."""
    base_profile = _profiles.shared_baseline_task_profile()
    effective_tools, restricted = _profiles.effective_tools(
        {"tool_profile": base_profile["tool_profile"]}, allowlist
    )
    missing = [c for c in requested_capabilities if not effective_tools.get(c)]
    rid = "%s/%s/%s" % (BASELINE_HARNESS_ID, runtime_mode, task_class)
    payload = {
        "contract": "hamh.resolution.v1",
        "version": "v1",
        "resolved_harness_id": rid,
        "harness_version": "v1",
        "provider": provider or "unknown",
        "model": model or "unknown",
        "model_revision": model_revision,
        "task_class": task_class,
        "runtime_mode": runtime_mode,
        "is_fallback": True,
        "effective_tool_profile": {
            "capabilities": effective_tools,
            "presentation": "flat",
            "restricted_by_controller": restricted,
        },
        "effective_context_profile": base_profile["context_profile"],
        "effective_reasoning_profile": base_profile["reasoning_profile"],
        "fallback_profile": {
            "name": "baseline",
            "harness_id": rid,
            "reason": "no ACTIVE harness for identity (explicit fallback)",
        },
        "requested_capabilities": requested_capabilities,
        "missing_capabilities": missing,
        "runtime_constraints": runtime_constraints,
    }
    payload["fingerprint"] = _fp(payload)
    return payload


def resolve_replay(registry, harness_id):
    """Explicit replay/audit resolution: returns the entry REGARDLESS of
    status. This is the ONLY path that can surface a RETIRED harness."""
    return registry.get(harness_id)
