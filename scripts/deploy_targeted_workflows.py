#!/usr/bin/env python3
"""Deploy only the explicitly allowlisted canonical n8n workflows."""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import urllib.error
import urllib.request
import sys

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from scripts.deployment_provenance import git_blob, valid_commit, workflow_sources  # noqa: E402

BASE = "http://192.168.1.52:5678"
API_KEY_PATH = pathlib.Path("/var/lib/n8n-spec-kit/secrets/ghiw-n8n-api-key")
ALLOWLIST = frozenset({
    "00 AutoDev API Start",
    "01 AutoDev Orchestrator",
    "05 AutoDev Control Gateway",
    "06 AutoDev Project Analysis",
    "07 AutoDev Blueprint Bootstrap",
    "08 AutoDev Project Reassessment",
})


def select_names(names: list[str]) -> list[str]:
    if not names or any(name not in ALLOWLIST for name in names) or len(set(names)) != len(names):
        raise ValueError("WORKFLOW_NAME_NOT_ALLOWLISTED_OR_DUPLICATE")
    return names


def api(method: str, path: str, body: object | None = None) -> tuple[int, dict]:
    key = API_KEY_PATH.read_text(encoding="utf-8").strip()
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(BASE + path, data=data, method=method,
                                     headers={"X-N8N-API-KEY": key,
                                              "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, {}


def deploy(commit: str, names: list[str]) -> dict:
    if not valid_commit(commit):
        raise ValueError("SOURCE_COMMIT_INVALID")
    names = select_names(names)
    source_by_name = {item["workflow_name"]: item for item in workflow_sources(commit)}
    if set(names) - set(source_by_name):
        raise ValueError("WORKFLOW_SOURCE_MISSING")
    status, listing = api("GET", "/api/v1/workflows?limit=250")
    if status != 200:
        raise RuntimeError(f"WORKFLOW_LIST_FAILED_HTTP_{status}")
    ids = {}
    for name in names:
        matches = [item for item in listing.get("data", []) if item.get("name") == name]
        if len(matches) != 1:
            raise RuntimeError(f"WORKFLOW_LIVE_NAME_COUNT:{name}:{len(matches)}")
        ids[name] = matches[0]["id"]
    updated = []
    for name in names:
        source = source_by_name[name]
        definition = json.loads(git_blob(commit, source["source_path"]))
        if not isinstance(definition.get("nodes"), list) or not isinstance(definition.get("connections"), dict):
            raise ValueError(f"WORKFLOW_SOURCE_INCOMPLETE:{name}")
        # PUT only the immutable export's deployable definition. No table or
        # credential endpoint is called, and no non-allowlisted workflow can be touched.
        status, response = api("PUT", "/api/v1/workflows/" + ids[name], definition)
        if status != 200:
            raise RuntimeError(f"WORKFLOW_UPDATE_FAILED:{name}:HTTP_{status}")
        status, _ = api("POST", "/api/v1/workflows/" + ids[name] + "/activate")
        if status not in (200, 201):
            raise RuntimeError(f"WORKFLOW_ACTIVATE_FAILED:{name}:HTTP_{status}")
        updated.append({"name": name, "id": ids[name], "active": True,
                        "response_id": response.get("id", ids[name])})
    return {"updated": updated, "updated_count": len(updated),
            "unrelated_updated_count": 0, "table_mutations": 0,
            "credential_mutations": 0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    parser.add_argument("--names", nargs="+", required=True)
    args = parser.parse_args()
    print(json.dumps(deploy(args.commit, args.names), sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, urllib.error.URLError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
