#!/usr/bin/env python3
"""Phase H: GHIW regression check — protected workflows unchanged, count 40->41."""

import json
import urllib.request

BASE = "http://192.168.1.52:5678"
KEY_PATH = "/var/lib/n8n-spec-kit/secrets/ghiw-n8n-api-key"

with open(KEY_PATH) as f:
    key = f.read().strip()


def api_get(path):
    req = urllib.request.Request(BASE + path, headers={"X-N8N-API-KEY": key})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


out = {}
wfs = api_get("/api/v1/workflows?limit=250")
items = wfs.get("data", [])
out["workflow_count_now"] = len(items)

protected = {
    "ghiw-10-issue-intake-firewall-auth": {
        "expect_active": True,
        "expect_nodes": 36,
        "expect_webhook": ["ghiw-e7-runtime-canary"],
    },
    "ghiw-blueprint-intake-dryrun": {
        "expect_active": False,
        "expect_nodes": 9,
        "expect_webhook": ["blueprint-intake"],
    },
    "ghiw-70-release-canary-orchestrator": {
        "expect_active": False,
        "expect_nodes": 4,
        "expect_webhook": [],
    },
    "n8n-ops-03-release-notes-docs": {
        "expect_active": False,
        "expect_nodes": 4,
        "expect_webhook": [],
    },
}

out["protected"] = {}
for wid, exp in protected.items():
    full = api_get("/api/v1/workflows/" + wid)
    webhooks = [
        (n.get("parameters") or {}).get("path")
        for n in full.get("nodes", [])
        if n.get("type") == "n8n-nodes-base.webhook"
    ]
    got = {
        "exists": True,
        "name": full.get("name"),
        "active": full.get("active"),
        "node_count": len(full.get("nodes", [])),
        "webhooks": webhooks,
    }
    ok = (
        got["active"] == exp["expect_active"]
        and got["node_count"] == exp["expect_nodes"]
        and sorted(got["webhooks"]) == sorted(exp["expect_webhook"])
    )
    got["ok"] = ok
    out["protected"][wid] = got

# credentials count (unchanged, only read)
try:
    creds = api_get("/api/v1/credentials?limit=250")
    out["credential_count"] = len(creds.get("data", []))
except Exception as e:
    out["credential_count"] = "error: %s" % e

# new workflow state
new = api_get("/api/v1/workflows/NdM7vcGvA4wkYswp")
out["new_workflow"] = {
    "id": new.get("id"),
    "name": new.get("name"),
    "active": new.get("active"),
    "node_count": len(new.get("nodes", [])),
    "webhooks": [
        (n.get("parameters") or {}).get("path")
        for n in new.get("nodes", [])
        if n.get("type") == "n8n-nodes-base.webhook"
    ],
}

print(json.dumps(out, indent=2))
all_protected_ok = all(v["ok"] for v in out["protected"].values())
print("PROTECTED_OK", all_protected_ok)
print(
    "COUNT_CHECK",
    "41" if out["workflow_count_now"] == 41 else str(out["workflow_count_now"]),
)
