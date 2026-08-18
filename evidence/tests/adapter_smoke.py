#!/usr/bin/env python3
"""Phase C: Adapter smoke tests — every endpoint, one happy-path request."""

import json
import urllib.request

BASE = "http://192.168.1.136:8080"
with open("/var/lib/autodev-harness/token") as f:
    TOKEN = f.read().strip()

RUN = "smoke-%d" % (__import__("time").time())


def post(path, payload):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-Harness-Token": TOKEN},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status, json.loads(r.read().decode())


results = {}
base = {
    "run_id": RUN,
    "task": "smoke: greet canary",
    "repository": "local-canary/greeter",
    "max_attempts": 2,
    "execution_backend": "embedded",
}

for path in [
    "/baseline",
    "/research/code",
    "/research/docs",
    "/research/tests",
    "/plan",
    "/build",
    "/verify",
    "/fix",
    "/review/correctness",
    "/review/security",
    "/review/quality",
]:
    try:
        code, body = post(path, base)
        ok = code == 200 and body.get("status") != "error"
        results[path] = {"http": code, "contract": body.get("contract"), "ok": ok}
        if not ok:
            results[path]["error"] = body.get("error")
    except Exception as e:
        results[path] = {"ok": False, "error": str(e)}

# verify should reference the build contract fields
code, verify_body = post("/verify", base)
results["/verify"]["passed_field"] = verify_body.get("verification", {}).get("passed")

# auth check: no token -> 401
req = urllib.request.Request(
    BASE + "/baseline",
    data=b"{}",
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    urllib.request.urlopen(req, timeout=30)
    results["auth_without_token"] = {"ok": False, "error": "no 401 raised"}
except urllib.error.HTTPError as e:
    results["auth_without_token"] = {"ok": e.code == 401, "http": e.code}

print(json.dumps(results, indent=2))
all_ok = all(v.get("ok") for k, v in results.items())
print("ALL_SMOKE_PASS", all_ok)
