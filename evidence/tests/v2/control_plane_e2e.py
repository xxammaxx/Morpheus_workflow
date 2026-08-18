#!/usr/bin/env python3
"""AutoDev Harness v2 — control-plane E2E matrix (fixture-driven, embedded backend).

Each test: POST /autodev/start -> poll status until terminal -> assert state/decision.

Run: python3 control_plane_e2e.py
"""

import json
import os
import sys
import time
import urllib.request

BASE = "http://192.168.1.52:5678"
TOKEN_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "..",
    "..",
    ".secrets",
    "autodev_api_token",
)

RESULTS = []


def api(method, path, body=None, token=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"X-AutoDev-Token": token or "", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode() or "{}")


def start_run(fixture, backend="embedded", task_desc=None):
    token = open(TOKEN_FILE).read().strip()
    body = {
        "task": {
            "task_ref": "e2e-" + (fixture or "happy"),
            "repository_ref": "autodev-v2-canary",
            "workspace": "autodev-v2-canary",
            "task_description": task_desc
            or "Implement a small greet function with tests.",
        },
        "fixture": fixture,
        "backend": backend,
    }
    resp = api("POST", "/webhook/autodev/start", body, token)
    return resp.get("run_id"), token


def wait_terminal(run_id, token, timeout=300):
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        try:
            s = api(
                "GET",
                "/webhook/autodev/status?run_id=" + run_id,
                token=token,
                timeout=10,
            )
        except Exception:
            time.sleep(10)
            continue
        if s.get("state") in (
            "PLAN_BLOCKED",
            "BLOCKED",
            "DONE",
            "SPLIT_REQUIRED",
            "FAILED",
        ):
            return s
        last = s
        time.sleep(10)
    return last


def test(
    name, fixture, expect_state, expect_decision=None, expect_reason=None, timeout=300
):
    try:
        run_id, token = start_run(fixture)
        if not run_id:
            RESULTS.append((name, False, "no run_id"))
            return
        s = wait_terminal(run_id, token, timeout)
        ok = s is not None and s.get("state") == expect_state
        if expect_decision:
            ok = ok and s.get("decision") == expect_decision
        if expect_reason:
            ok = ok and expect_reason in (s.get("reason_code") or "")
        detail = (
            json.dumps(
                {
                    k: s.get(k)
                    for k in ("state", "decision", "reason_code", "result_ref")
                }
            )
            if s
            else "no status"
        )
        RESULTS.append((name, ok, detail + " run=" + run_id))
    except Exception as e:
        RESULTS.append((name, False, str(e)[:200]))


def main():
    # negative paths
    test(
        "E2E_INVALID_PLAN_GATE_REJECT",
        "invalid_plan",
        "PLAN_BLOCKED",
        "BLOCKED",
        "PLAN_RUN_ID_MISMATCH",
    )
    test(
        "E2E_VERIFY_FAIL_NO_DELTA_SPLIT",
        "verify_fail_no_delta",
        "SPLIT_REQUIRED",
        "SPLIT",
        "RETRY_DENIED_NO_STRATEGY_DELTA",
    )
    test(
        "E2E_VERIFY_NO_SIGNATURE_SPLIT",
        "no_signature",
        "SPLIT_REQUIRED",
        "SPLIT",
        "RETRY_DENIED_NO_FAILURE_SIGNATURE",
    )
    test(
        "E2E_ATTEMPT_LIMIT_SPLIT",
        "attempt_limit",
        "SPLIT_REQUIRED",
        "SPLIT",
        "RETRY_DENIED_ATTEMPT_LIMIT",
    )
    test(
        "E2E_SECURITY_HARD_BLOCK",
        "security_critical_blocking",
        "BLOCKED",
        "BLOCKED",
        "BLOCKING_HIGH_OR_CRITICAL_FINDING",
    )
    test(
        "E2E_REVIEW_SPLIT",
        "review_split",
        "SPLIT_REQUIRED",
        "SPLIT",
        "REVIEW_REQUESTED_SPLIT",
    )

    # happy + fix paths
    test("E2E_HAPPY_PATH", None, "DONE", "DONE", "ALL_HARD_GATES_GREEN")
    test("E2E_FIX_PATH", "verify_fail_delta", "DONE", "DONE", "ALL_HARD_GATES_GREEN")
    test("E2E_REVIEW_FIX_PATH", "review_fix", "DONE", "DONE", "ALL_HARD_GATES_GREEN")

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = len(RESULTS) - passed
    out = "CONTROL_PLANE_E2E %d passed, %d failed\n" % (passed, failed)
    for name, ok, detail in RESULTS:
        out += ("PASS " if ok else "FAIL ") + name + " :: " + detail + "\n"
    with open(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "control-plane-e2e-result.txt"
        ),
        "w",
    ) as f:
        f.write(out)
    print(out)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
