#!/usr/bin/env python3
"""HAMH model and task profiles (Layer C and D, ADR H2/H7/H8/H9).

ModelProfile  = versionable, model-dependent configuration (Layer C).
TaskProfile   = task-class-dependent configuration inside a model profile
                (Layer D). All four task classes start with the IDENTICAL
                shared baseline profile; specialization requires
                SPECIALIZATION_VALUE=PROVEN (order section 6).

Tool architecture invariant (order section 10):

    effective_tools  SUBSETEQ  controller_allowed_tools

A task profile may only NARROW the controller allowlist, never extend it.
Tool CAPABILITY and tool PRESENTATION are separated (Devil-in-the-Interface).
"""

import copy

TASK_CLASSES = ("research", "plan", "build", "review")
RUNTIME_MODES = ("thinking", "non-thinking", "auto")

# Controller allowlists (Shared Kernel, Layer A). These mirror the adapter's
# static agent tool policies (PLAN_TOOLS/BUILD_TOOLS in harness_adapter_v2.py)
# and are the UPPER BOUND for every task profile.
READONLY_TOOLS = {
    "read": True,
    "glob": True,
    "grep": True,
    "list": True,
    "bash": False,
    "edit": False,
    "write": False,
    "webfetch": False,
    "task": False,
    "skill": False,
    "question": False,
    "todowrite": False,
}
WRITE_TOOLS = {
    "read": True,
    "edit": True,
    "write": True,
    "list": True,
    "bash": False,
    "glob": True,
    "grep": True,
    "webfetch": False,
    "task": False,
    "skill": False,
    "question": False,
    "todowrite": False,
}
CONTROLLER_ALLOWED_TOOLS = {
    "research": READONLY_TOOLS,
    "plan": READONLY_TOOLS,
    "review": READONLY_TOOLS,
    "build": WRITE_TOOLS,
    "verify": READONLY_TOOLS,
    "baseline": READONLY_TOOLS,
}


def shared_baseline_task_profile():
    """The one shared baseline task profile used by ALL task classes
    initially. Specialization is forbidden without proven value."""
    return {
        "task_class": None,  # filled on use
        "tool_profile": {
            "capabilities": {},  # empty = inherit controller allowlist as-is
            "presentation": "flat",
        },
        "context_profile": {
            "stable_prefix": ["system_instructions", "tool_schemas"],
            "variable": ["task", "retrieved_files", "execution_state"],
            "cache_layout": "stable_first",
        },
        "reasoning_profile": {
            "thinking": "auto",
            "reasoning_effort": None,
        },
        "editing_profile": {"strategy": "direct_edit"},
        "stop_profile": {"stop_on_complete": True},
    }


def baseline_model_profile():
    """Shared-kernel default ModelProfile used as explicit fallback."""
    return {
        "provider": None,  # filled on use
        "model": None,  # filled on use
        "reasoning_strategy": {"thinking": "auto", "reasoning_effort": None},
        "context_preferences": {
            "stable_prefix": ["system_instructions", "tool_schemas"],
            "variable": ["task", "retrieved_files", "execution_state"],
            "cache_layout": "stable_first",
        },
        "tool_interface_preferences": {"presentation": "flat"},
        "editing_strategy": "direct_edit",
        "stop_behavior": {"stop_on_complete": True},
        "failure_fingerprints": [],
        "preferred_interaction": "single_pass",
        "complexity_thresholds": {},
    }


def build_task_profile(task_class, patch=None):
    """Build a task profile for a task class (deep-copied, isolated)."""
    profile = copy.deepcopy(shared_baseline_task_profile())
    profile["task_class"] = task_class
    if patch:
        _apply_patch(profile, patch)
    return profile


def build_model_profile(provider, model, patch=None):
    """Build a model profile (deep-copied, isolated)."""
    profile = copy.deepcopy(baseline_model_profile())
    profile["provider"] = provider
    profile["model"] = model
    if patch:
        _apply_patch(profile, patch)
    return profile


def _apply_patch(profile, patch):
    for key, value in (patch or {}).items():
        if key in profile:
            if isinstance(value, dict) and isinstance(profile[key], dict):
                profile[key] = _deep_merge(profile[key], value)
            else:
                profile[key] = copy.deepcopy(value)


def _deep_merge(base, patch):
    out = copy.deepcopy(base)
    for k, v in (patch or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def effective_tools(task_profile, controller_allowlist=None):
    """Intersect the task profile tool capabilities with the controller
    allowlist. Returns (effective, restricted). A profile may only NARROW.

    capability semantics:
        profile capability True  + allowlist True  -> True
        profile capability True  + allowlist False -> False (restricted)
        profile capability False + allowlist True  -> False (narrowed)
        profile capability unset + allowlist True  -> True  (inherit)
    """
    allowlist = controller_allowlist or {}
    profile_caps = (task_profile.get("tool_profile") or {}).get("capabilities") or {}
    effective = {}
    restricted = False
    for tool, allowed in allowlist.items():
        if tool in profile_caps:
            wants = bool(profile_caps[tool])
            if wants and not allowed:
                restricted = True
                effective[tool] = False
            else:
                effective[tool] = wants and allowed
        else:
            effective[tool] = bool(allowed)
    # profile-named tools that do not exist in the allowlist are DROPPED
    # (a profile can never invent new capabilities)
    unknown = set(profile_caps) - set(allowlist)
    return effective, (restricted or bool(unknown))


def tool_presentation(task_profile):
    return (task_profile.get("tool_profile") or {}).get("presentation", "flat")
