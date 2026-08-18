#!/usr/bin/env python3
"""AutoDev contract fingerprints — canonical SHA-256.

Canonical serialization:
    semantic JSON -> stable canonicalization (recursively sorted keys,
    ensure_ascii, no whitespace) -> SHA-256 hex.

Non-semantic runtime metadata (top-level "x-metadata" key and schema-declared
x-metadata field names) never changes the fingerprint.

Properties:
    same semantic content -> same hash
    changed semantic content -> changed hash
"""

import hashlib
import json
import os


def canonicalize(obj):
    """Stable canonical string form of a JSON value."""
    if isinstance(obj, dict):
        parts = []
        for key in sorted(obj.keys()):
            parts.append(json.dumps(key, ensure_ascii=True))
            parts.append(":")
            parts.append(canonicalize(obj[key]))
            parts.append(",")
        return "{" + "".join(parts) + "}"
    if isinstance(obj, list):
        return "[" + ",".join(canonicalize(item) for item in obj) + "]"
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if obj is None:
        return "null"
    if isinstance(obj, (int, float)):
        return json.dumps(obj, ensure_ascii=True)
    return json.dumps(obj, ensure_ascii=True)


def semantic_part(payload, exclude_keys=("x-metadata",)):
    """Strip non-semantic metadata from the payload before hashing."""
    if isinstance(payload, dict):
        return {
            key: semantic_part(value, exclude_keys)
            for key, value in payload.items()
            if key not in exclude_keys
        }
    if isinstance(payload, list):
        return [semantic_part(item, exclude_keys) for item in payload]
    return payload


def fingerprint(payload, exclude_keys=("x-metadata",)):
    """SHA-256 over canonicalized semantic payload."""
    canonical = canonicalize(semantic_part(payload, exclude_keys))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    import sys

    with open(sys.argv[1]) as f:
        data = json.load(f)
    print(fingerprint(data))
