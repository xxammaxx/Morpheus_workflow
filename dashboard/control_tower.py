#!/usr/bin/env python3
"""Morpheus Control Tower: authenticated, read-only operational projection."""
import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VERSION = "1.1.2"
ACTIVE_RUN_STATES = frozenset({"ACCEPTED", "BASELINING", "RESEARCHING", "PLANNING", "BUILDING", "VERIFYING", "REVIEWING", "DECIDING", "RUNNING", "ACTIVE"})
TERMINAL_FAILURE_STATES = frozenset({"FAILED", "BLOCKED"})
STALE_RUN_SECONDS = int(os.environ.get("CONTROL_TOWER_STALE_RUN_SECONDS", "1800"))
FREE_POOL_MINIMUM = 2
ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
STARTED = time.monotonic()
N8N_BASE = os.environ.get("MORPHEUS_N8N_BASE", "http://192.168.1.52:5678/api/v1").rstrip("/")
ADAPTER_BASE = os.environ.get("MORPHEUS_ADAPTER_BASE", "http://192.168.1.136:8081").rstrip("/")
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")
HARNESS_TOKEN = os.environ.get("HARNESS_TOKEN", "")
VIEWER_TOKEN = os.environ.get("CONTROL_TOWER_VIEW_TOKEN", "")
TABLE_IDS = {"runs": os.environ.get("MORPHEUS_RUNS_TABLE", ""), "attempts": os.environ.get("MORPHEUS_ATTEMPTS_TABLE", "")}
GOLDEN_RUN = "run-mt6unuge-agsdu4"
FAILURE_RUN = "run-mt6uony8-jjp9hf"
_table_lock = threading.Lock()


def read_credential(name):
    directory = os.environ.get("CREDENTIALS_DIRECTORY")
    if not directory:
        return ""
    try:
        return (Path(directory) / name).read_text().strip()
    except OSError:
        return ""


if not N8N_API_KEY:
    N8N_API_KEY = read_credential("n8n_api_key")
if not HARNESS_TOKEN:
    HARNESS_TOKEN = read_credential("harness_token")
if not VIEWER_TOKEN:
    VIEWER_TOKEN = read_credential("viewer_token")


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def safe_status(ok, checked=None):
    return {"status": "HEALTHY" if ok else "UNAVAILABLE", "checked_at": checked or now(), "freshness_seconds": 0}


