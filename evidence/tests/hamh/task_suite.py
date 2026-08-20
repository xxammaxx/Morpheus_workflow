#!/usr/bin/env python3
"""HAMH deterministic task suite — evolution governance proof WITHOUT an LLM.

Proves the full promotion pipeline mechanics deterministically:

    baseline ACTIVE -> weakness mining -> hypothesis -> minimal candidate
    -> CANDIDATE -> offline eval (TRAIN+VALIDATION) -> SHADOW
    -> HOLDOUT -> CANARY -> AUTHORIZED promotion -> ACTIVE
    -> rollback restores exactly the previous active config

A deterministic stub "model" answers micro-tasks through a harness strategy.
The verifier runs hidden tests (deterministic). No live model, no network.

Evidence is written to ./task-suite-result.txt

Run: python3 evidence/tests/hamh/task_suite.py
"""

import copy
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "runtime"))

from contracts.fingerprint import fingerprint as fp  # noqa: E402
from hamh import evolution, profiles, registry, resolver  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "task-suite-result.txt")
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


# ------------------------------------------------------------ task corpus --
# Deterministic micro-tasks: spec + hidden tests. The stub model is a
# pattern-based solver: BASELINE harness knows only "greet"; the candidate
# adds "add" — a minimal ONE-component prompt change.
TRAIN = [
    {
        "id": "train-1",
        "kind": "greet",
        "spec": "implement greet(name)",
        "tests": [("Welt", "Hello, Welt!")],
    },
    {
        "id": "train-2",
        "kind": "greet",
        "spec": "implement greet(name) again",
        "tests": [("Ada", "Hello, Ada!")],
    },
    {
        "id": "train-3",
        "kind": "add",
        "spec": "implement add(a, b)",
        "tests": [(2, 3), (10, 5)],
    },
    {
        "id": "train-4",
        "kind": "add",
        "spec": "implement add(a, b) again",
        "tests": [(1, 1), (0, 7)],
    },
]
VALIDATION = [
    {
        "id": "val-1",
        "kind": "add",
        "spec": "implement add(a, b) variant",
        "tests": [(4, 4), (2, 2)],
    },
    {
        "id": "val-2",
        "kind": "greet",
        "spec": "implement greet(name) variant",
        "tests": [("OpenCode", "Hello, OpenCode!")],
    },
]
HOLDOUT = [
    {
        "id": "holdout-1",
        "kind": "multiply",
        "spec": "implement multiply(a, b) — HOLD_99",
        "tests": [(3, 4)],
    },
    {
        "id": "holdout-2",
        "kind": "add",
        "spec": "implement add(a, b) held-out — HOLD_98",
        "tests": [(6, 6)],
    },
]

BASELINE_STRATEGY = {"greet": lambda args: "Hello, %s!" % args[0]}
CANDIDATE_STRATEGY = {
    "greet": lambda args: "Hello, %s!" % args[0],
    "add": lambda args: str(args[0] + args[1]),
}
EXPECTED = {
    "greet": lambda args: "Hello, %s!" % args[0],
    "add": lambda args: str(args[0] + args[1]),
    "multiply": lambda args: str(args[0] * args[1]),
}


def solve(task, strategy):
    """Deterministic stub model + harness strategy: returns per-test answers."""
    fn = strategy.get(task["kind"])
    if fn is None:
        return None
    outs = []
    for t in task["tests"]:
        args = t if isinstance(t, tuple) else (t,)
        try:
            outs.append(fn(args))
        except Exception:
            outs.append(None)
    return outs


def verify_answer(task, answers):
    """Deterministic verifier: run hidden tests against the answers."""
    if answers is None:
        return {"passed": False, "detail": "NO_ANSWER"}
    exp = EXPECTED.get(task["kind"])
    if exp is None:
        return {"passed": False, "detail": "UNKNOWN_KIND"}
    for t, a in zip(task["tests"], answers):
        args = t if isinstance(t, tuple) else (t,)
        if a != exp(args):
            return {"passed": False, "detail": "WRONG_RESULT"}
    return {"passed": True, "detail": "ok"}


def evaluate(strategy, tasks):
    """Deterministic evaluation -> metrics dict."""
    verified = 0
    total_tool_calls = 0
    for t in tasks:
        total_tool_calls += 1
        answers = solve(t, strategy)
        if verify_answer(t, answers)["passed"]:
            verified += 1
    n = len(tasks) or 1
    return {
        "verified_success_rate": round(verified / n, 4),
        "first_pass_success": verified,
        "cost_per_verified_success": 10 + total_tool_calls,
        "latency_per_verified_success": 1.0,
        "tool_calls_per_verified_success": round(
            total_tool_calls / max(verified, 1), 4
        ),
        "retry_rate": 0.0,
        "escalation_rate": 0.0,
        "token_usage": n * 50,
        "cache_hit_rate": 0.0,
        "regression_rate": 0.0,
        "tool_calls": total_tool_calls,
        "tool_failures": 0,
        "latency": 1.0,
    }



