#!/usr/bin/env python3
"""AutoDev contract registry — CONTRACT_ID -> SCHEMA -> VALIDATOR.

Used by the harness adapter (deployed copy) and by the test suite.
"""

import json
import os

from . import fingerprint as _fp
from . import validator as _val

SCHEMA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schemas")

CONTRACTS = [
    "autodev.issue.v1",
    "autodev.baseline.v1",
    "autodev.research.v1",
    "autodev.plan.v1",
    "autodev.build-input.v1",
    "autodev.build-result.v1",
    "autodev.verification.v1",
    "autodev.finding.v1",
    "autodev.review-batch.v1",
    "autodev.decision.v1",
    "autodev.split.v1",
    "autodev.run-event.v1",
    "hamh.harness.v1",
    "hamh.resolution.v1",
    "provider.execution-proof.v1",
    "autodev.benchmark-task.v1",
    "autodev.benchmark-result.v1",
    "autodev.context-pack.v1",
    "autodev.experience.v1",
    "autodev.harness-candidate.v1",
    "autodev.adaptive-metadata.v1",
]

_SCHEMAS = {}


def get_schema(contract_id):
    if contract_id not in _SCHEMAS:
        path = os.path.join(SCHEMA_DIR, contract_id + ".schema.json")
        with open(path) as f:
            _SCHEMAS[contract_id] = json.load(f)
    return _SCHEMAS[contract_id]


def validate(payload, contract_id=None):
    """Validate payload. contract_id inferred from payload.contract if omitted."""
    if contract_id is None:
        contract_id = payload.get("contract") if isinstance(payload, dict) else None
    if contract_id not in CONTRACTS:
        return {
            "ok": False,
            "contract": contract_id,
            "errors": [
                "unknown contract %r (known: %s)" % (contract_id, ", ".join(CONTRACTS))
            ],
            "error_count": 1,
        }
    schema = get_schema(contract_id)
    result = _val.validate(payload, schema)
    # enforce version tag consistency (only for contracts whose schema declares "version")
    if result["ok"] and "version" in schema.get("properties", {}):
        expected = schema.get("version", "v1")
        if payload.get("version") != expected:
            result = {
                "ok": False,
                "contract": contract_id,
                "errors": [
                    "version %r does not match schema version %r"
                    % (payload.get("version"), expected)
                ],
                "error_count": 1,
            }
    return result


def fingerprint(payload):
    return _fp.fingerprint(payload)


def load_all_schemas():
    return {cid: get_schema(cid) for cid in CONTRACTS}