def parse_timestamp(value):
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=dt.timezone.utc) if parsed.tzinfo is None else parsed.astimezone(dt.timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def classify_run_state(run):
    return str((run or {}).get("state", "UNKNOWN")).upper()


def is_active_run(run):
    return classify_run_state(run) in ACTIVE_RUN_STATES


def is_within_24h(timestamp, reference=None):
    parsed = parse_timestamp(timestamp)
    if parsed is None:
        return False
    reference = reference or dt.datetime.now(dt.timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=dt.timezone.utc)
    reference = reference.astimezone(dt.timezone.utc)
    return parsed >= reference - dt.timedelta(hours=24) and parsed <= reference


def terminal_timestamp(run):
    return (run or {}).get("ended_at") or (run or {}).get("updated_at")


def is_stale_run(run, threshold_seconds=STALE_RUN_SECONDS, reference=None):
    if not is_active_run(run):
        return False
    updated = parse_timestamp((run or {}).get("updated_at"))
    if updated is None:
        return False
    reference = reference or dt.datetime.now(dt.timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=dt.timezone.utc)
    return (reference.astimezone(dt.timezone.utc) - updated).total_seconds() > threshold_seconds


def build_run_counts(runs, reference=None):
    counts = {"running": 0, "waiting": 0, "done_24h": 0, "failed_24h": 0}
    for run in runs:
        state = classify_run_state(run)
        if state in ACTIVE_RUN_STATES:
            counts["running"] += 1
        elif state in ("WAITING", "QUEUED"):
            counts["waiting"] += 1
        elif state in ("DONE", "COMPLETED") and is_within_24h(terminal_timestamp(run), reference):
            counts["done_24h"] += 1
        elif state in TERMINAL_FAILURE_STATES and is_within_24h(terminal_timestamp(run), reference):
            counts["failed_24h"] += 1
    return counts


def sort_recent_runs(runs, limit=50):
    def key(run):
        parsed = parse_timestamp(run.get("updated_at"))
        return (parsed is not None, parsed or dt.datetime.min.replace(tzinfo=dt.timezone.utc))
    return sorted(runs, key=key, reverse=True)[:limit]


def provider_pool_status(size):
    return "HEALTHY" if size >= FREE_POOL_MINIMUM else "DEGRADED" if size == 1 else "UNAVAILABLE"


class Upstream:
    """Only GET requests are possible by construction."""
    def __init__(self, base, headers=None):
        self.base = base
        self.headers = headers or {}

    def get(self, path, query=None, timeout=4):
        url = self.base + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        request = urllib.request.Request(url, headers=self.headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError, urllib.error.HTTPError):
            return 0, None


def unwrap(payload):
    if isinstance(payload, dict):
        return payload.get("data", payload.get("items", payload))
    return payload


def list_items(payload):
    value = unwrap(payload)
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("data", "items", "results", "executions", "workflows", "rows"):
            if isinstance(value.get(key), list):
                return value[key]
    return []


def sanitize_run(row):
    if not isinstance(row, dict):
        return {}
    allowed = ("run_id", "state", "current_job", "decision", "reason_code", "created_at", "updated_at", "started_at", "ended_at", "job_id", "attempt_id", "job", "status", "result_ref", "task_ref", "repository_ref", "attempt_count", "failure_signature", "strategy_delta", "selected_provider", "selected_model", "resolved_model", "actual_provider", "actual_model", "cost_class", "actual_cost", "free_eligible", "fallback_chain", "paid_escalation", "harness_id", "harness_fingerprint")
    return {key: row.get(key) for key in allowed if key in row}


def table_rows(name):
    table_id = TABLE_IDS.get(name, "")
    if not table_id:
        status, payload = Upstream(N8N_BASE, {"X-N8N-API-KEY": N8N_API_KEY}).get("/data-tables", {"limit": 250})
        for item in list_items(payload) if status == 200 else []:
            if item.get("name") == "autodev_" + name:
                table_id = item.get("id", "")
                TABLE_IDS[name] = table_id
                break
    if not table_id:
        return [], False
    client = Upstream(N8N_BASE, {"X-N8N-API-KEY": N8N_API_KEY})
    rows, cursor = [], None
    for _ in range(20):
        query = {"limit": 250}
        if cursor:
            query["cursor"] = cursor
        status, payload = client.get("/data-tables/%s/rows" % table_id, query)
        if status != 200:
            return rows, False
        rows.extend(list_items(payload))
        cursor = payload.get("nextCursor") if isinstance(payload, dict) else None
        if not cursor:
            break
    return rows, True


def adapter_runtime():
    if not HARNESS_TOKEN:
        return {}, False
    status, payload = Upstream(ADAPTER_BASE, {"X-Harness-Token": HARNESS_TOKEN}).get("/v1/status/runtime")
    value = unwrap(payload)
    return (value if isinstance(value, dict) else {}, status == 200)


def adapter_health():
    status, payload = Upstream(ADAPTER_BASE).get("/healthz")
    return safe_status(status == 200)


def n8n_health():
    status, payload = Upstream(N8N_BASE, {"X-N8N-API-KEY": N8N_API_KEY}).get("/workflows", {"limit": 250})
    health = safe_status(status == 200)
    workflows = list_items(payload) if status == 200 else []
    canonical_prefixes = {"00", "01", "02", "10", "20", "30", "40", "50", "60", "70", "80", "90"}
    health["workflow_count"] = sum(1 for item in workflows if str(item.get("name", ""))[:2] in canonical_prefixes and str(item.get("name", ""))[2:3] == " ")
    return health


def timeline(attempts):
    events = []
    for item in attempts:
        item = sanitize_run(item)
        run_id = item.get("run_id")
        for kind, timestamp in (("ATTEMPT_STARTED", item.get("started_at")), ("ATTEMPT_FINISHED", item.get("ended_at"))):
            if timestamp:
                events.append({"contract": "autodev.timeline-event.v1", "version": "v1", "event": kind, "run_id": run_id, "timestamp": timestamp, "job_id": item.get("job_id"), "attempt_id": item.get("attempt_id"), "status": item.get("status"), "provider": item.get("actual_provider") or item.get("selected_provider"), "model": item.get("actual_model") or item.get("selected_model"), "failure_signature": item.get("failure_signature"), "strategy_delta": item.get("strategy_delta")})
    return sorted(events, key=lambda x: x.get("timestamp") or "")


def projection():
    runs, runs_ok = table_rows("runs")
    attempts, attempts_ok = table_rows("attempts")
    runtime, runtime_ok = adapter_runtime()
    health_n8n = n8n_health()
    health_adapter = adapter_health()
    clean_runs = [sanitize_run(x) for x in runs]
    recent = sort_recent_runs(clean_runs)
    pool = [p for p in runtime.get("providers", []) if p.get("free_eligible")]
    run_counts = build_run_counts(clean_runs)
    alerts = []
    if len(pool) < FREE_POOL_MINIMUM: alerts.append({"severity": "HIGH", "code": "FREE_POOL_BELOW_MIN", "message": "Free provider pool below two eligible providers"})
    if runtime.get("automatic_paid_agent_escalation"): alerts.append({"severity": "CRITICAL", "code": "PAID_ESCALATION_ENABLED", "message": "Automatic paid escalation enabled"})
    if health_n8n["status"] != "HEALTHY": alerts.append({"severity": "HIGH", "code": "N8N_UNAVAILABLE", "message": "n8n UNAVAILABLE"})
    if health_adapter["status"] != "HEALTHY": alerts.append({"severity": "HIGH", "code": "ADAPTER_UNAVAILABLE", "message": "Adapter UNAVAILABLE"})
    for run in clean_runs:
        if is_stale_run(run): alerts.append({"severity": "WARNING", "code": "STALE_ACTIVE_RUN", "message": "Active run has not been updated for a long time", "run_id": run.get("run_id")})
    return {"contract": "autodev.control-tower-overview.v1", "version": "v1", "generated_at": now(), "freshness": {"checked_at": now(), "freshness_seconds": 0}, "system_health": {"n8n": health_n8n, "adapter": health_adapter, "provider_pool": safe_status(runtime_ok and provider_pool_status(len(pool)) == "HEALTHY") | {"status": provider_pool_status(len(pool))}}, "free_pool": {"size": len(pool), "providers": pool}, "run_counts": run_counts, "recent_runs": recent, "alerts": alerts, "release": {"dashboard_version": VERSION, "core_v1_release": "v1.0.0", "morpheus_release": "v1.1.2", "dashboard_release": "v1.1.2", "v1_release": "v1.0.0", "n8n_autodev_workflows": health_n8n.get("workflow_count", 0), "free_first_active": bool(runtime.get("free_first_enabled")), "paid_escalation": bool(runtime.get("automatic_paid_agent_escalation")), "deepseek": "INELIGIBLE"}, "sources": {"n8n": "LIVE" if runs_ok and health_n8n["status"] == "HEALTHY" else "UNAVAILABLE", "adapter": "LIVE" if runtime_ok else "UNAVAILABLE"}}


def run_view(run_id):
    runs, _ = table_rows("runs")
    attempts, _ = table_rows("attempts")
    run = next((sanitize_run(x) for x in runs if sanitize_run(x).get("run_id") == run_id), {"run_id": run_id, "state": "UNKNOWN"})
    own = [sanitize_run(x) for x in attempts if sanitize_run(x).get("run_id") == run_id]
    run["attempts"] = own
    run["attempt_count"] = len(own)
    run["timeline"] = timeline(own)
    run["contract"] = "autodev.run-view.v1"
    run["version"] = "v1"
    return run


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *_): pass
    def headers_out(self):
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    def send_json(self, code, value):
        body = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(code); self.headers_out(); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def authorized(self):
        return bool(VIEWER_TOKEN) and hmac.compare_digest(self.headers.get("X-Control-Tower-Token", ""), VIEWER_TOKEN)
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/healthz":
            return self.send_json(200, {"status": "ok", "version": VERSION, "uptime_seconds": round(time.monotonic() - STARTED, 1)})
        if path.startswith("/static/") or path == "/":
            if path == "/": path = "/static/index.html"
            target = (ROOT / path.lstrip("/")).resolve()
            if ROOT not in target.parents or not target.is_file(): return self.send_json(404, {"error": "not found"})
            body = target.read_bytes(); self.send_response(200); self.headers_out(); self.send_header("Content-Type", "text/html; charset=utf-8" if target.suffix == ".html" else "text/javascript; charset=utf-8" if target.suffix == ".js" else "text/css; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if not self.authorized(): return self.send_json(401, {"error": "unauthorized"})
        if self.command != "GET": return self.send_json(405, {"error": "method not allowed"})
        if path == "/api/v1/overview": return self.send_json(200, projection())
        if path == "/api/v1/runs":
            runs, _ = table_rows("runs"); return self.send_json(200, {"contract": "autodev.run-view.v1", "version": "v1", "runs": [sanitize_run(x) for x in runs]})
        if path.startswith("/api/v1/runs/") and path.endswith("/timeline"):
            run_id = urllib.parse.unquote(path[len("/api/v1/runs/"):-len("/timeline")]); view = run_view(run_id); return self.send_json(200, {"contract": "autodev.timeline-event.v1", "version": "v1", "run_id": run_id, "events": view["timeline"]})
        if path.startswith("/api/v1/runs/"):
            return self.send_json(200, run_view(urllib.parse.unquote(path[len("/api/v1/runs/"):])) )
        if path in ("/api/v1/providers", "/api/v1/runtime"):
            runtime, ok = adapter_runtime(); return self.send_json(200 if ok else 503, {"contract": "autodev.runtime-health.v1", "version": "v1", "source": "LIVE" if ok else "UNAVAILABLE", **runtime})
        return self.send_json(404, {"error": "not found"})
    def do_POST(self): self.send_json(405, {"error": "method not allowed"})
    do_PUT = do_POST; do_PATCH = do_POST; do_DELETE = do_POST


def main():
    bind = os.environ.get("CONTROL_TOWER_BIND", "192.168.1.136")
    port = int(os.environ.get("CONTROL_TOWER_PORT", "8090"))
    ThreadingHTTPServer((bind, port), Handler).serve_forever()


if __name__ == "__main__": main()
