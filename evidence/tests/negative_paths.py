#!/usr/bin/env python3
"""Phase E: Negative path tests via real webhook POSTs (deterministic fixtures)."""

import json
import time
import urllib.request

WEBHOOK = "http://192.168.1.52:5678/webhook/autodev-harness"


def post(payload):
    req = urllib.request.Request(
        WEBHOOK,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.loads(r.read().decode())


SCENARIOS = [
    {
        "name": "invalid_plan",
        "payload": {
            "task": "neg: invalid plan",
            "repository": "local-canary/greeter",
            "fixture": "invalid_plan",
            "max_attempts": 2,
        },
        "expect_decision": "BLOCKED",
        "expect_reason": "ACCEPTANCE_CRITERIA_MISSING",
    },
    {
        "name": "verify_fail_delta",
        "payload": {
            "task": "neg: verify fail with delta",
            "repository": "local-canary/greeter",
            "fixture": "verify_fail_delta",
            "max_attempts": 2,
        },
        "expect_decision": "DONE",
        "expect_reason": "ALL_HARD_GATES_GREEN",
    },
    {
        "name": "verify_fail_no_delta",
        "payload": {
            "task": "neg: verify fail no delta",
            "repository": "local-canary/greeter",
            "fixture": "verify_fail_no_delta",
            "max_attempts": 2,
        },
        "expect_decision": "SPLIT",
        "expect_reason": "RETRY_DENIED_NO_STRATEGY_DELTA",
    },
    {
        "name": "no_signature",
        "payload": {
            "task": "neg: no failure signature",
            "repository": "local-canary/greeter",
            "fixture": "no_signature",
            "max_attempts": 2,
        },
        "expect_decision": "SPLIT",
        "expect_reason": "RETRY_DENIED_NO_FAILURE_SIGNATURE",
    },
    {
        "name": "attempt_limit",
        "payload": {
            "task": "neg: attempt limit",
            "repository": "local-canary/greeter",
            "fixture": "attempt_limit",
            "max_attempts": 2,
        },
        "expect_decision": "SPLIT",
        "expect_reason": "RETRY_DENIED_ATTEMPT_LIMIT",
    },
    {
        "name": "security_critical_blocking",
        "payload": {
            "task": "neg: security critical",
            "repository": "local-canary/greeter",
            "fixture": "security_critical_blocking",
            "max_attempts": 2,
        },
        "expect_decision": "BLOCKED",
        "expect_reason": "BLOCKING_HIGH_OR_CRITICAL_FINDING",
    },
    {
        "name": "review_fix",
        "payload": {
            "task": "neg: non-blocking review finding",
            "repository": "local-canary/greeter",
            "fixture": "review_fix",
            "max_attempts": 2,
        },
        "expect_decision": "FIX",
        "expect_reason": "NON_BLOCKING_REVIEW_FINDINGS",
    },
    {
        "name": "review_split",
        "payload": {
            "task": "neg: review requests split",
            "repository": "local-canary/greeter",
            "fixture": "review_split",
            "max_attempts": 2,
        },
        "expect_decision": "SPLIT",
        "expect_reason": "REVIEW_REQUESTED_SPLIT",
    },
    {
        "name": "intake_invalid",
        "payload": {"repository": "local-canary/greeter", "max_attempts": 2},
        "expect_decision": "BLOCKED",
        "expect_reason": "INTAKE_INVALID",
        "expect_run_id": False,
    },
]

results = {}
all_pass = True
for sc in SCENARIOS:
    try:
        resp = post(sc["payload"])
        decision = resp.get("decision")
        reason = resp.get("reason_code")
        run_id = resp.get("run_id")
        ok = (
            decision == sc["expect_decision"]
            and reason == sc["expect_reason"]
            and (sc.get("expect_run_id", True) is False or bool(run_id))
        )
        results[sc["name"]] = {
            "ok": ok,
            "decision": decision,
            "reason": reason,
            "run_id": run_id,
        }
        all_pass = all_pass and ok
    except Exception as e:
        results[sc["name"]] = {"ok": False, "error": str(e)}
        all_pass = False
    time.sleep(1)

print(json.dumps(results, indent=2))
print("ALL_NEGATIVE_PASS", all_pass)
