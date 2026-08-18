#!/usr/bin/env python3
"""AutoDev Harness v2 — n8n backup (read-only source).

Exports all workflows, active states, webhook registrations and credential
METADATA (names/types only — never values) from the n8n Public API.

Run on the Proxmox host (key file lives there):
    python3 backup_v2.py <outdir>

Never prints secrets. Credential values are never fetched.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

BASE = "http://192.168.1.52:5678"
KEY_PATH = "/var/lib/n8n-spec-kit/secrets/ghiw-n8n-api-key"


def api(path):
    with open(KEY_PATH) as f:
        key = f.read().strip()
    req = urllib.request.Request(BASE + path, headers={"X-N8N-API-KEY": key})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "backup"
    os.makedirs(os.path.join(outdir, "workflows"), exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    wfs = api("/api/v1/workflows?limit=250")["data"]
    print("WORKFLOW_TOTAL", len(wfs))

    manifest = []
    active = []
    webhooks = []
    for w in wfs:
        wid = w["id"]
        fn = os.path.join(outdir, "workflows", f"{wid}.json")
        with open(fn, "w") as f:
            json.dump(w, f, indent=2, ensure_ascii=False)
        manifest.append(
            {
                "id": wid,
                "name": w["name"],
                "active": w["active"],
                "nodes": len(w.get("nodes", [])),
                "file": f"{wid}.json",
            }
        )
        if w["active"]:
            active.append(
                {"id": wid, "name": w["name"], "nodes": len(w.get("nodes", []))}
            )
        for n in w.get("nodes", []):
            if n.get("type") == "n8n-nodes-base.webhook":
                webhooks.append(
                    {
                        "workflow": w["name"],
                        "workflow_id": wid,
                        "method": n.get("parameters", {}).get("httpMethod"),
                        "path": n.get("parameters", {}).get("path"),
                    }
                )

    # credentials: metadata only
    creds = api("/api/v1/credentials?limit=100")["data"]
    cred_meta = [{"id": c["id"], "name": c["name"], "type": c["type"]} for c in creds]

    summary = {
        "stamp": stamp,
        "workflow_total": len(wfs),
        "active_total": len(active),
        "active": active,
        "webhooks": webhooks,
        "credential_metadata_only": cred_meta,
    }
    with open(os.path.join(outdir, f"manifest-{stamp}.json"), "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print("MANIFEST", f"manifest-{stamp}.json")
    print("ACTIVE_TOTAL", len(active))
    for a in active:
        print("ACTIVE", a["id"], a["name"])
    print("WEBHOOK_TOTAL", len(webhooks))
    for w in webhooks:
        print("WEBHOOK", w["method"], w["path"], w["workflow_id"])
    print("CRED_TOTAL", len(cred_meta))
    for c in cred_meta:
        print("CRED", c["id"], c["name"], c["type"])


if __name__ == "__main__":
    main()
