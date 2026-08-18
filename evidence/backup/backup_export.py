#!/usr/bin/env python3
"""Phase B: Full backup export of protected workflows + all workflow metadata."""

import json
import urllib.request

BASE = "http://192.168.1.52:5678"
KEY_PATH = "/var/lib/n8n-spec-kit/secrets/ghiw-n8n-api-key"

with open(KEY_PATH) as f:
    key = f.read().strip()


def api_get(path):
    req = urllib.request.Request(BASE + path, headers={"X-N8N-API-KEY": key})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


PROTECTED_IDS = [
    "ghiw-10-issue-intake-firewall-auth",
    "ghiw-blueprint-intake-dryrun",
    "ghiw-70-release-canary-orchestrator",
    "n8n-ops-03-release-notes-docs",
]

bundle = {"captured_at": None, "workflows": {}}

wfs = api_get("/api/v1/workflows?limit=250")
bundle["workflow_list"] = wfs.get("data", [])

import datetime

bundle["captured_at"] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

for wid in PROTECTED_IDS:
    full = api_get("/api/v1/workflows/" + wid)
    bundle["workflows"][wid] = full

with open("/tmp/autodev-backup-protected.json", "w") as f:
    json.dump(bundle, f, indent=2)

print("OK", {k: bool(v) for k, v in bundle["workflows"].items()})
print("FULL_LIST_LEN", len(bundle["workflow_list"]))
