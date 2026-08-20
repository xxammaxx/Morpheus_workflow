#!/usr/bin/env python3
"""HAMH adapter seam tests (AC-16, T4): the harness adapter accepts optional
provider/model/model_revision/task_class, resolves a harness at dispatch,
records harness fields, and stays fully backwards compatible.

Runs the ADAPTER CODE in-process with a temp state dir (no live pve service
touched). Backend routing and all existing behavior stay unchanged.

Run: python3 evidence/tests/hamh/test_adapter_hamh_seam.py
"""

import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

ADAPTER = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "adapter", "harness_adapter_v2.py"
)
RUNTIME = os.path.join(os.path.dirname(__file__), "..", "..", "..", "runtime")

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("PASS %s" % name)
    else:
        FAIL += 1
        print("FAIL %s %s" % (name, detail))


def main():
    state = tempfile.mkdtemp(prefix="hamh-adapter-")
    os.environ["AUTODEV_V2_STATE"] = state
    with open(os.path.join(state, "token"), "w") as f:
        f.write("test-token")
        os.chmod(os.path.join(state, "token"), 0o600)

    # pre-seed the HAMH registry with ONE ACTIVE deepseek plan harness so the
    # adapter->registry->resolver wiring is proven end-to-end (MAJOR-3 fix)
    os.makedirs(os.path.join(state, "hamh"), exist_ok=True)
    deepseek_active = {
        "contract": "hamh.harness.v1",
        "version": "v1",
        "harness_id": "deepseek/v4-flash/0731/auto/plan/v1",
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "model_revision": "0731",
        "task_class": "plan",
        "runtime_mode": "auto",
        "harness_version": "v1",
        "status": "ACTIVE",
        "fingerprint": "c" * 64,
        "prompt_profile": {"thinking": "auto"},
        "context_profile": {"stable_prefix": ["system"], "variable": ["task"]},
        "tool_profile": {"capabilities": {}, "presentation": "flat"},
        "created_at": "2026-08-20T00:00:00Z",
    }
    with open(os.path.join(state, "hamh", "registry.json"), "w") as f:
        json.dump(
            {
                "entries": {deepseek_active["harness_id"]: deepseek_active},
                "active_history": {},
            },
            f,
        )

    # import the adapter module (repo copy) with runtime/ on the path
    sys.path.insert(0, RUNTIME)
    import importlib.util

    spec = importlib.util.spec_from_file_location("harness_adapter_v2", ADAPTER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # --- _opencode_sem latent NameError is fixed (ADR H15)
    check(
        "AC16_OPENCODE_SEM_DEFINED",
        hasattr(mod, "_opencode_sem"),
    )

    # --- HAMH registry was loaded from STATE_DIR and consulted (MAJOR-3)
    check("AC16_HAMH_REGISTRY_LOADED", getattr(mod, "_hamh_registry", None) is not None)

    # --- opencode backend defaults are lmstudio/<model> (observability
    # consistency with the resolved identity; embedded stays embedded)
    rec_oc = mod.new_job(
        "dflt-run",
        "dflt-run:build:1",
        "build",
        "dflt-run:build:1",
        "autodev.issue.v1",
        {},
        "opencode-builder-8001",
    )
    check(
        "AC16_OPENCODE_DEFAULT_IDENTITY",
        rec_oc["provider"] == "lmstudio" and rec_oc["model"] == mod.LMSTUDIO_MODEL,
    )
    rec_em = mod.new_job(
        "dflt-run2",
        "dflt-run2:build:1",
        "build",
        "dflt-run2:build:1",
        "autodev.issue.v1",
        {},
        "embedded",
    )
    check(
        "AC16_EMBEDDED_DEFAULT_IDENTITY",
        rec_em["provider"] == "embedded" and rec_em["model"] == "embedded",
    )

    # --- backend routing unchanged (ROUTING_AUTHORITY)
    check(
        "ROUTING_BACKENDS_UNCHANGED",
        mod.VALID_BACKENDS == {"embedded", "opencode-builder-8001"},
    )

    # start the adapter HTTP server in-process on 127.0.0.1:<free port>
    srv = ThreadingHTTPServer(("127.0.0.1", 0), mod.Handler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    BASE = "http://127.0.0.1:%d" % port
    HDRS = {"X-Harness-Token": "test-token", "Content-Type": "application/json"}

    def post(path, body, expect=202):
        req = urllib.request.Request(
            BASE + path,
            data=json.dumps(body).encode(),
            headers=HDRS,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def get(path):
        req = urllib.request.Request(BASE + path, headers=HDRS)
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())

    issue = {
        "contract": "autodev.issue.v1",
        "version": "v1",
        "run_id": "hamh-seam-run1",
        "repository_ref": "repo",
        "workspace": "ws",
        "task_description": "hamh adapter seam test task",
        "trace_id": "t",
    }

    # 1. backward compatibility: dispatch WITHOUT provider/model (v2 style)
    body = {
        "run_id": "hamh-seam-run1",
        "job_id": "hamh-seam-run1:baseline:1",
        "job_type": "baseline",
        "attempt_id": "hamh-seam-run1:baseline:1",
        "input_contract": "autodev.issue.v1",
        "input": issue,
        "backend": "embedded",
    }
    st, resp = post("/v1/jobs", body)
    check(
        "SEAM_BACKCOMPAT_202",
        st == 202
        and resp.get("data", {}).get("status") in ("queued", "running", "completed"),
    )
    check(
        "SEAM_BACKCOMPAT_HARNESS_FALLBACK",
        resp.get("data", {}).get("harness", {}).get("is_fallback") is True,
    )

    # 2. dispatch WITH deepseek identity
    body2 = {
        "run_id": "hamh-seam-run2",
        "job_id": "hamh-seam-run2:plan:1",
        "job_type": "plan",
        "attempt_id": "hamh-seam-run2:plan:1",
        "input_contract": "autodev.issue.v1",
        "input": issue,
        "backend": "embedded",
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "model_revision": "0731",
        "task_class": "plan",
    }
    st, resp = post("/v1/jobs", body2)
    check("SEAM_DEEPSEEK_202", st == 202)
    h = resp.get("data", {}).get("harness", {})
    # the ACTIVE deepseek plan harness from the pre-seeded registry is used
    # (end-to-end proof: adapter -> registry -> resolver -> dispatch)
    check(
        "SEAM_HARNESS_RESOLVED",
        h.get("resolved_harness_id") == "deepseek/v4-flash/0731/auto/plan/v1",
        json.dumps(h),
    )
    check("SEAM_HARNESS_NOT_FALLBACK", h.get("is_fallback") is False)
    check("SEAM_HARNESS_FP_64", len(h.get("fingerprint", "")) == 64)

    # 3. invalid identity values rejected
    bad = dict(body2)
    bad["job_id"] = "hamh-seam-run2:plan:2"
    bad["attempt_id"] = "hamh-seam-run2:plan:2"
    bad["provider"] = "bad provider!"
    st, resp = post("/v1/jobs", bad, expect=400)
    check(
        "SEAM_BAD_PROVIDER_400",
        st == 400 and resp.get("error", {}).get("code") == "BAD_PROVIDER",
    )

    bad2 = dict(body2)
    bad2["job_id"] = "hamh-seam-run2:plan:3"
    bad2["attempt_id"] = "hamh-seam-run2:plan:3"
    bad2["task_class"] = "hacking"
    st, resp = post("/v1/jobs", bad2, expect=400)
    check(
        "SEAM_BAD_TASK_CLASS_400",
        st == 400 and resp.get("error", {}).get("code") == "BAD_TASK_CLASS",
    )

    # 4. job view carries provider/model + task_class
    import time

    time.sleep(1.5)  # let embedded jobs finish
    view = get("/v1/jobs/hamh-seam-run2:plan:1")
    d = view.get("data", {})
    check("SEAM_JOB_VIEW_PROVIDER", d.get("provider") == "deepseek")
    check("SEAM_JOB_VIEW_MODEL", d.get("model") == "deepseek-v4-flash")
    check("SEAM_JOB_VIEW_TASK_CLASS", d.get("task_class") == "plan")

    # 5. resolution artifact readable via the artifacts endpoint
    art = get("/v1/artifacts/hamh-seam-run2/hamh_resolution")
    check(
        "SEAM_RESOLUTION_ARTIFACT",
        art.get("data", {}).get("hamh-seam-run2:plan:1") is not None,
    )

    # 6. ledger contains harness metadata (parse state dir ledger)
    ledger_path = os.path.join(state, "logs", "runs.jsonl")
    with open(ledger_path) as f:
        lines = [json.loads(l) for l in f if l.strip()]
    plan_lines = [l for l in lines if l.get("job_id") == "hamh-seam-run2:plan:1"]
    check("SEAM_LEDGER_RECORDS", len(plan_lines) >= 2)  # queued + final
    check(
        "SEAM_LEDGER_HAS_TASK_CLASS",
        any(l.get("task_class") == "plan" for l in plan_lines),
    )

    # 7. idempotency preserved with identical dispatch
    st2, resp2 = post("/v1/jobs", body2)
    check(
        "SEAM_IDEMPOTENCY_KEPT",
        st2 == 202 and resp2.get("data", {}).get("job_id") == "hamh-seam-run2:plan:1",
    )

    srv.shutdown()
    print("\nRESULT %d passed, %d failed" % (PASS, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
