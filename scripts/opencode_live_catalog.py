#!/usr/bin/env python3
"""Expose CT8001's live OpenCode model catalog as JSON lines."""

import json
import re
import subprocess
import sys


ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
OPENCode = "/opt/dev-fabric/opencode/opencode"


def main(argv=None):
    args = list(argv or sys.argv[1:])
    if not args:
        args = ["models", "--refresh", "--verbose"]
    command = [
        "pct", "exec", "8001", "--", "su", "-", "builder", "-c",
        " ".join([OPENCode, *args]),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    output = ANSI.sub("", result.stdout or "")
    decoder = json.JSONDecoder()
    cursor = 0
    found = 0
    while True:
        start = output.find("{", cursor)
        if start < 0:
            break
        try:
            value, end = decoder.raw_decode(output[start:])
        except json.JSONDecodeError:
            cursor = start + 1
            continue
        cursor = start + end
        if not isinstance(value, dict) or not value.get("providerID") or not value.get("id"):
            continue
        cost = value.get("cost") if isinstance(value.get("cost"), dict) else {}
        limit = value.get("limit") if isinstance(value.get("limit"), dict) else {}
        print(json.dumps({
            "provider": value["providerID"],
            "id": value["id"],
            "pricing": {
                "prompt": cost.get("input"),
                "completion": cost.get("output"),
            },
            "capabilities": value.get("capabilities") or {},
            "context_length": limit.get("context", 0),
            "name": value.get("name", ""),
            "family": value.get("family", ""),
            "supported_parameters": value.get("supported_parameters") or [],
        }, sort_keys=True))
        found += 1
    if result.stderr:
        sys.stderr.write(result.stderr)
    if result.returncode != 0 or not found:
        return result.returncode or 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
