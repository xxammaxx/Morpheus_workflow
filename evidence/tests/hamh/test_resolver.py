#!/usr/bin/env python3
"""HAMH resolver tests (AC-4, AC-5, AC-6, AC-9).

Run: python3 evidence/tests/hamh/test_resolver.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "runtime"))

from hamh import profiles, registry, resolver  # noqa: E402

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


def make_registry(tmpdir):
    path = os.path.join(tmpdir, "hamh-registry.json")
    reg = registry.HarnessRegistry(path=path, authority_token="test-authority")
    return reg, path


def add_active(reg, hid, provider, model, revision, task_class, runtime_mode):
    from contracts.fingerprint import fingerprint as fp

    entry = {
        "contract": "hamh.harness.v1",
        "version": "v1",
        "harness_id": hid,
        "provider": provider,
        "model": model,
        "model_revision": revision,
        "task_class": task_class,
        "runtime_mode": runtime_mode,
        "harness_version": "v1",
        "status": "DRAFT",
        "fingerprint": fp({"hid": hid, "provider": provider}),
        "prompt_profile": {"style": "profile-%s" % task_class},
        "context_profile": {"stable_prefix": ["system"], "variable": ["task"]},
        "tool_profile": {"capabilities": {}, "presentation": "flat"},
        "created_at": "2026-08-20T00:00:00Z",
    }
    r = reg.add(entry)
    assert r["ok"], r
    # DRAFT -> CANDIDATE -> SHADOW -> CANARY -> ACTIVE (authorized path)
    for state in ("CANDIDATE", "SHADOW", "CANARY"):
        r = reg.transition(hid, state)
        assert r["ok"], r
    r = reg.promote(hid, "test-authority")
    assert r["ok"], r


def main():
    import tempfile

    tmp = tempfile.mkdtemp(prefix="hamh-resolver-")

    # --- AC-5: unknown model -> deterministic baseline fallback, no crash
    r1 = resolver.resolve("unknown-prov", "unknown-model", "plan", "auto")
    r2 = resolver.resolve("unknown-prov", "unknown-model", "plan", "auto")
    check("AC5_FALLBACK_NO_CRASH", r1["is_fallback"] is True)
    check("AC5_FALLBACK_ID", r1["resolved_harness_id"].startswith("baseline/shared"))
    check("AC5_FALLBACK_FP", len(r1.get("fingerprint", "")) == 64)

    # --- AC-9: determinism over N repetitions (identical inputs)
    same = all(
        json.dumps(resolver.resolve("p", "m", "build", "thinking"), sort_keys=True)
        == json.dumps(
            r1 if False else resolver.resolve("p", "m", "build", "thinking"),
            sort_keys=True,
        )
        for _ in range(20)
    )
    check("AC9_DETERMINISM_20X", same)
    d1 = resolver.resolve("deepseek", "deepseek-v4-flash", "build", "thinking")
    d2 = resolver.resolve("deepseek", "deepseek-v4-flash", "build", "thinking")
    check("AC9_DETERMINISM_EXACT", d1 == d2)

    # --- AC-4: tool subset (profile cannot enable denied tools)
    reg, _ = make_registry(tmp)
    add_active(
        reg,
        "deepseek/v4-flash/0731/thinking/build/v1",
        "deepseek",
        "deepseek-v4-flash",
        "0731",
        "build",
        "thinking",
    )
    # active build harness with a tool profile trying to enable bash+webfetch
    entry = reg.get("deepseek/v4-flash/0731/thinking/build/v1")
    entry["tool_profile"] = {
        "capabilities": {"bash": True, "webfetch": True, "read": True},
        "presentation": "structured",
    }
    # rebuild entry with new fingerprint through a fresh DRAFT entry
    from contracts.fingerprint import fingerprint as fp

    entry["harness_id"] = "deepseek/v4-flash/0731/thinking/build/v1b"
    entry["status"] = "DRAFT"
    entry["fingerprint"] = fp(entry)
    reg.add(entry)
    for state in ("CANDIDATE", "SHADOW", "CANARY"):
        assert reg.transition(entry["harness_id"], state)["ok"]
    assert reg.promote(entry["harness_id"], "test-authority")["ok"]
    res = resolver.resolve(
        "deepseek",
        "deepseek-v4-flash",
        "build",
        "thinking",
        model_revision="0731",
        registry=reg,
    )
    eff = res["effective_tool_profile"]["capabilities"]
    check("AC4_TOOL_SUBSET_BASH_DENIED", eff.get("bash") is False)
    check("AC4_TOOL_SUBSET_WEBFETCH_DENIED", eff.get("webfetch") is False)
    check(
        "AC4_TOOL_SUBSET_RESTRICTED_FLAG",
        res["effective_tool_profile"].get("restricted_by_controller") is True,
    )
    check("AC4_TOOL_SUBSET_READ_ALLOWED", eff.get("read") is True)

    # unknown capability requested -> missing_capabilities
    res2 = resolver.resolve(
        "deepseek",
        "deepseek-v4-flash",
        "build",
        "thinking",
        model_revision="0731",
        registry=reg,
        requested_capabilities=["bash"],
    )
    check(
        "AC4_MISSING_CAPABILITY_REPORTED",
        "bash" in res2.get("missing_capabilities", []),
    )

    # --- AC-6: RETIRED harness is not resolved (only ACTIVE)
    reg.transition("deepseek/v4-flash/0731/thinking/build/v1b", "RETIRED")
    res3 = resolver.resolve(
        "deepseek",
        "deepseek-v4-flash",
        "build",
        "thinking",
        model_revision="0731",
        registry=reg,
    )
    # the retired one is gone; the older ACTIVE v1 wins (same identity family)
    check(
        "AC6_RETIRED_NOT_RESOLVED",
        res3["resolved_harness_id"] != "deepseek/v4-flash/0731/thinking/build/v1b",
    )
    replay = resolver.resolve_replay(reg, "deepseek/v4-flash/0731/thinking/build/v1b")
    check(
        "AC6_REPLAY_SURFACES_RETIRED",
        replay is not None and replay["status"] == "RETIRED",
    )

    # --- resolver never changes backend (routing authority unchanged)
    check("RESOLVER_NO_BACKEND_FIELD", "backend" not in res3)

    # --- fallback with registry present but no matching entry
    res4 = resolver.resolve(
        "openai",
        "gpt-x",
        "research",
        "non-thinking",
        registry=reg,
    )
    check("FALLBACK_OTHER_PROVIDER", res4["is_fallback"] is True)

    print("\nRESULT %d passed, %d failed" % (PASS, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