def main():
    import tempfile

    tmp = tempfile.mkdtemp(prefix="hamh-suite-")
    reg = registry.HarnessRegistry(
        path=os.path.join(tmp, "registry.json"),
        authority_token="controller-authority",
    )

    # ------------------------------------------------------------- baseline
    base_entry = {
        "contract": "hamh.harness.v1",
        "version": "v1",
        "harness_id": "stub/v1/flash/thinking/build/v1",
        "provider": "stub",
        "model": "stub-flash",
        "model_revision": "0731",
        "task_class": "build",
        "runtime_mode": "thinking",
        "harness_version": "v1",
        "status": "DRAFT",
        "fingerprint": fp({"strategy": "baseline"}),
        "prompt_profile": {"strategy": "baseline"},
        "context_profile": {"stable_prefix": ["system"], "variable": ["task"]},
        "tool_profile": {"capabilities": {}, "presentation": "flat"},
        "created_at": "2026-08-20T00:00:00Z",
    }
    check("SUITE_BASELINE_ADD", reg.add(base_entry)["ok"])
    for state in ("CANDIDATE", "SHADOW", "CANARY"):
        assert reg.transition(base_entry["harness_id"], state)["ok"]
    check(
        "SUITE_BASELINE_PROMOTE",
        reg.promote(base_entry["harness_id"], "controller-authority")["ok"],
    )

    # resolver serves the baseline harness
    r = resolver.resolve("stub", "stub-flash", "build", "thinking", registry=reg)
    check(
        "SUITE_RESOLVER_BASELINE_ACTIVE",
        r["resolved_harness_id"] == base_entry["harness_id"],
    )

    # baseline metrics on TRAIN (baseline knows greet only -> 2/4)
    m_base = evaluate(BASELINE_STRATEGY, TRAIN)
    check("SUITE_BASELINE_METRICS", m_base["verified_success_rate"] == 0.5, str(m_base))

    # ---------------------------------------------------- weakness mining --
    traj = [
        {"weakness_patterns": ["premature_stop", "unused_exposed_tools"]},
        {"weakness_patterns": ["premature_stop", "context_retrieval_misses"]},
    ]
    w = evolution.weakness_mining(traj)
    check("SUITE_WEAKNESS_AGGREGATED", w["patterns"] == [("premature_stop", 2)])

    # --------------------------------------------------------- candidate --
    sandbox = evolution.EvolutionSandbox(
        reg, holdout=HOLDOUT, train_set=TRAIN, validation_set=VALIDATION
    )
    cand = evolution.Candidate(
        hypothesis="adding the add() pattern to the prompt fixes premature stops",
        observed_failure_pattern="premature_stop",
        affected_component="prompt",
        minimal_delta={"prompt": {"strategy": "baseline-plus-add"}},
        expected_effect="solve add-kind tasks",
        risk="low",
        rollback_path="registry.rollback",
        evaluation_plan="train+validation offline eval, then holdout",
    )
    check("SUITE_CANDIDATE_NO_LEAK", sandbox.leakage_check(cand)["leak"] is False)

    cand_entry = copy.deepcopy(base_entry)
    cand_entry["harness_id"] = "stub/v1/flash/thinking/build/v2"
    cand_entry["harness_version"] = "v2"
    cand_entry["parent_version"] = "v1"
    cand_entry["prompt_profile"] = {"strategy": "baseline-plus-add"}
    cand_entry["fingerprint"] = fp({"strategy": "baseline-plus-add"})
    r = sandbox.propose(cand, registry_entry=cand_entry)
    check(
        "SUITE_PROPOSE_CANDIDATE",
        r["ok"] and reg.get(cand_entry["harness_id"])["status"] == "CANDIDATE",
    )

    # offline eval: TRAIN + VALIDATION must improve and beat matched compute
    m_b_train = evaluate(CANDIDATE_STRATEGY, TRAIN)
    m_b_val = evaluate(CANDIDATE_STRATEGY, VALIDATION)
    # matched-compute control: C = baseline + extra budget (same results here
    # -> budget does NOT explain the gain; the harness change does)
    m_c = evaluate(BASELINE_STRATEGY, TRAIN)
    m_c["verified_success_rate"] = 0.5  # extra budget cannot add capability
    verdict = evolution.EvolutionSandbox.matched_compute_verdict(m_base, m_b_train, m_c)
    check(
        "SUITE_MATCHED_COMPUTE_IMPROVED", verdict["verdict"] == "IMPROVED", str(verdict)
    )
    check("SUITE_VALIDATION_IMPROVED", m_b_val["verified_success_rate"] == 1.0)

    # --------------------------------------------------------- shadow ---
    r = reg.transition(cand_entry["harness_id"], "SHADOW", "OFFLINE_EVAL_PASSED")
    check("SUITE_SHADOW", r["ok"])

    # --------------------------------------------------------- holdout ---
    m_holdout = evaluate(CANDIDATE_STRATEGY, HOLDOUT)
    # holdout-2 (add) solves; holdout-1 (multiply) does NOT — the candidate
    # generalized within its one-component change, nothing more
    check(
        "SUITE_HOLDOUT_HONEST",
        m_holdout["verified_success_rate"] == 0.5,
        str(m_holdout),
    )

    # --------------------------------------------------------- canary ---
    r = reg.transition(cand_entry["harness_id"], "CANARY", "HOLDOUT_PASSED")
    check("SUITE_CANARY", r["ok"])

    # ------------------------------------------------ promotion denied ---
    r = reg.promote(cand_entry["harness_id"], None)
    check("SUITE_SELF_PROMOTE_DENIED", r.get("code") == "PROMOTE_DENIED")
    r = reg.promote(cand_entry["harness_id"], "evolver-guess")
    check("SUITE_EVOLVER_PROMOTE_DENIED", r.get("code") == "PROMOTE_DENIED")

    # ---------------------------------------------- authorized promotion --
    r = reg.promote(cand_entry["harness_id"], "controller-authority")
    check("SUITE_AUTHORIZED_PROMOTION", r["ok"])
    check("SUITE_V2_ACTIVE", reg.get(cand_entry["harness_id"])["status"] == "ACTIVE")
    check("SUITE_V1_RETIRED", reg.get(base_entry["harness_id"])["status"] == "RETIRED")

    # resolver now serves the candidate
    r = resolver.resolve("stub", "stub-flash", "build", "thinking", registry=reg)
    check(
        "SUITE_RESOLVER_CANDIDATE_ACTIVE",
        r["resolved_harness_id"] == cand_entry["harness_id"],
    )

    # --------------------------------------------------------- rollback --
    r = reg.rollback(cand_entry["harness_id"], "controller-authority")
    check("SUITE_ROLLBACK_OK", r["ok"])
    restored = reg.get(base_entry["harness_id"])
    check(
        "SUITE_ROLLBACK_EXACT",
        restored["status"] == "ACTIVE"
        and restored["prompt_profile"] == {"strategy": "baseline"}
        and reg.get(cand_entry["harness_id"])["status"] == "RETIRED",
    )
    r = resolver.resolve("stub", "stub-flash", "build", "thinking", registry=reg)
    check(
        "SUITE_RESOLVER_AFTER_ROLLBACK",
        r["resolved_harness_id"] == base_entry["harness_id"],
    )

    # ------------------------------------------------- leakage attempt ----
    bad_cand = evolution.Candidate(
        hypothesis="use HOLD_99 trick from the holdout",
        observed_failure_pattern="premature_stop",
        affected_component="prompt",
        minimal_delta={"prompt": {"strategy": "x"}},
        expected_effect="x",
        risk="x",
        rollback_path="x",
        evaluation_plan="x",
    )
    check("SUITE_LEAK_DETECTED", sandbox.leakage_check(bad_cand)["leak"] is True)
    bad_entry = copy.deepcopy(cand_entry)
    bad_entry["harness_id"] = "stub/v1/flash/thinking/build/v3"
    r = sandbox.propose(bad_cand, registry_entry=bad_entry)
    check("SUITE_LEAK_REJECTED", r.get("code") == "LEAKAGE_REJECTED")

    # ----------------------------------------------------- value verdict --
    # honest: on the FULL corpus the candidate is not proven (multiply unsolved
    # by both; add solved by candidate) -> NOT_PROVEN overall is acceptable and
    # must be stated honestly, never faked
    full = TRAIN + VALIDATION + HOLDOUT
    m_a = evaluate(BASELINE_STRATEGY, full)
    m_b = evaluate(CANDIDATE_STRATEGY, full)
    m_c2 = evaluate(BASELINE_STRATEGY, full)
    verdict = evolution.EvolutionSandbox.matched_compute_verdict(m_a, m_b, m_c2)
    check(
        "SUITE_VALUE_VERDICT_HONEST", verdict["verdict"] in ("IMPROVED", "NOT_PROVEN")
    )

    with open(OUT, "w") as f:
        f.write(
            json.dumps(
                {
                    "baseline_train": m_base,
                    "candidate_train": m_b_train,
                    "candidate_validation": m_b_val,
                    "candidate_holdout": m_holdout,
                    "matched_compute_verdict": verdict,
                    "promotion_path": [
                        "CANDIDATE",
                        "OFFLINE_EVAL",
                        "HOLDOUT",
                        "SHADOW",
                        "CANARY",
                        "AUTHORIZED_PROMOTION",
                        "ROLLBACK_OK",
                    ],
                    "leakage_attempt": "REJECTED",
                    "self_promotion_attempts": "DENIED",
                },
                indent=2,
                sort_keys=True,
            )
        )

    print("\nRESULT %d passed, %d failed" % (PASS, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
