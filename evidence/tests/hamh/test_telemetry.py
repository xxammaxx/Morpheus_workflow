#!/usr/bin/env python3
"""HAMH trajectory telemetry tests (ADR H11) — privacy by default.

Proves: denied keys are rejected at the top level AND stripped at any
nesting depth (the sanitizer is applied to the final record, not only to
top-level kwargs).

Run: python3 evidence/tests/hamh/test_telemetry.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "runtime"))

from hamh import telemetry  # noqa: E402

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


def main():
    # --- all trajectory fields present with None defaults
    rec = telemetry.build_trajectory("run-1")
    for field in telemetry.TRAJECTORY_FIELDS:
        check("FIELD_%s" % field.upper(), field in rec)
    check("RUN_ID_SET", rec["run_id"] == "run-1")

    # --- top-level denied key raises
    try:
        telemetry.build_trajectory("run-2", reasoning_content="secret CoT")
        check("PRIVACY_TOPLEVEL_REJECT", False, "expected ValueError")
    except ValueError:
        check("PRIVACY_TOPLEVEL_REJECT", True)

    # --- nested denied content is stripped at ANY depth (bypass attempt)
    rec = telemetry.build_trajectory(
        "run-3",
        verification_result={
            "checks": [
                {
                    "name": "unit",
                    "detail": "ok",
                    "reasoning_content": "nested secret CoT",
                },
            ]
        },
        trace=[
            {
                "role": "assistant",
                "content": "answer",
                "reasoning_content": "deeply nested CoT",
            },
        ],
    )
    nested = rec["verification_result"]["checks"][0]
    check("PRIVACY_NESTED_STRIPPED", "reasoning_content" not in nested, str(nested))
    check("PRIVACY_DEEPLY_NESTED_STRIPPED", "reasoning_content" not in rec["trace"][0])
    check(
        "PRIVACY_BENIGN_KEPT", rec["verification_result"]["checks"][0]["detail"] == "ok"
    )

    # --- sanitize is recursive and idempotent
    dirty = {"a": 1, "blob": {"x": 1}, "list": [{"secret": "s"}, {"ok": True}]}
    clean = telemetry.sanitize(dirty)
    check("SANITIZE_TOP", "blob" not in clean)
    check("SANITIZE_NESTED", "secret" not in clean["list"][0])
    check("SANITIZE_IDEMPOTENT", telemetry.sanitize(clean) == clean)

    print("\nRESULT %d passed, %d failed" % (PASS, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
