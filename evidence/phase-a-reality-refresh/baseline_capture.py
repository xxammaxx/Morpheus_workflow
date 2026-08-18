#!/usr/bin/env python3
"""Phase A: n8n workflow baseline capture (read-only, no secrets in output)."""

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

# 1. health
out["healthz"] = api_get("/healthz")

# 2. all workflows (list)
wfs = api_get("/api/v1/workflows?limit=250")
items = wfs.get("data", [])
out["workflow_count"] = len(items)
out["workflows"] = [
    {
        "id": w.get("id"),
        "name": w.get("name"),
        "active": w.get("active"),
        "createdAt": w.get("createdAt"),
        "updatedAt": w.get("updatedAt"),
        "tags": [t.get("name") for t in (w.get("tags") or [])],
    }
    for w in items
]

# 3. detail for the 4 protected/relevant workflows (match by name)
interesting = ["GHIW-10", "Blueprint", "GHIW-70", "N8N-OPS-03", "AutoDev"]
details = []
for w in items:
    name = w.get("name") or ""
    if any(k.lower() in name.lower() for k in interesting):
        try:
            d = api_get("/api/v1/workflows/" + w["id"])
            details.append(
                {
                    "id": d.get("id"),
                    "name": d.get("name"),
                    "active": d.get("active"),
                    "createdAt": d.get("createdAt"),
                    "updatedAt": d.get("updatedAt"),
                    "node_count": len(d.get("nodes", [])),
                    "node_types": sorted(
                        {n.get("type", "?") for n in d.get("nodes", [])}
                    ),
                    "webhook_nodes": [
                        {
                            "name": n.get("name"),
                            "path": (n.get("parameters") or {}).get("path"),
                            "method": (n.get("parameters") or {}).get("httpMethod"),
                        }
                        for n in d.get("nodes", [])
                        if n.get("type") == "n8n-nodes-base.webhook"
                    ],
                    "tags": [t.get("name") for t in (d.get("tags") or [])],
                }
            )
        except Exception as e:
            details.append({"id": w["id"], "name": name, "error": str(e)})
out["relevant_workflow_details"] = details

# 4. executions endpoint shape (paginated stats)
try:
    ex = api_get("/api/v1/executions?limit=250")
    out["executions_first_page"] = {
        "count_on_page": len(ex.get("data", [])),
        "keys": list(ex.keys()),
        "nextCursor": ex.get("nextCursor"),
    }
    # iterate pages to count total + failures
    total = 0
    failed = 0
    cursor = None
    seen = set()
    while True:
        url = "/api/v1/executions?limit=250"
        if cursor:
            url += "&cursor=" + cursor
        page = api_get(url)
        data = page.get("data", [])
        for e in data:
            if e["id"] in seen:
                continue
            seen.add(e["id"])
            total += 1
            if e.get("status") not in ("success",):
                failed += 1
        cursor = page.get("nextCursor")
        if not cursor or not data:
            break
        if total > 5000:
            break
    out["execution_stats_from_api"] = {"total": total, "failed": failed}
except Exception as e:
    out["execution_stats_from_api"] = {"error": str(e)}

with open("/tmp/autodev-baseline.json", "w") as f:
    json.dump(out, f, indent=2)

print(
    json.dumps(
        {
            "healthz": out["healthz"],
            "workflow_count": out["workflow_count"],
            "execution_stats_from_api": out.get("execution_stats_from_api"),
        },
        indent=2,
    )
)
print("DETAILS_FILE=/tmp/autodev-baseline.json")
