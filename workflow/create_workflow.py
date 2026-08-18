#!/usr/bin/env python3
"""Create the AutoDev Harness workflow via n8n Public API.

Usage: python3 create_workflow.py <workflow-json> [--activate]
API key read from file (never argv).
"""

import json
import sys
import urllib.request

BASE = "http://192.168.1.52:5678"
KEY_PATH = "/var/lib/n8n-spec-kit/secrets/ghiw-n8n-api-key"

with open(KEY_PATH) as f:
    KEY = f.read().strip()

wf_path = sys.argv[1]
with open(wf_path) as f:
    wf = json.load(f)

req = urllib.request.Request(
    BASE + "/api/v1/workflows",
    data=json.dumps(wf).encode(),
    headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=60) as r:
    created = json.loads(r.read().decode())

wid = created.get("id")
print("CREATED_ID", wid)
print("CREATED_NAME", created.get("name"))
print("NODE_COUNT", len(created.get("nodes", [])))
print("ACTIVE", created.get("active"))

# verify GET roundtrip
req = urllib.request.Request(
    BASE + "/api/v1/workflows/" + wid, headers={"X-N8N-API-KEY": KEY}
)
with urllib.request.urlopen(req, timeout=30) as r:
    back = json.loads(r.read().decode())
print("VERIFY_GET_NODES", len(back.get("nodes", [])))
print("VERIFY_GET_CONNS", len(back.get("connections", {})))
print("VERIFY_NAME", back.get("name"))

with open("/tmp/autodev-workflow-id.txt", "w") as f:
    f.write(wid)
