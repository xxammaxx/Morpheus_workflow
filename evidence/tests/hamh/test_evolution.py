#!/usr/bin/env python3
"""HAMH evolution governance tests (AC-3, AC-12, AC-13 + order section 16-21).

Proves: EVOLVER_CAN_PROPOSE/TEST only; candidate can NEVER set itself ACTIVE;
leakage sentinel; matched-compute control; one-component-per-experiment;
weakness mining requires aggregated evidence.

Run: python3 evidence/tests/hamh/test_evolution.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "runtime"))

from contracts.fingerprint import fingerprint as fp  # noqa: E402
from hamh import evolution, registry  # noqa: E402

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


def make_entry(hid, status="DRAFT"):
    return {
        "contract": "hamh.harness.v1",
        "version": "v1",
        "harness_id": hid,
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "model_revision": "0731",
        "task_class": "build",
        "runtime_mode": "thinking",
        "harness_version": "v1",
        "status": status,
        "fingerprint": fp({"hid": hid}),
        "prompt_profile": {"style": "baseline"},
        "context_profile": {"stable_prefix": ["system"]},
        "tool_profile": {"capabilities": {}, "presentation": "flat"},
        "created_at": "2026-08-20T00:00:00Z",
    }


HOLDOUT = [
    {"id": "holdout-task-7", "content": "SECRET_HOLDOUT_7: implement quicksort"},
    {"id": "holdout-task-8", "content": "SECRET_HOLDOUT_8: implement parser"},
]


def main():
    import tempfile

    tmp = tempfile.mkdtemp(prefix="hamh-evol-")
    path = os.path.join(tmp, "registry.json")
    reg = registry.HarnessRegistry(path=path, authority_token="real-authority")
    sandbox = evolution.EvolutionSandbox(
        reg,
        holdout=HOLDOUT,
        train_set=[{"id": "t1", "content": "train task"}],
        validation_set=[{"id": "v1", "content": "val task"}],
    )

    # --- governance constants are hard-coded denials
    check("GOV_PROMOTE_NO", evolution.EVOLVER_CAN_PROMOTE is False)
    check("GOV_GATES_NO", evolution.EVOLVER_CAN_CHANGE_GATES is False)
    check("GOV_HOLDOUT_NO", evolution.EVOLVER_CAN_CHANGE_HOLDOUT is False)
    check("GOV_PROPOSE_YES", evolution.EVOLVER_CAN_PROPOSE is True)
    check("GOV_TEST_YES", evolution.EVOLVER_CAN_TEST is True)

    # --- holdout is locked
    r = sandbox.change_holdout([{"id": "x"}])
    check("HOLDOUT_LOCKED", r.get("code") == "HOLDOUT_LOCKED")

    # --- one-component rule
    cand_multi = evolution.Candidate(
        hypothesis="h",
        observed_failure_pattern="p",
        affected_component="prompt",
        minimal_delta={"prompt": {...}, "tool_architecture": {...}},
        expected_effect="e",
        risk="r",
        rollback_path="p",
        evaluation_plan="p",
    )
    r = sandbox.propose(cand_multi, registry_entry=make_entry("cand/multi/v1"))
    check("ONE_COMPONENT_RULE", r.get("code") == "ONE_COMPONENT_RULE")

    # --- NON_OPTIMIZABLE guard (order section 5): thinking-mode-dead
    # parameters (temperature/top_p/presence_penalty/frequency_penalty) are
    # documented no-ops and must be BLOCKED as evolution dimensions
    for bad_param in (
        "temperature",
        "top_p",
        "presence_penalty",
        "frequency_penalty",
    ):
        cand_bad = evolution.Candidate(
            hypothesis="h",
            observed_failure_pattern="excessive_reasoning",
            affected_component="thinking_policy",
            minimal_delta={"thinking_policy": {bad_param: 0.7}},
            expected_effect="e",
            risk="r",
            rollback_path="p",
            evaluation_plan="p",
        )
        r = sandbox.propose(
            cand_bad, registry_entry=make_entry("cand/nonopt-%s" % bad_param)
        )
        check(
            "EVO_NON_OPTIMIZABLE_%s_BLOCKED" % bad_param.upper(),
            r.get("code") == "NON_OPTIMIZABLE_PARAMETER",
        )

    # --- canonical reasoning_effort guard (order section 4/26):
    # only high|max are HAMH evolution dimensions; low/medium/xhigh blocked
    for bad_effort in ("low", "medium", "xhigh"):
        cand_bad_effort = evolution.Candidate(
            hypothesis="h",
            observed_failure_pattern="excessive_reasoning",
            affected_component="thinking_policy",
            minimal_delta={"thinking_policy": {"reasoning_effort": bad_effort}},
            expected_effect="e",
            risk="r",
            rollback_path="p",
            evaluation_plan="p",
        )
        r = sandbox.propose(
            cand_bad_effort,
            registry_entry=make_entry("cand/effort-%s" % bad_effort),
        )
        check(
            "EVO_EFFORT_%s_BLOCKED" % bad_effort.upper(),
            r.get("code") == "NON_CANONICAL_REASONING_EFFORT",
        )
    for good_effort in ("high", "max"):
        cand_good_effort = evolution.Candidate(
            hypothesis="h",
            observed_failure_pattern="excessive_reasoning",
            affected_component="thinking_policy",
            minimal_delta={"thinking_policy": {"reasoning_effort": good_effort}},
            expected_effect="e",
            risk="r",
            rollback_path="p",
            evaluation_plan="p",
        )
        r = sandbox.propose(
            cand_good_effort,
            registry_entry=make_entry("cand/effort-%s" % good_effort),
        )
        check(
            "EVO_EFFORT_%s_ALLOWED" % good_effort.upper(),
            r["ok"] is True
            and reg.get("cand/effort-%s" % good_effort)["status"] == "CANDIDATE",
        )

    # --- malformed minimal_delta shape is rejected (INVALID_MINIMAL_DELTA)
    cand_scalar = evolution.Candidate(
        hypothesis="h",
        observed_failure_pattern="excessive_reasoning",
        affected_component="thinking_policy",
        minimal_delta={"thinking_policy": "max"},
        expected_effect="e",
        risk="r",
        rollback_path="p",
        evaluation_plan="p",
    )
    r = sandbox.propose(cand_scalar, registry_entry=make_entry("cand/scalar-delta"))
    check(
        "EVO_INVALID_MINIMAL_DELTA_REJECTED",
        r.get("code") == "INVALID_MINIMAL_DELTA",
    )

    # --- leakage sentinel: candidate referencing holdout content -> REJECTED
    cand_leak = evolution.Candidate(
        hypothesis="improve by using SECRET_HOLDOUT_7 ideas",
        observed_failure_pattern="p",
        affected_component="prompt",
        minimal_delta={"prompt": {"style": "v2"}},
        expected_effect="e",
        risk="r",
        rollback_path="p",
        evaluation_plan="p",
    )
    leak = sandbox.leakage_check(cand_leak)
    check("AC12_LEAK_DETECTED", leak["leak"] is True)
    r = sandbox.propose(cand_leak, registry_entry=make_entry("cand/leak/v1"))
    check("AC12_LEAK_REJECTED", r.get("code") == "LEAKAGE_REJECTED")

    # --- clean candidate passes the sentinel and lands as CANDIDATE
    cand_ok = evolution.Candidate(
        hypothesis="stable-first context improves cache hits",
        observed_failure_pattern="context_retrieval_misses",
        affected_component="context_selection",
        minimal_delta={"context_selection": {"cache_layout": "stable_first"}},
        expected_effect="fewer retrieval misses",
        risk="low",
        rollback_path="registry.rollback",
        evaluation_plan="offline eval + holdout",
    )
    leak = sandbox.leakage_check(cand_ok)
    check("AC12_CLEAN_NO_LEAK", leak["leak"] is False)
    r = sandbox.propose(cand_ok, registry_entry=make_entry("cand/ok/v1"))
    check("PROPOSE_OK_CANDIDATE", r["ok"] is True)
    check("PROPOSE_NEVER_ACTIVE", reg.get("cand/ok/v1")["status"] == "CANDIDATE")

    # --- AC-3: candidate cannot promote itself (no authority from sandbox)
    for state in ("SHADOW", "CANARY"):
        assert reg.transition("cand/ok/v1", state)["ok"]
    r = reg.promote("cand/ok/v1", None)
    check("AC3_SELF_PROMOTE_DENIED", r.get("code") == "PROMOTE_DENIED")
    r = reg.promote("cand/ok/v1", "not-the-authority")
    check("AC3_WRONG_TOKEN_DENIED", r.get("code") == "PROMOTE_DENIED")
    # only the real authority can promote
    r = reg.promote("cand/ok/v1", "real-authority")
    check("PROMOTE_BY_AUTHORITY_OK", r["ok"])

    # --- AC-13 matched-compute control
    # B beats A clearly, C does not reach B -> IMPROVED
    v = evolution.EvolutionSandbox.matched_compute_verdict(
        {"verified_success_rate": 0.5},
        {"verified_success_rate": 0.8},
        {"verified_success_rate": 0.6},
    )
    check("AC13_IMPROVED_VERDICT", v["verdict"] == "IMPROVED")
    # B beats A but C explains it -> NOT_PROVEN
    v = evolution.EvolutionSandbox.matched_compute_verdict(
        {"verified_success_rate": 0.5},
        {"verified_success_rate": 0.8},
        {"verified_success_rate": 0.85},
    )
    check("AC13_EXPLAINED_BY_COMPUTE", v["verdict"] == "NOT_PROVEN")
    # B does not beat A -> NOT_PROVEN regardless of C
    v = evolution.EvolutionSandbox.matched_compute_verdict(
        {"verified_success_rate": 0.5},
        {"verified_success_rate": 0.5},
        {"verified_success_rate": 0.4},
    )
    check("AC13_NO_BEAT", v["verdict"] == "NOT_PROVEN")
    # cheaper but worse harness is NOT an improvement (primary metric rule)
    v = evolution.EvolutionSandbox.matched_compute_verdict(
        {"verified_success_rate": 0.7},
        {"verified_success_rate": 0.6},
        {"verified_success_rate": 0.65},
    )
    check("AC13_WORSE_NOT_IMPROVED", v["verdict"] == "NOT_PROVEN")

    # --- weakness mining: single run is NOT sufficient evidence
    single = [{"weakness_patterns": ["excessive_tool_loops"]}]
    w = evolution.weakness_mining(single)
    check("WEAKNESS_SINGLE_RUN_INSUFFICIENT", w["patterns"] == [])
    multi = [
        {"weakness_patterns": ["excessive_tool_loops"]},
        {"weakness_patterns": ["excessive_tool_loops", "premature_stop"]},
        {"weakness_patterns": ["premature_stop"]},
    ]
    w = evolution.weakness_mining(multi)
    check(
        "WEAKNESS_AGGREGATED",
        w["patterns"] == [("excessive_tool_loops", 2), ("premature_stop", 2)],
    )

    print("\nRESULT %d passed, %d failed" % (PASS, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
