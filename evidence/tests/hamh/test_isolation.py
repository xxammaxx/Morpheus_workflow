#!/usr/bin/env python3
"""HAMH isolation tests (AC-1, AC-2, AC-7).

Test A: DeepSeek build profile cannot mutate DeepSeek research profile.
Test B: DeepSeek profiles cannot mutate other models' profiles.
Test G: every semantically relevant harness change changes the fingerprint.

Run: python3 evidence/tests/hamh/test_isolation.py
"""

import copy
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "runtime"))

from contracts.fingerprint import fingerprint as fp  # noqa: E402
from hamh import profiles  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("PASS %s" % name)
    else:
        FAIL += 1
        print("FAIL %s %s" % (name, detail))


def harness_entry(hid, provider, model, task_class, patch=None):
    p = profiles.build_task_profile(task_class, patch=patch)
    e = {
        "contract": "hamh.harness.v1",
        "version": "v1",
        "harness_id": hid,
        "provider": provider,
        "model": model,
        "model_revision": "0731",
        "task_class": task_class,
        "runtime_mode": "auto",
        "harness_version": "v1",
        "status": "CANDIDATE",
        "prompt_profile": p["reasoning_profile"],
        "context_profile": p["context_profile"],
        "tool_profile": p["tool_profile"],
        "editing_profile": p["editing_profile"],
        "stop_profile": p["stop_profile"],
        "created_at": "2026-08-20T00:00:00Z",
    }
    e["fingerprint"] = entry_fp(e)
    return e


def entry_fp(e):
    """Registry fingerprint semantics (ADR H5): SHA-256 over the semantic
    PROFILE fields (x-metadata excluded; identity bookkeeping excluded)."""
    return fp(
        {
            k: e[k]
            for k in (
                "prompt_profile",
                "context_profile",
                "tool_profile",
                "editing_profile",
                "stop_profile",
            )
        }
    )


def main():
    # --- AC-1: deepseek build profile cannot mutate deepseek research profile
    p_build = profiles.build_task_profile("build")
    p_research = profiles.build_task_profile("research")
    p_build["tool_profile"]["capabilities"] = {"edit": True, "write": True}
    p_build["context_profile"]["variable"].append("build_only_context")
    check(
        "AC1_RESEARCH_UNTOUCHED_TOOLS", p_research["tool_profile"]["capabilities"] == {}
    )
    check(
        "AC1_RESEARCH_UNTOUCHED_CONTEXT",
        "build_only_context" not in p_research["context_profile"]["variable"],
    )

    # deepcopy independence in both directions
    a = profiles.build_task_profile("build")
    b = copy.deepcopy(a)
    b["editing_profile"]["strategy"] = "rewrite_whole_file"
    check("AC1_DEEPCOPY_INDEPENDENT", a["editing_profile"]["strategy"] == "direct_edit")

    # --- AC-2: deepseek profiles cannot mutate other models' profiles
    ds = profiles.build_model_profile("deepseek", "deepseek-v4-flash")
    other = profiles.build_model_profile("lmstudio", "huihui-qwen3.5-9b-abliterated")
    ds["editing_strategy"] = "structured_edits"
    ds["context_preferences"]["cache_layout"] = "deepseek_prefix_blocks"
    check("AC2_OTHER_MODEL_UNTOUCHED_EDIT", other["editing_strategy"] == "direct_edit")
    check(
        "AC2_OTHER_MODEL_UNTOUCHED_CACHE",
        other["context_preferences"]["cache_layout"] == "stable_first",
    )

    # --- AC-7: every semantically relevant change changes the fingerprint
    e1 = harness_entry("ds/build/v1", "deepseek", "deepseek-v4-flash", "build")
    fp1 = e1["fingerprint"]

    e_prompt = copy.deepcopy(e1)
    e_prompt["prompt_profile"] = {"thinking": "disabled"}
    e_prompt["fingerprint"] = entry_fp(e_prompt)
    check("AC7_PROMPT_CHANGE", e_prompt["fingerprint"] != fp1)

    e_tool = copy.deepcopy(e1)
    e_tool["tool_profile"] = {"capabilities": {"read": True}, "presentation": "flat"}
    e_tool["fingerprint"] = entry_fp(e_tool)
    check("AC7_TOOL_CHANGE", e_tool["fingerprint"] != fp1)

    e_context = copy.deepcopy(e1)
    e_context["context_profile"] = {"stable_prefix": ["a"], "variable": ["b"]}
    e_context["fingerprint"] = entry_fp(e_context)
    check("AC7_CONTEXT_CHANGE", e_context["fingerprint"] != fp1)

    e_edit = copy.deepcopy(e1)
    e_edit["editing_profile"] = {"strategy": "rewrite_whole_file"}
    e_edit["fingerprint"] = entry_fp(e_edit)
    check("AC7_EDITING_CHANGE", e_edit["fingerprint"] != fp1)

    e_stop = copy.deepcopy(e1)
    e_stop["stop_profile"] = {"stop_on_complete": False}
    e_stop["fingerprint"] = entry_fp(e_stop)
    check("AC7_STOP_CHANGE", e_stop["fingerprint"] != fp1)

    # metadata change does NOT change the fingerprint
    e_meta = copy.deepcopy(e1)
    e_meta["created_at"] = "2026-08-21T00:00:00Z"
    e_meta["x-metadata"] = {"owner": "someone"}
    check("AC7_METADATA_INSENSITIVE", entry_fp(e_meta) == fp1)

    # identical semantic content -> identical fingerprint (stability)
    e_same = harness_entry("ds/build/v1", "deepseek", "deepseek-v4-flash", "build")
    check("AC7_STABLE_FP", e_same["fingerprint"] == fp1)

    # --- AC-2 (registry level): mutating a deepseek registry entry copy can
    # never affect an ACTIVE harness of ANOTHER model
    import tempfile

    from hamh import registry

    tmp = tempfile.mkdtemp(prefix="hamh-iso-")
    reg = registry.HarnessRegistry(
        path=os.path.join(tmp, "r.json"), authority_token="auth"
    )
    r = reg.add(harness_entry("ds/build/v1", "deepseek", "deepseek-v4-flash", "build"))
    assert r["ok"], r
    r = reg.add(
        harness_entry(
            "lm/build/v1", "lmstudio", "huihui-qwen3.5-9b-abliterated", "build"
        )
    )
    assert r["ok"], r
    # mutate the returned COPY of the deepseek entry aggressively
    got = reg.get("ds/build/v1")
    got["prompt_profile"] = {"thinking": "destroyed"}
    got["context_profile"] = {"stable_prefix": ["nothing"]}
    other = reg.get("lm/build/v1")
    check(
        "AC2_REGISTRY_OTHER_MODEL_UNTOUCHED_PROMPT",
        other["prompt_profile"]
        == harness_entry(
            "lm/build/v1", "lmstudio", "huihui-qwen3.5-9b-abliterated", "build"
        )["prompt_profile"],
    )
    check(
        "AC2_REGISTRY_DEEPSEEK_UNMUTATED",
        reg.get("ds/build/v1")["prompt_profile"]
        == {"thinking": "auto", "reasoning_effort": None},
    )

    print("\nRESULT %d passed, %d failed" % (PASS, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
