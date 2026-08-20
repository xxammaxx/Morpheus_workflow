#!/usr/bin/env python3
"""Register the HAMH candidate (CANDIDATE status — never ACTIVE).

Adds the precision-edit candidate derived from the ACTIVE baseline entry.
The candidate is registered as CANDIDATE only; promotion requires the
authorized governance path (shadow -> canary -> ACTIVE) which this run
does NOT execute unless the value gate passes (order §34).
"""

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
PARENT_ID = "hamh/baseline/deepseek-v4-flash/build/thinking/v1"
CANDIDATE_ID = "hamh/candidate/build/precision-edit/v1"

EDIT_PROTOCOL = (
    "Edit protocol (precision_edit): use small, unique oldString anchors; "
    "before each edit, read the exact lines you intend to change; keep diffs "
    "minimal; one logical change per edit."
)


def main():
    if not os.path.exists(AUTHORITY_FILE):
        print("AUTHORITY_MISSING", file=sys.stderr)
        return 2
    authority = open(AUTHORITY_FILE).read().strip()
    reg = HarnessRegistry(REGISTRY_PATH, authority_token=authority)
    parent = reg.get(PARENT_ID)
    if parent is None:
        print("PARENT_NOT_FOUND", file=sys.stderr)
        return 1
    existing = reg.get(CANDIDATE_ID)
    if existing is not None:
        print("CANDIDATE_EXISTS status=%s" % existing.get("status"))
        return 0
    candidate = dict(parent)
    candidate["harness_id"] = CANDIDATE_ID
    # schema: parent_version max 32 chars [A-Za-z0-9._-]
    candidate["parent_version"] = parent.get("fingerprint")[:32]
    candidate["status"] = "DRAFT"
    candidate.pop("promotion_state", None)
    candidate["editing_profile"] = {
        "strategy": "precision_edit",
        "edit_protocol_instruction": EDIT_PROTOCOL,
    }
    candidate["fingerprint"] = _fp(
        {
            "harness_id": candidate["harness_id"],
            "editing_profile": candidate["editing_profile"],
            "parent": parent.get("fingerprint"),
        }
    )
    r = reg.add(candidate)
    if not r["ok"]:
        print("ADD_FAILED: %s" % r, file=sys.stderr)
        return 1
    r = reg.transition(CANDIDATE_ID, "CANDIDATE", "OPERATOR_REGISTERED")
    print(
        "CANDIDATE_REGISTERED status=%s fingerprint=%s"
        % (
            reg.get(CANDIDATE_ID).get("status"),
            reg.get(CANDIDATE_ID).get("fingerprint")[:24],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
