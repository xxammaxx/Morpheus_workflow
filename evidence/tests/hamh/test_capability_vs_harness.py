#!/usr/bin/env python3
"""HAMH capability-vs-harness proof (AC-11, order section 27).

Controlled flow that prevents a backbone-capability problem from being
treated as an endless harness problem:

    failure
      -> retry with justified delta
      -> same fundamental failure
      -> failure taxonomy
      -> CAPABILITY_FAILURE candidate
      -> routing/escalation  (NO infinite evolution loop)

Run: python3 evidence/tests/hamh/test_capability_vs_harness.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "runtime"))

from hamh import taxonomy  # noqa: E402

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


def run_cycle(max_cycles=5):
    """Simulated evolution-vs-capability decision loop.

    Returns the decision ladder: list of actions taken. The loop MUST
    terminate in CAPABILITY_FAILURE -> ESCALATE, never cycle forever.
    """
    failure_signature = "sig-fundamental-math-error"
    attempts = 0
    actions = []
    for cycle in range(max_cycles):
        # deterministic verifier result: same fundamental failure each time
        # even though a justified strategy delta was applied
        attempts += 1
        klass, reason, escalate = taxonomy.classify(
            "TEST_FAILURE",
            {
                "failure_signature": failure_signature,
                "attempt_count": attempts,
                "same_fundamental_failure": True,
                "strategy_delta": True,
                "new_evidence": ["same error output"],
            },
        )
        actions.append((klass, reason, escalate))
        if taxonomy.capability_bound(klass):
            actions.append(("ROUTE_ESCALATE", "RETRY_DENIED_ATTEMPT_LIMIT", True))
            break
    return actions


def main():
    # --- base mapping table (extension of the adapter classes)
    check("MAP_TEST", taxonomy.BASE_MAP["TEST_FAILURE"] == "STRATEGY_FAILURE")
    check("MAP_INFRA", taxonomy.BASE_MAP["INFRA_FAILURE"] == "EXECUTION_FAILURE")
    check("MAP_CONTEXT", taxonomy.BASE_MAP["CONTEXT_FAILURE"] == "HARNESS_FAILURE")
    check("MAP_PROVIDER", taxonomy.BASE_MAP["PROVIDER_FAILURE"] == "EXECUTION_FAILURE")

    # infra/provider failures are NEVER classified as model incapability
    k, reason, esc = taxonomy.classify("INFRA_FAILURE", {})
    check("EXECUTION_NOT_CAPABILITY", k == "EXECUTION_FAILURE" and esc is False)
    k, reason, esc = taxonomy.classify("TIMEOUT", {})
    check("TIMEOUT_NOT_CAPABILITY", k == "EXECUTION_FAILURE" and esc is False)

    # malformed model output is a HARNESS/protocol problem, not capability
    k, reason, esc = taxonomy.classify(
        "CONTRACT_FAILURE", {"malformed_model_output": True}
    )
    check("MALFORMED_IS_HARNESS", k == "HARNESS_FAILURE" and esc is False)

    # single failure without repeats -> strategy territory (FIX/SPLIT ladder)
    k, reason, esc = taxonomy.classify(
        "TEST_FAILURE",
        {"attempt_count": 1, "strategy_delta": True, "new_evidence": ["x"]},
    )
    check("FIRST_FAILURE_STRATEGY", k == "STRATEGY_FAILURE" and esc is False)

    # repeated fundamental failure across justified deltas -> CAPABILITY
    k, reason, esc = taxonomy.classify(
        "TEST_FAILURE",
        {
            "attempt_count": 2,
            "same_fundamental_failure": True,
            "strategy_delta": True,
        },
    )
    check("AC11_CAPABILITY_CLASSIFIED", k == "CAPABILITY_FAILURE" and esc is True)

    # --- the controlled loop terminates in escalation (no infinite evolution)
    actions = run_cycle(max_cycles=5)
    final = actions[-1]
    check("AC11_LOOP_TERMINATES", final[0] == "ROUTE_ESCALATE")
    # exactly one strategy attempt, then capability classification, then
    # escalation — the loop must NOT keep evolving the harness forever
    classes = [a[0] for a in actions]
    check(
        "AC11_NO_INFINITE_LOOP",
        classes == ["STRATEGY_FAILURE", "CAPABILITY_FAILURE", "ROUTE_ESCALATE"],
        str(classes),
    )

    print("\nRESULT %d passed, %d failed" % (PASS, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
