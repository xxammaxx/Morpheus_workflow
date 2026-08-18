#!/usr/bin/env python3
"""AutoDev Harness v2 — Adapter test suite (execution plane).

Run from the workstation:
    python3 adapter_suite.py

Covers: healthz, auth, dispatch, idempotency, contract boundary, fixtures
(negative paths), timeout, malformed response, duplicate callback,
batch parallelism, artifacts, restart recovery.

Evidence is written to ./adapter-suite-result.txt
"""

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

BASE = "http://192.168.1.136:8081"
TOKEN_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "..",
    "..",
    ".secrets",
    "harness_token_v2",
)

RESULTS = []


def record(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print("%s %s %s" % ("PASS" if ok else "FAIL", name, detail))


def get(path, token=None):
    req = urllib.request.Request(BASE + path, headers={"X-Harness-Token": token or ""})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def post(path, body, token=None, expect_status=None):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"X-Harness-Token": token or "", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode())
            status = r.status
    except urllib.error.HTTPError as e:
        try:
            data = json.loads(e.read().decode())
        except Exception:
            data = {}
        status = e.code
    if expect_status is not None:
        return data, status
    return data, status


def wait_job(job_id, token, timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            d = get("/v1/jobs/" + urllib.parse.quote(job_id, safe=""), token)["data"]
        except Exception:
            time.sleep(1)
            continue
        if d.get("status") in ("completed", "failed", "interrupted"):
            return d
        time.sleep(0.5)
    return get("/v1/jobs/" + urllib.parse.quote(job_id, safe=""), token)["data"]


def wait_batch(batch_id, token, timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            b = get("/v1/batches/" + urllib.parse.quote(batch_id, safe=""), token)[
                "data"
            ]
        except Exception:
            time.sleep(1)
            continue
        if b.get("status") in ("completed", "interrupted"):
            return b
        time.sleep(0.5)
    return get("/v1/batches/" + urllib.parse.quote(batch_id, safe=""), token)["data"]


def issue(run_id, extra=None):
    d = {
        "contract": "autodev.issue.v1",
        "version": "v1",
        "run_id": run_id,
        "repository_ref": "adapter-suite",
        "workspace": "suite",
        "task_description": "Adapter test suite canary task with enough length",
    }
    if extra:
        d.update(extra)
    return d


# ------------------------------------------------------------------ tests --
class CallbackSink(BaseHTTPRequestHandler):
    received = []
    lock = threading.Lock()

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length).decode()) if length else {}
        with CallbackSink.lock:
            CallbackSink.received.append(body)
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


