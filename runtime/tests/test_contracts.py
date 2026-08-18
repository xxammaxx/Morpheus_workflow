#!/usr/bin/env python3
"""Contract tests: validation, version rejection, fingerprint stability.

Run: python3 runtime/tests/test_contracts.py
Gates: CONTRACT_VALIDATION, CONTRACT_INVALID, CONTRACT_VERSION_REJECT,
       FINGERPRINT_STABILITY
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from contracts import registry  # noqa: E402

SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "..", "contracts", "schemas")


def load(name):
    with open(os.path.join(SCHEMA_DIR, name)) as f:
        return json.load(f)


def sample_issue(overrides=None, drop=None):
    p = {
        "contract": "autodev.issue.v1",
        "version": "v1",
        "run_id": "run-test-0001",
        "repository_ref": "autodev-v2-canary",
        "workspace": "ws-test",
        "task_description": "Implement a small greet function with tests.",
        "trace_id": "trace-1",
        "x-metadata": {"source": "test", "created_at": "2026-08-17T00:00:00Z"},
    }
    if overrides:
        p.update(overrides)
    if drop:
        for k in drop:
            p.pop(k, None)
    return p


def sample_plan(overrides=None, drop=None):
    p = {
        "contract": "autodev.plan.v1",
        "version": "v1",
        "run_id": "run-test-0001",
        "repository_head": "abcdef1234567890abcdef1234567890abcdef12",
        "targets": {"files": ["src/greeter.py"], "symbols": ["greet"]},
        "acceptance_criteria": ["greet('Welt') returns 'Hello, Welt!'"],
        "required_tests": ["tests/test_greeter.py"],
        "risks": [],
        "build_scope": {"allowed_files": ["src/greeter.py", "tests/test_greeter.py"]},
        "context": {"fingerprint": "a" * 64, "research_summary": "short"},
        "safety": {
            "sentinel_absent": True,
            "repo_unchanged": True,
            "write_attempts": 0,
        },
        "x-metadata": {"job_id": "j1"},
    }
    if overrides:
        p.update(overrides)
    if drop:
        for k in drop:
            p.pop(k, None)
    return p


def main():
    passed = failed = 0

    def check(name, cond, detail=""):
        nonlocal passed, failed
        if cond:
            passed += 1
            print("PASS %s" % name)
        else:
            failed += 1
            print("FAIL %s %s" % (name, detail))

    # --- CONTRACT_VALIDATION: every schema accepts its canonical sample
    valid_samples = {
        "autodev.issue.v1": sample_issue(),
        "autodev.baseline.v1": {
            "contract": "autodev.baseline.v1",
            "version": "v1",
            "run_id": "run-test-0001",
            "repository": {
                "identity": "git@x/y",
                "head": "abcdef1",
                "branch": "main",
                "working_tree_clean": True,
                "build_system": "python",
                "test_system": "pytest",
                "relevant_files": ["src/a.py"],
                "constraints": [],
            },
            "read_only_proof": {"sentinel_absent": True, "git_status_unchanged": True},
            "x-metadata": {},
        },
        "autodev.research.v1": {
            "contract": "autodev.research.v1",
            "version": "v1",
            "run_id": "run-test-0001",
            "areas": {"code": "n", "docs": "n", "tests": "n"},
            "parallelism": {
                "jobs": [
                    {
                        "job_id": "j1",
                        "job_type": "research.code",
                        "started_at": "t",
                        "ended_at": "t",
                        "duration_ms": 1,
                    }
                ],
                "overlap_proven": True,
            },
            "x-metadata": {},
        },
        "autodev.plan.v1": sample_plan(),
        "autodev.build-input.v1": {
            "contract": "autodev.build-input.v1",
            "version": "v1",
            "run_id": "run-test-0001",
            "attempt_id": "run-test-0001:build:1",
            "plan_fingerprint": "b" * 64,
            "repository_head": "abcdef1",
            "targets": {"files": ["src/greeter.py"]},
            "acceptance_criteria": ["ok"],
            "required_tests": ["t"],
            "build_scope": {"allowed_files": ["src/greeter.py"]},
            "x-metadata": {},
        },
        "autodev.build-result.v1": {
            "contract": "autodev.build-result.v1",
            "version": "v1",
            "run_id": "run-test-0001",
            "status": "success",
            "changed_files": [{"path": "src/a.py", "change": "add", "size": 10}],
            "summary": "ok",
            "x-metadata": {},
        },
        "autodev.verification.v1": {
            "contract": "autodev.verification.v1",
            "version": "v1",
            "run_id": "run-test-0001",
            "passed": True,
            "checks": [
                {"name": "unit", "type": "unit", "passed": True, "detail": "1 passed"}
            ],
            "failure_class": None,
            "failure_signature": None,
            "new_evidence": [],
            "x-metadata": {},
        },
        "autodev.finding.v1": {
            "category": "security",
            "severity": "CRITICAL",
            "confidence": "HIGH",
            "blocking": True,
            "rule": "SEC-001",
            "evidence": {"file": "src/a.py", "symbol": "x", "line_range": "1-5"},
            "recommendation": "remove secret",
        },
        "autodev.review-batch.v1": {
            "contract": "autodev.review-batch.v1",
            "version": "v1",
            "run_id": "run-test-0001",
            "reviews": [
                {
                    "category": "security",
                    "verdict": "FAIL",
                    "findings": [
                        {
                            "category": "security",
                            "severity": "CRITICAL",
                            "confidence": "HIGH",
                            "blocking": True,
                            "rule": "SEC-001",
                            "evidence": {"file": "a.py"},
                            "recommendation": "x",
                        }
                    ],
                }
            ],
            "blocked": True,
            "blocking_findings": [],
            "parallelism": {"jobs": [], "overlap_proven": True},
            "x-metadata": {},
        },
        "autodev.decision.v1": {
            "contract": "autodev.decision.v1",
            "version": "v1",
            "run_id": "run-test-0001",
            "decision": "DONE",
            "reason_code": "ALL_HARD_GATES_GREEN",
            "next": "terminal",
            "evidence": {"verification_ref": "v", "review_ref": "r"},
            "x-metadata": {},
        },
        "autodev.split.v1": {
            "contract": "autodev.split.v1",
            "version": "v1",
            "parent_run_id": "run-test-0001",
            "reason": "retry exhausted",
            "reason_code": "RETRY_DENIED_ATTEMPT_LIMIT",
            "subtasks": [
                {"id": "st-1", "title": "Subtask A", "description": "do thing A properly"},
                {"id": "st-2", "title": "Subtask B", "description": "do thing B properly"},
            ],
            "dependencies": [["st-1", "st-2"]],
            "acceptance_criteria": ["A and B done"],
            "limits": {"max_split_depth": 2, "max_subtasks": 5, "current_depth": 1},
            "x-metadata": {},
        },
        "autodev.run-event.v1": {
            "contract": "autodev.run-event.v1",
            "version": "v1",
            "run_id": "run-test-0001",
            "event": "STATE_CHANGE",
            "timestamp": "2026-08-17T00:00:00Z",
            "state": {"previous_state": "ACCEPTED", "new_state": "BASELINING"},
            "reason_code": "INTAKE_OK",
            "x-metadata": {},
        },
    }
    for cid, sample in valid_samples.items():
        r = registry.validate(sample, cid)
        check("VALID_%s" % cid, r["ok"], json.dumps(r))

    # --- CONTRACT_INVALID
    bad = sample_issue(drop=["task_description"])
    r = registry.validate(bad)
    check(
        "INVALID_ISSUE_MISSING_TASK",
        not r["ok"] and "$: task_description is required" in r["errors"],
        json.dumps(r),
    )

    bad2 = sample_issue(overrides={"run_id": "bad id with spaces!"})
    r = registry.validate(bad2)
    check(
        "INVALID_ISSUE_RUNID_PATTERN",
        not r["ok"] and "pattern" in str(r["errors"]),
        json.dumps(r),
    )

    bad3 = sample_plan(drop=["acceptance_criteria"])
    r = registry.validate(bad3)
    check(
        "INVALID_PLAN_NO_AC",
        not r["ok"] and "$: acceptance_criteria is required" in r["errors"],
        json.dumps(r),
    )

    bad4 = sample_plan(
        overrides={
            "safety": {
                "sentinel_absent": False,
                "repo_unchanged": True,
                "write_attempts": 0,
            }
        }
    )
    r = registry.validate(bad4)
    check("INVALID_PLAN_SENTINEL", not r["ok"], json.dumps(r))

    bad5 = sample_plan(overrides={"targets": {"files": [], "symbols": []}})
    r = registry.validate(bad5)
    check("INVALID_PLAN_EMPTY_TARGETS", not r["ok"], json.dumps(r))

    bad6 = {"contract": "autodev.plan.v1", "version": "v1", "run_id": "x"}
    r = registry.validate(bad6)
    check("INVALID_PLAN_GARBAGE", not r["ok"], json.dumps(r))

    # --- CONTRACT_VERSION_REJECT
    badv = sample_issue(overrides={"version": "v2"})
    r = registry.validate(badv)
    check(
        "VERSION_REJECT", not r["ok"] and "version" in str(r["errors"]), json.dumps(r)
    )

    # unknown contract
    r = registry.validate({"contract": "autodev.unknown.v9"})
    check("UNKNOWN_CONTRACT", not r["ok"], json.dumps(r))

    # --- FINGERPRINT_STABILITY
    a = sample_issue()
    b = sample_issue()  # same semantic content
    fa, fb = registry.fingerprint(a), registry.fingerprint(b)
    check("FP_SAME_SEMANTIC", fa == fb, "%s != %s" % (fa, fb))

    c = sample_issue(overrides={"x-metadata": {"other": "value"}})
    fc = registry.fingerprint(c)
    check("FP_METADATA_INSENSITIVE", fa == fc)

    d = sample_issue(overrides={"task_description": "A DIFFERENT task description."})
    fd = registry.fingerprint(d)
    check("FP_CHANGED_CONTENT", fa != fd, "hash collision!")

    e = sample_issue(overrides={"acceptance_hint": "hint changed"})
    fe = registry.fingerprint(e)
    check("FP_ADDED_FIELD", fa != fe)

    # key-order invariance (semantic JSON)
    import copy

    f_reordered = json.loads(json.dumps(a))
    f_reordered = {k: f_reordered[k] for k in reversed(list(f_reordered.keys()))}
    check("FP_KEY_ORDER_INVARIANT", registry.fingerprint(f_reordered) == fa)

    # run-event fingerprint
    ev = valid_samples["autodev.run-event.v1"]
    ev2 = json.loads(json.dumps(ev))
    ev2["x-metadata"]["session_id"] = "zzz"
    check("FP_RUNEVENT_META", registry.fingerprint(ev) == registry.fingerprint(ev2))

    print("\nRESULT %d passed, %d failed" % (passed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
