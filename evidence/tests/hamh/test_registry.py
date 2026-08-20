#!/usr/bin/env python3
"""HAMH registry tests (AC-3, AC-8, AC-10).

Run: python3 evidence/tests/hamh/test_registry.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "runtime"))

from contracts.fingerprint import fingerprint as fp  # noqa: E402
from hamh import registry  # noqa: E402

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


def entry(
    hid,
    provider="deepseek",
    model="deepseek-v4-flash",
    task_class="build",
    runtime_mode="thinking",
    status="DRAFT",
):
    return {
        "contract": "hamh.harness.v1",
        "version": "v1",
        "harness_id": hid,
        "provider": provider,
        "model": model,
        "model_revision": "0731",
        "task_class": task_class,
        "runtime_mode": runtime_mode,
        "harness_version": "v1",
        "status": status,
        "fingerprint": fp({"hid": hid}),
        "prompt_profile": {"style": "v1"},
        "context_profile": {"stable_prefix": ["system"]},
        "tool_profile": {"capabilities": {}, "presentation": "flat"},
        "created_at": "2026-08-20T00:00:00Z",
    }


def promote_through(reg, hid, token="real-authority"):
    for state in ("CANDIDATE", "SHADOW", "CANARY"):
        r = reg.transition(hid, state)
        assert r["ok"], r
    return reg.promote(hid, token)


def main():
    import tempfile

    tmp = tempfile.mkdtemp(prefix="hamh-registry-")
    path = os.path.join(tmp, "registry.json")

    # --- AC-10: no authority configured -> promote ALWAYS denied
    reg0 = registry.HarnessRegistry(path=path)
    r = reg0.add(entry("h/noauth/v1"))
    check("AC10_ADD_DRAFT_OK", r["ok"])
    # walk to CANARY WITHOUT authority (transitions are gate-bound, not
    # authority-bound; only the ACTIVE promotion is authority-gated)
    for state in ("CANDIDATE", "SHADOW", "CANARY"):
        assert reg0.transition("h/noauth/v1", state)["ok"]
    promote_through_noauth = reg0.promote("h/noauth/v1", "whatever-token")
    check(
        "AC10_NO_AUTHORITY_PROMOTE_DENIED",
        promote_through_noauth.get("code") == "PROMOTE_DENIED",
    )

    # --- AC-10: wrong token denied
    reg = registry.HarnessRegistry(path=path, authority_token="real-authority")
    r = reg.add(entry("h/v1"))
    check("ADD_OK", r["ok"])
    for state in ("CANDIDATE", "SHADOW", "CANARY"):
        assert reg.transition("h/v1", state)["ok"]
    r = reg.promote("h/v1", "wrong-token")
    check("AC10_WRONG_TOKEN_DENIED", r.get("code") == "PROMOTE_DENIED")
    r = reg.promote("h/v1", "real-authority")
    check("AC10_RIGHT_TOKEN_ALLOWED", r["ok"])
    check("AC10_ACTIVE_SET", reg.get("h/v1")["status"] == "ACTIVE")

    # --- AC-3: candidate can never set itself ACTIVE
    r = reg.add(entry("h/selfpromo/v1"))
    check("SELF_ADD_OK", r["ok"])
    r = reg.add(entry("h/selfpromo-active/v1", status="ACTIVE"))
    check("AC3_INITIAL_ACTIVE_FORBIDDEN", r.get("code") == "INITIAL_STATUS_FORBIDDEN")
    # jumping DRAFT -> ACTIVE is forbidden regardless of authority
    r = reg.transition("h/selfpromo/v1", "ACTIVE", authority_token="real-authority")
    check(
        "AC3_DRAFT_TO_ACTIVE_FORBIDDEN",
        r.get("code") in ("TRANSITION_FORBIDDEN", "PROMOTE_FROM_CANARY_ONLY"),
    )

    # --- forbidden transitions
    r = reg.transition("h/v1", "DRAFT")
    check(
        "TRANSITION_ACTIVE_TO_DRAFT_FORBIDDEN", r.get("code") == "TRANSITION_FORBIDDEN"
    )

    # --- supersede + AC-8 rollback restores EXACT previous active
    r = reg.add(entry("h/v2"))
    promote_through(reg, "h/v2")
    check("V2_ACTIVE", reg.get("h/v2")["status"] == "ACTIVE")
    check("V1_SUPERSEDED_RETIRED", reg.get("h/v1")["status"] == "RETIRED")
    r = reg.rollback("h/v2", "wrong-token")
    check("AC8_ROLLBACK_WRONG_TOKEN_DENIED", r.get("code") == "ROLLBACK_DENIED")
    r = reg.rollback("h/v2", "real-authority")
    check("AC8_ROLLBACK_OK", r["ok"])
    restored = reg.get("h/v1")
    check(
        "AC8_ROLLBACK_EXACT_CONFIG",
        restored is not None
        and restored["status"] == "ACTIVE"
        and restored["prompt_profile"] == {"style": "v1"}
        and restored["harness_id"] == "h/v1",
    )
    check("AC8_ROLLBACK_V2_RETIRED", reg.get("h/v2")["status"] == "RETIRED")

    # --- persistence round-trip
    reg.save()
    reg2 = registry.HarnessRegistry(path=path, authority_token="real-authority")
    check("PERSIST_ENTRIES", set(reg2.entries().keys()) == set(reg.entries().keys()))
    check("PERSIST_STATUS", reg2.get("h/v1")["status"] == "ACTIVE")

    # --- deep-copy isolation at the API surface
    e = reg2.get("h/v1")
    e["prompt_profile"]["style"] = "MUTATED_BY_CALLER"
    check("ISOLATION_READ_COPY", reg2.get("h/v1")["prompt_profile"]["style"] == "v1")

    # --- corrupt registry file: backup + start empty, never crash
    corrupt_path = os.path.join(tmp, "corrupt.json")
    with open(corrupt_path, "w") as f:
        f.write("{ this is not json !!!")
    reg3 = registry.HarnessRegistry(path=corrupt_path)
    check("CORRUPT_FILE_NO_CRASH", reg3.entries() == {})
    backups = [n for n in os.listdir(tmp) if n.startswith("corrupt.json.corrupt-")]
    check("CORRUPT_FILE_BACKED_UP", len(backups) == 1)

    # --- thread-safety smoke: concurrent adds never corrupt the store
    import threading

    reg4 = registry.HarnessRegistry(
        path=os.path.join(tmp, "threads.json"), authority_token="t"
    )
    errors = []

    def worker(i):
        try:
            for k in range(10):
                reg4.add(entry("thread/%d/v%d" % (i, k)))
        except Exception as exc:  # noqa: BLE001 - test collects
            errors.append(str(exc))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    check(
        "THREADSAFE_ADDS", not errors and len(reg4.entries()) == 80, str(errors)[:200]
    )

    print("\nRESULT %d passed, %d failed" % (PASS, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
