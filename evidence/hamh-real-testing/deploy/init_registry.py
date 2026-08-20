#!/usr/bin/env python3
"""HAMH registry initializer (operator-authorized, additive deployment).

Creates/updates the registry at state/registry.json with the EXPLICIT
baseline harness entry for the production identity:

    provider=deepseek  model=deepseek-v4-flash  task_class=build
    runtime_mode=thinking

The entry mirrors the shared baseline profiles exactly (no specialization,
no tuning) so that resolution for the production identity is explicit
(is_fallback=false) while behaving identically to the fallback profiles.
Promotion to ACTIVE uses the EXISTING adapter secret store as authority
(/var/lib/autodev-harness-v2/api-token) — operator-authorized only,
EVOLVER_CAN_PROMOTE stays NO.

Stdlib only. Idempotent.
"""

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "runtime"))
sys.path.insert(0, os.path.join(HERE, "runtime", "hamh"))
sys.path.insert(0, os.path.join(HERE, "runtime", "contracts"))

from contracts.fingerprint import fingerprint as _fp  # noqa: E402
from hamh.registry import HarnessRegistry  # noqa: E402

STATE_DIR = os.path.join(HERE, "state")
REGISTRY_PATH = os.path.join(STATE_DIR, "registry.json")
AUTHORITY_FILE = "/var/lib/autodev-harness-v2/api-token"

ENTRIES = [
    {
        "contract": "hamh.harness.v1",
        "version": "v1",
        "harness_id": "hamh/baseline/deepseek-v4-flash/build/thinking/v1",
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "model_revision": "0731",
        "task_class": "build",
        "runtime_mode": "thinking",
        "harness_version": "v1",
        "prompt_profile": {
            "thinking": "enabled",
            "reasoning_effort": "high",
        },
        "context_profile": {
            "stable_prefix": ["system_instructions", "tool_schemas"],
            "variable": ["task", "retrieved_files", "execution_state"],
            "cache_layout": "stable_first",
        },
        "tool_profile": {
            "capabilities": {},
            "presentation": "flat",
        },
        "created_at": "2026-08-20T00:00:00Z",
        "evaluation_reference": {},
    },
]


def main():
    os.makedirs(STATE_DIR, exist_ok=True)
    if not os.path.exists(AUTHORITY_FILE):
        print("AUTHORITY_MISSING: %s" % AUTHORITY_FILE, file=sys.stderr)
        return 2
    authority = open(AUTHORITY_FILE).read().strip()

    reg = HarnessRegistry(REGISTRY_PATH, authority_token=authority)
    for entry in ENTRIES:
        entry = dict(entry)
        entry["fingerprint"] = _fp(
            {
                "harness_id": entry["harness_id"],
                "provider": entry["provider"],
                "model": entry["model"],
            }
        )
        hid = entry["harness_id"]
        existing = reg.get(hid)
        if existing is None:
            r = reg.add(dict(entry, status="DRAFT"))
            if not r["ok"]:
                print("ADD_FAILED %s: %s" % (hid, r), file=sys.stderr)
                return 1
            r = reg.transition(hid, "CANDIDATE", "OPERATOR_INIT")
            r = reg.transition(hid, "SHADOW", "OPERATOR_INIT")
            r = reg.transition(hid, "CANARY", "OPERATOR_INIT")
            r = reg.promote(hid, authority)
            print("PROMOTED %s -> %s" % (hid, r.get("status")))
        else:
            print("EXISTS %s status=%s" % (hid, existing.get("status")))
            if existing.get("status") != "ACTIVE":
                reg.promote(hid, authority)
                print("RE-PROMOTED -> ACTIVE")
    # show final state
    reg2 = HarnessRegistry(REGISTRY_PATH, authority_token=authority)
    for hid, e in sorted(reg2.entries().items()):
        print(
            "REGISTRY %s | %s | %s" % (hid, e.get("status"), e.get("promotion_state"))
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