def main():
    import urllib.parse

    token = open(TOKEN_FILE).read().strip()
    assert token, "token missing"

    # --- healthz + auth
    h = get("/healthz")
    record("HEALTHZ", h.get("data", {}).get("status") == "ok")
    _, s1 = post("/v1/jobs", {}, token=None, expect_status=401)
    record("AUTH_NO_TOKEN_401", s1 == 401)
    _, s2 = post("/v1/jobs", {}, token="wrong", expect_status=401)
    record("AUTH_WRONG_TOKEN_401", s2 == 401)

    # --- job dispatch + result
    run = "suite-%d" % int(time.time())
    d, st = post(
        "/v1/jobs",
        {
            "run_id": run,
            "job_id": run + ":baseline:1",
            "job_type": "baseline",
            "attempt_id": run + ":baseline:1",
            "input_contract": "autodev.issue.v1",
            "input": issue(run),
            "backend": "embedded",
        },
        token,
        expect_status=202,
    )
    record(
        "JOB_DISPATCH_202",
        st == 202 and d.get("data", {}).get("job_id") == run + ":baseline:1",
    )
    j = wait_job(run + ":baseline:1", token)
    record("JOB_COMPLETES", j.get("status") == "completed")
    record("JOB_CONTRACT_OUT", j.get("output_contract") == "autodev.baseline.v1")
    record(
        "JOB_FINGERPRINTS",
        bool(j.get("input_fingerprint")) and bool(j.get("output_fingerprint")),
    )

    # --- contract boundary: invalid input
    bad = dict(issue(run), run_id="x")
    _, st = post(
        "/v1/jobs",
        {
            "run_id": run,
            "job_id": run + ":bad:1",
            "job_type": "baseline",
            "attempt_id": run + ":bad:1",
            "input_contract": "autodev.issue.v1",
            "input": bad,
            "backend": "embedded",
        },
        token,
        expect_status=400,
    )
    record("CONTRACT_BOUNDARY_400", st == 400)
    _, st = post(
        "/v1/jobs",
        {
            "run_id": run,
            "job_id": run + ":bad2:1",
            "job_type": "baseline",
            "attempt_id": run + ":bad2:1",
            "input_contract": "autodev.unknown.v9",
            "input": issue(run),
            "backend": "embedded",
        },
        token,
        expect_status=400,
    )
    record("UNKNOWN_CONTRACT_400", st == 400)

    # --- idempotent dispatch
    body = {
        "run_id": run,
        "job_id": run + ":idem:1",
        "job_type": "research.code",
        "attempt_id": run + ":idem:1",
        "input_contract": "autodev.issue.v1",
        "input": issue(run),
        "backend": "embedded",
        "sleep_seconds": 2,
    }
    d1, _ = post("/v1/jobs", body, token, expect_status=202)
    jid1 = d1.get("data", {}).get("job_id")
    time.sleep(0.3)
    d2, st = post("/v1/jobs", body, token)
    jid2 = d2.get("data", {}).get("job_id")
    j = wait_job(run + ":idem:1", token)
    record("IDEMPOTENT_DISPATCH", jid1 == jid2 and j.get("status") == "completed")
    # same job_id, different payload -> conflict
    body2 = dict(body, input=issue(run, extra={"acceptance_hint": "different"}))
    _, st = post("/v1/jobs", body2, token, expect_status=400)
    record("IDEMPOTENCY_CONFLICT_400", st == 400)

    # --- fixtures (unique run_id per fixture so fail-once semantics stay isolated)
    fixtures = {
        "verify_fail_delta": ("verify", "TEST_FAILURE"),
        "verify_fail_no_delta": ("verify", "TEST_FAILURE"),
        "no_signature": ("verify", "TEST_FAILURE"),
        "security_critical_blocking": ("review.security", None),
    }
    for fx, (jtype, fclass) in fixtures.items():
        fx_run = "suitefx-%d-%s" % (int(time.time()), fx)
        d, _ = post(
            "/v1/jobs",
            {
                "run_id": fx_run,
                "job_id": "%s:%s:1" % (fx_run, fx),
                "job_type": jtype,
                "attempt_id": "%s:%s:1" % (fx_run, fx),
                "input_contract": "autodev.issue.v1",
                "input": issue(fx_run),
                "backend": "embedded",
                "fixture": fx,
            },
            token,
        )
        j = wait_job("%s:%s:1" % (fx_run, fx), token)
        res = j.get("result") or {}
        if fx == "verify_fail_delta":
            record(
                "FIXTURE_VERIFY_FAIL_DELTA",
                j["status"] == "completed"
                and res.get("passed") is False
                and res.get("failure_signature")
                and res.get("new_evidence"),
            )
        elif fx == "verify_fail_no_delta":
            record(
                "FIXTURE_VERIFY_FAIL_NO_DELTA",
                j["status"] == "completed"
                and res.get("passed") is False
                and res.get("failure_signature")
                and not res.get("new_evidence"),
            )
        elif fx == "no_signature":
            record(
                "FIXTURE_VERIFY_NO_SIGNATURE",
                j["status"] == "completed"
                and res.get("passed") is False
                and res.get("failure_signature") is None,
            )
        elif fx == "security_critical_blocking":
            rec = j.get("result") or {}
            findings = []
            for rv in rec.get("reviews", []):
                findings.extend(rv.get("findings", []))
            record(
                "FIXTURE_SECURITY_CRITICAL",
                j["status"] == "completed"
                and rec.get("blocked") is True
                and any(
                    f.get("severity") == "CRITICAL" and f.get("blocking")
                    for f in findings
                ),
            )

    # review fixtures (unique run_id each)
    for fx in ("review_fix", "review_split"):
        fx_run = "suitefx-%d-%s" % (int(time.time()), fx)
        d, _ = post(
            "/v1/jobs",
            {
                "run_id": fx_run,
                "job_id": "%s:%s:1" % (fx_run, fx),
                "job_type": "review.quality",
                "attempt_id": "%s:%s:1" % (fx_run, fx),
                "input_contract": "autodev.issue.v1",
                "input": issue(fx_run),
                "backend": "embedded",
                "fixture": fx,
            },
            token,
        )
        j = wait_job("%s:%s:1" % (fx_run, fx), token)
        res = j.get("result") or {}
        recs = res.get("reviews") or []
        findings = [f for rv in recs for f in rv.get("findings", [])]
        record("FIXTURE_%s" % fx.upper(), j["status"] == "completed" and bool(findings))

    # invalid_plan fixture: schema-valid plan with mismatched run_id (gate rejects)
    d, _ = post(
        "/v1/jobs",
        {
            "run_id": fx_run,
            "job_id": "%s:invalid_plan:1" % fx_run,
            "job_type": "plan",
            "attempt_id": "%s:invalid_plan:1" % fx_run,
            "input_contract": "autodev.issue.v1",
            "input": issue(fx_run),
            "backend": "embedded",
            "fixture": "invalid_plan",
        },
        token,
    )
    j = wait_job("%s:invalid_plan:1" % fx_run, token)
    res = j.get("result") or {}
    record(
        "FIXTURE_INVALID_PLAN",
        j["status"] == "completed"
        and res.get("contract") == "autodev.plan.v1"
        and res.get("run_id") != fx_run,
    )

    # --- timeout
    d, _ = post(
        "/v1/jobs",
        {
            "run_id": fx_run,
            "job_id": "%s:timeout:1" % fx_run,
            "job_type": "research.code",
            "attempt_id": "%s:timeout:1" % fx_run,
            "input_contract": "autodev.issue.v1",
            "input": issue(fx_run),
            "backend": "embedded",
            "fixture": "adapter_timeout",
            "timeout_s": 2,
        },
        token,
    )
    j = wait_job("%s:timeout:1" % fx_run, token, timeout=15)
    record(
        "ADAPTER_TIMEOUT_CLASS",
        j.get("status") == "failed" and j.get("failure_class") == "TIMEOUT",
        json.dumps(j)[:200],
    )

    # --- malformed response
    d, _ = post(
        "/v1/jobs",
        {
            "run_id": fx_run,
            "job_id": "%s:malformed:1" % fx_run,
            "job_type": "plan",
            "attempt_id": "%s:malformed:1" % fx_run,
            "input_contract": "autodev.issue.v1",
            "input": issue(fx_run),
            "backend": "embedded",
            "fixture": "malformed_response",
        },
        token,
    )
    j = wait_job("%s:malformed:1" % fx_run, token)
    record(
        "MALFORMED_RESPONSE_CLASS",
        j.get("status") == "failed" and j.get("failure_class") == "CONTRACT_FAILURE",
    )

    # --- batch parallelism (controlled)
    par = "parsuite-%d" % int(time.time())
    jobs = []
    for jt in ("research.code", "research.docs", "research.tests"):
        jobs.append(
            {
                "job_id": "%s:%s:1" % (par, jt),
                "job_type": jt,
                "attempt_id": "%s:%s:1" % (par, jt),
                "input_contract": "autodev.issue.v1",
                "input": issue(par),
                "backend": "embedded",
                "sleep_seconds": 3,
            }
        )
    d, _ = post(
        "/v1/batches", {"run_id": par, "batch_id": par + ":b1", "jobs": jobs}, token
    )
    record("BATCH_DISPATCH", len(d.get("data", {}).get("errors", [])) == 0)
    b = wait_batch(par + ":b1", token, timeout=20)
    record("BATCH_BARRIER", b.get("status") == "completed")
    spans = []
    for j in b.get("jobs", []):
        try:
            st_ = time.mktime(time.strptime(j["started_at"], "%Y-%m-%dT%H:%M:%SZ"))
            en_ = time.mktime(time.strptime(j["ended_at"], "%Y-%m-%dT%H:%M:%SZ"))
            spans.append((st_, en_))
        except (TypeError, ValueError):
            pass
    overlaps = sum(
        1
        for i in range(len(spans))
        for k in range(i + 1, len(spans))
        if spans[i][0] < spans[k][1] and spans[k][0] < spans[i][1]
    )
    record("BATCH_PARALLELISM_OVERLAP", overlaps >= 1, "overlaps=%d" % overlaps)

    # --- duplicate callback
    sink = HTTPServer(("192.168.1.195", 18091), CallbackSink)
    threading.Thread(target=sink.serve_forever, daemon=True).start()
    CallbackSink.received = []
    cb_run = "cb-%d" % int(time.time())
    post(
        "/v1/jobs",
        {
            "run_id": cb_run,
            "job_id": cb_run + ":baseline:1",
            "job_type": "baseline",
            "attempt_id": cb_run + ":baseline:1",
            "input_contract": "autodev.issue.v1",
            "input": issue(cb_run),
            "backend": "embedded",
            "resume_url": "http://192.168.1.195:18091/cb",
        },
        token,
    )
    time.sleep(2)
    first = list(CallbackSink.received)
    time.sleep(1)
    second = list(CallbackSink.received)
    record(
        "CALLBACK_DELIVERED",
        len(first) == 1 and first[0].get("job_id") == cb_run + ":baseline:1",
        json.dumps(first)[:200],
    )
    record("CALLBACK_DEDUPED", len(second) == 1)
    sink.shutdown()

    # --- artifacts
    ar = "art-%d" % int(time.time())
    d, st = post(
        "/v1/artifacts/%s/split" % ar,
        {
            "artifact": {
                "contract": "autodev.split.v1",
                "parent_run_id": ar,
                "subtasks": [],
            }
        },
        token,
        expect_status=201,
    )
    record("ARTIFACT_POST", st == 201 and bool(d.get("data", {}).get("ref")))
    got = get("/v1/artifacts/%s/split" % ar, token)
    record(
        "ARTIFACT_GET",
        got.get("data", {}).get("contract") == "autodev.split.v1",
    )

    # --- restart recovery (completed job survives; in-flight becomes interrupted)
    rec_run = "rec-%d" % int(time.time())
    post(
        "/v1/jobs",
        {
            "run_id": rec_run,
            "job_id": rec_run + ":baseline:1",
            "job_type": "baseline",
            "attempt_id": rec_run + ":baseline:1",
            "input_contract": "autodev.issue.v1",
            "input": issue(rec_run),
            "backend": "embedded",
        },
        token,
    )
    wait_job(rec_run + ":baseline:1", token)
    post(
        "/v1/jobs",
        {
            "run_id": rec_run,
            "job_id": rec_run + ":inflight:1",
            "job_type": "research.code",
            "attempt_id": rec_run + ":inflight:1",
            "input_contract": "autodev.issue.v1",
            "input": issue(rec_run),
            "backend": "embedded",
            "sleep_seconds": 30,
        },
        token,
    )
    time.sleep(1)
    subprocess.run(
        ["ssh", "192.168.1.136", "systemctl restart autodev-harness-v2"],
        capture_output=True,
        timeout=60,
    )
    time.sleep(3)
    done = wait_job(rec_run + ":baseline:1", token, timeout=15)
    record("RECOVERY_COMPLETED_SURVIVES", done.get("status") == "completed")
    inflight = wait_job(rec_run + ":inflight:1", token, timeout=15)
    record(
        "RECOVERY_INFLIGHT_INTERRUPTED",
        inflight.get("status") == "interrupted"
        and inflight.get("failure_class") == "INFRA_FAILURE",
        json.dumps(inflight)[:200],
    )
    # completed job must not be re-run: same dispatch returns existing completed
    d, st = post(
        "/v1/jobs",
        {
            "run_id": rec_run,
            "job_id": rec_run + ":baseline:1",
            "job_type": "baseline",
            "attempt_id": rec_run + ":baseline:1",
            "input_contract": "autodev.issue.v1",
            "input": issue(rec_run),
            "backend": "embedded",
        },
        token,
    )
    record("RECOVERY_NO_RERUN", d.get("data", {}).get("status") == "completed")

    # --- summary
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = len(RESULTS) - passed
    out = "ADAPTER_SUITE_RESULT %d passed, %d failed\n" % (passed, failed)
    for name, ok, detail in RESULTS:
        out += (
            ("PASS " if ok else "FAIL ")
            + name
            + (" " + detail if detail else "")
            + "\n"
        )
    with open(
        os.path.join(os.path.dirname(__file__), "adapter-suite-result.txt"), "w"
    ) as f:
        f.write(out)
    print("\nRESULT %d passed, %d failed" % (passed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
