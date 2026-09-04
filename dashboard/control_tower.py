#!/usr/bin/env python3
"""Morpheus Control Tower BFF: read projections plus audited n8n commands."""
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

from control_center import (ADMIN_COMMANDS, COMMAND_PATHS, OPERATOR_COMMANDS,
                            READ_ROLES, audit_entry, blueprint_projection,
                            correlation_id,
                            project_projection, redact, role_for_token,
                            validate_command, validate_target)
from telemetry import runtime_telemetry

VERSION = "1.2.0"
ACTIVE_RUN_STATES = frozenset({"ACCEPTED", "BASELINING", "RESEARCHING", "PLANNING", "BUILDING", "VERIFYING", "REVIEWING", "DECIDING", "RUNNING", "ACTIVE"})
TERMINAL_FAILURE_STATES = frozenset({"FAILED", "BLOCKED"})
STALE_RUN_SECONDS = int(os.environ.get("CONTROL_TOWER_STALE_RUN_SECONDS", "1800"))
FREE_POOL_MINIMUM = 1
ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
STARTED = time.monotonic()
N8N_BASE = os.environ.get("MORPHEUS_N8N_BASE", "http://192.168.1.52:5678/api/v1").rstrip("/")
ADAPTER_BASE = os.environ.get("MORPHEUS_ADAPTER_BASE", "http://192.168.1.136:8081").rstrip("/")
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")
HARNESS_TOKEN = os.environ.get("HARNESS_TOKEN", "")
VIEWER_TOKEN = os.environ.get("CONTROL_TOWER_VIEW_TOKEN", "")
TABLE_IDS = {"runs": os.environ.get("MORPHEUS_RUNS_TABLE", ""), "attempts": os.environ.get("MORPHEUS_ATTEMPTS_TABLE", "")}
TABLE_IDS.update({"projects": os.environ.get("MORPHEUS_PROJECTS_TABLE", ""), "issues": os.environ.get("MORPHEUS_ISSUES_TABLE", ""), "events": os.environ.get("MORPHEUS_EVENTS_TABLE", "")})
OPERATOR_TOKEN = os.environ.get("CONTROL_TOWER_OPERATOR_TOKEN", "")
ADMIN_TOKEN = os.environ.get("CONTROL_TOWER_ADMIN_TOKEN", "")
COMMAND_TOKEN = os.environ.get("MORPHEUS_COMMAND_TOKEN", "")
COMMAND_BASE = os.environ.get("MORPHEUS_COMMAND_BASE", "").rstrip("/")
if not COMMAND_BASE:
    COMMAND_BASE = N8N_BASE.rsplit("/api/v1", 1)[0]
COMMAND_TIMEOUT = float(os.environ.get("CONTROL_TOWER_COMMAND_TIMEOUT", "8"))
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
if not OPERATOR_TOKEN:
    OPERATOR_TOKEN = read_credential("operator_token")
if not ADMIN_TOKEN:
    ADMIN_TOKEN = read_credential("admin_token")
if not COMMAND_TOKEN:
    COMMAND_TOKEN = read_credential("command_token")


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def re_correlation_id(value):
    return isinstance(value, str) and 3 <= len(value) <= 96 and all(char.isalnum() or char in "_-:." for char in value)


def safe_status(ok, checked=None):
    return {
        "status": "HEALTHY" if ok else "UNAVAILABLE",
        "diagnostic_status": "OK" if ok else "NICHT_OK",
        "role": "REQUIRED",
        "checked_at": checked or now(),
        "freshness_seconds": 0,
    }


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


def operational_provider_pool(runtime, runtime_ok):
    """Project the canonical routable pool; unavailable data is not an empty pool."""
    if not runtime_ok or not isinstance(runtime, dict):
        return []
    return [provider for provider in runtime.get("providers", [])
            if isinstance(provider, dict) and provider.get("router_eligible") is True]


class Upstream:
    """Read-only upstream client; writes use command_post's fixed n8n path."""
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
        for key in ("data", "items", "results", "executions", "workflows", "rows", "events"):
            if isinstance(value.get(key), list):
                return value[key]
    return []


def sanitize_run(row):
    if not isinstance(row, dict):
        return {}
    allowed = ("run_id", "project_id", "issue_number", "state", "current_job", "decision", "reason_code", "created_at", "updated_at", "started_at", "ended_at", "job_id", "attempt_id", "job", "status", "result_ref", "task_ref", "repository_ref", "attempt_count", "failure_signature", "strategy_delta", "selected_provider", "selected_model", "resolved_model", "actual_provider", "actual_model", "cost_class", "actual_cost", "free_eligible", "fallback_chain", "paid_escalation", "harness_id", "harness_fingerprint", "input_contract", "output_contract", "payload", "source", "target", "worker_id", "mcp_call_id", "routing_event_id", "correlation_id", "contract", "validation", "backend", "runtime_backend", "runtime_guest_id", "runtime_guest", "runtime_guests", "usage", "source_run_id", "created_via", "continuation_reason", "requested_action", "requested_by", "trace_id", "adaptive_metadata", "experiment_id", "benchmark_task_id", "benchmark_split", "candidate_id", "factor", "context_policy", "repo_explorer_policy", "experience_policy", "config_hash", "task_set_hash", "harness_version", "last_action")
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


def adapter_events():
    if not HARNESS_TOKEN:
        return [], False
    status, payload = Upstream(ADAPTER_BASE, {"X-Harness-Token": HARNESS_TOKEN}).get("/v1/events", {"limit": 250})
    return (list_items(payload), status == 200)


def command_post(path, body):
    """The only mutating upstream path: an allow-listed n8n webhook."""
    url = COMMAND_BASE + path if path.startswith("/") else COMMAND_BASE + "/" + path
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if COMMAND_TOKEN:
        headers["X-AutoDev-Token"] = COMMAND_TOKEN
    if N8N_API_KEY:
        headers["X-N8N-API-KEY"] = N8N_API_KEY
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=COMMAND_TIMEOUT) as response:
            value = json.loads(response.read().decode("utf-8"))
            return response.status, value if isinstance(value, dict) else {"data": value}
    except (OSError, ValueError, urllib.error.HTTPError) as exc:
        return 502, {"error": "canonical command unavailable", "error_class": type(exc).__name__}


def n8n_health():
    status, payload = Upstream(N8N_BASE, {"X-N8N-API-KEY": N8N_API_KEY}).get("/workflows", {"limit": 250})
    health = safe_status(status == 200)
    workflows = list_items(payload) if status == 200 else []
    canonical_prefixes = {"00", "01", "02", "05", "06", "07", "08", "10", "20", "30", "40", "50", "60", "70", "80", "90"}
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


def debugging_events(run_id=None):
    attempts, attempts_ok = table_rows("attempts")
    canonical_events, events_ok = table_rows("events")
    external, external_ok = adapter_events()
    events = []
    for item in attempts:
        row = sanitize_run(item)
        if run_id and row.get("run_id") != run_id:
            continue
        for event_name, timestamp, status in (("ATTEMPT_STARTED", row.get("started_at"), "RUNNING"), ("ATTEMPT_FINISHED", row.get("ended_at"), row.get("status", "UNKNOWN"))):
            if timestamp:
                events.append({"timestamp": timestamp, "source": row.get("source") or "n8n", "target": row.get("target") or "UNKNOWN", "event": event_name,
                               "run_id": row.get("run_id"), "attempt_id": row.get("attempt_id"), "status": status,
                               "correlation_id": row.get("correlation_id") or "UNKNOWN",
                               "contract": row.get("contract") or row.get("output_contract") or row.get("input_contract") or "UNKNOWN",
                               "validation": row.get("validation") or "UNKNOWN",
                               "provider": row.get("actual_provider") or row.get("selected_provider"),
                               "model": row.get("actual_model") or row.get("selected_model"),
                               "payload": {"job_id": row.get("job_id"), "result_ref": row.get("result_ref")}})
    for event in canonical_events + external:
        if not isinstance(event, dict) or (run_id and event.get("run_id") != run_id):
            continue
        clean = redact(event)
        clean.setdefault("source", "UNKNOWN")
        clean.setdefault("target", "UNKNOWN")
        clean.setdefault("run_id", "UNKNOWN")
        clean.setdefault("attempt_id", "UNKNOWN")
        clean.setdefault("correlation_id", "UNKNOWN")
        clean.setdefault("contract", "UNKNOWN")
        clean.setdefault("validation", "UNKNOWN")
        clean.setdefault("timestamp", clean.get("ts") or clean.get("created_at"))
        events.append(clean)
    events = [redact(e) for e in events if e.get("timestamp")]
    # Reachable event sources are not evidence of a live flow.  The caller
    # must only label the stream LIVE when at least one correlated event was
    # actually observed for the requested run.
    return sorted(events, key=lambda x: x.get("timestamp") or ""), bool(events)


def telemetry_projection():
    runs, _ = table_rows("runs")
    active = choose_active_run([sanitize_run(x) for x in runs])
    events, _ = debugging_events(active.get("run_id") if active else None)
    return runtime_telemetry(active or {}, events)


def projection():
    runs, runs_ok = table_rows("runs")
    attempts, attempts_ok = table_rows("attempts")
    projects, projects_ok = table_rows("projects")
    issues, issues_ok = table_rows("issues")
    runtime, runtime_ok = adapter_runtime()
    health_n8n = n8n_health()
    health_adapter = adapter_health()
    clean_runs = [sanitize_run(x) for x in runs]
    recent = sort_recent_runs(clean_runs)
    pool = operational_provider_pool(runtime, runtime_ok)
    mcp = runtime.get("mcp") if isinstance(runtime.get("mcp"), dict) else {}
    mcp_servers = runtime.get("mcp_servers") if isinstance(runtime.get("mcp_servers"), list) else mcp.get("servers", [])
    lmstudio_configured = any(str(p.get("provider", "")).lower() == "lmstudio" for p in runtime.get("providers", []))
    opencode = runtime.get("opencode") if isinstance(runtime.get("opencode"), dict) else {}
    opencode_ok = opencode.get("ct8001_reachable") is True and opencode.get("binary_present") is True and bool(opencode.get("version")) and opencode.get("version") != "UNKNOWN"
    run_counts = build_run_counts(clean_runs)
    alerts = []
    if runtime_ok and len(pool) < FREE_POOL_MINIMUM: alerts.append({"severity": "HIGH", "code": "FREE_POOL_BELOW_MIN", "message": "No eligible zero-cost route available"})
    if runtime.get("automatic_paid_agent_escalation"): alerts.append({"severity": "CRITICAL", "code": "PAID_ESCALATION_ENABLED", "message": "Automatic paid escalation enabled"})
    if health_n8n["status"] != "HEALTHY": alerts.append({"severity": "HIGH", "code": "N8N_UNAVAILABLE", "message": "n8n UNAVAILABLE"})
    if health_adapter["status"] != "HEALTHY": alerts.append({"severity": "HIGH", "code": "ADAPTER_UNAVAILABLE", "message": "Adapter UNAVAILABLE"})
    for run in clean_runs:
        if is_stale_run(run): alerts.append({"severity": "WARNING", "code": "STALE_ACTIVE_RUN", "message": "Active run has not been updated for a long time", "run_id": run.get("run_id")})
    project_rows = project_projection(projects, issues, clean_runs)
    active = choose_active_run(clean_runs)
    debug, debug_ok = debugging_events(active.get("run_id") if active else None)
    telemetry = runtime_telemetry(active or {}, debug)
    pool_health = provider_pool_status(len(pool)) if runtime_ok else "UNAVAILABLE"
    pool_module = {"status": pool_health, "diagnostic_status": "OK" if pool_health == "HEALTHY" else "NICHT_OK", "role": "REQUIRED", "checked_at": now(), "freshness_seconds": 0}
    event_module = safe_status(debug_ok)
    mcp_module = {"status": "OK" if mcp.get("status") == "OK" else "NICHT_KONFIGURIERT" if mcp.get("status") == "NICHT_KONFIGURIERT" else "NICHT_OK", "diagnostic_status": mcp.get("status", "NICHT_KONFIGURIERT"), "role": "OPTIONAL", "checked_at": now(), "freshness_seconds": 0, "servers": mcp_servers}
    lmstudio_module = {"status": "OK" if lmstudio_configured else "NICHT_KONFIGURIERT", "diagnostic_status": "OK" if lmstudio_configured else "NICHT_KONFIGURIERT", "role": "OPTIONAL", "checked_at": now(), "freshness_seconds": 0}
    opencode_module = {"status": "HEALTHY" if opencode_ok else "UNAVAILABLE", "diagnostic_status": "OK" if opencode_ok else "NICHT_OK", "role": "REQUIRED", "checked_at": now(), "freshness_seconds": 0, "version": opencode.get("version", "UNKNOWN")}
    modules = {"n8n": health_n8n, "adapter": health_adapter, "opencode": opencode_module, "provider_pool": pool_module, "event_stream": event_module, "mcp": mcp_module, "lmstudio": lmstudio_module}
    deepseek_policy = runtime.get("deepseek_policy") if isinstance(runtime.get("deepseek_policy"), dict) else {}
    deepseek_denied = all(deepseek_policy.get(key) is False for key in ("catalog_eligible", "router_eligible", "explicit_request_allowed", "fallback_allowed", "opencode_default"))
    mandatory_ok = health_n8n["status"] == "HEALTHY" and health_adapter["status"] == "HEALTHY" and opencode_ok and pool_health == "HEALTHY" and runtime.get("automatic_paid_agent_escalation") is False and deepseek_denied
    optional_missing = []
    if mcp_module["status"] == "NICHT_KONFIGURIERT": optional_missing.append("MCP")
    if lmstudio_module["status"] == "NICHT_KONFIGURIERT": optional_missing.append("LM Studio")
    free_pool_status = "AVAILABLE" if runtime_ok and pool else "EMPTY" if runtime_ok else "UNAVAILABLE"
    return {"contract": "autodev.control-tower-overview.v1", "version": "v1", "generated_at": now(), "freshness": {"checked_at": now(), "freshness_seconds": 0}, "system_health": modules, "system_health_summary": {"status": "OK" if mandatory_ok else "NICHT_OK", "diagnostic_status": "OK" if mandatory_ok else "NICHT_OK", "mandatory_ok": mandatory_ok, "ok": sum(value.get("status") in {"HEALTHY", "OK"} for value in modules.values()), "total": len(modules), "optional_not_configured": len(optional_missing)}, "free_pool": {"status": free_pool_status, "size": len(pool), "providers": pool}, "run_counts": run_counts, "recent_runs": recent, "projects": project_rows, "active_run": active, "debugging": {"current_run_id": active.get("run_id") if active else None, "stage": active.get("current_job") if active else None, "events": debug, "source": "LIVE" if debug_ok else "IDLE"}, "telemetry": telemetry, "alerts": alerts, "optional_components_not_configured": optional_missing, "release": {"dashboard_version": VERSION, "core_v1_release": "v1.0.0", "morpheus_release": "v1.1.2", "dashboard_release": VERSION, "v1_release": "v1.0.0", "n8n_autodev_workflows": health_n8n.get("workflow_count", 0), "free_first_active": bool(runtime.get("free_first_enabled")), "paid_escalation": bool(runtime.get("automatic_paid_agent_escalation")), "deepseek": "INELIGIBLE"}, "sources": {"n8n": "LIVE" if runs_ok and health_n8n["status"] == "HEALTHY" else "UNAVAILABLE", "adapter": "LIVE" if runtime_ok else "UNAVAILABLE", "projects": "LIVE" if projects_ok or issues_ok else "DERIVED"}}


def command_result_status(upstream_status: int, result: dict) -> int:
    """Map bounded canonical errors to HTTP without exposing upstream details."""
    if upstream_status >= 300:
        return upstream_status
    code = str(result.get("code", "")) if isinstance(result, dict) else ""
    if code in {"PROJECT_NOT_FOUND", "ISSUE_NOT_FOUND", "RUN_NOT_FOUND"}:
        return 404
    if code in {"PROJECT_ACTIVE_RUN_CONFLICT", "DUPLICATE_REQUEST", "CONTINUATION_NOT_ALLOWED", "RUN_ID_OWNERSHIP_CONFLICT"}:
        return 409
    if code in {"INVALID_TARGET", "COMMAND_NOT_ALLOWED", "ROLE_FORBIDDEN"}:
        return 403 if code == "ROLE_FORBIDDEN" else 400
    if isinstance(result, dict) and result.get("status") == "error":
        return 409
    return 202


def choose_active_run(runs):
    active = [run for run in runs if is_active_run(run)]
    return sort_recent_runs(active, 1)[0] if active else None


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
        return self.role() in READ_ROLES
    def role(self):
        return role_for_token(self.headers.get("X-Control-Tower-Token", ""), OPERATOR_TOKEN, ADMIN_TOKEN, VIEWER_TOKEN)
    def csrf_valid(self):
        # A custom header prevents a cross-site HTML form from reaching this
        # endpoint. Same-origin fetches send it explicitly.
        origin = self.headers.get("Origin") or self.headers.get("Referer")
        host = self.headers.get("Host", "")
        if origin:
            parsed = urllib.parse.urlparse(origin)
            if parsed.netloc and parsed.netloc != host:
                return False
        return self.headers.get("X-Control-Tower-Request") == "1"
    def request_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 600_000:
            raise ValueError("request body is missing or too large")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValueError("incomplete request body")
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("request body must be an object")
        return value
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/healthz":
            return self.send_json(200, {"status": "ok", "version": VERSION, "uptime_seconds": round(time.monotonic() - STARTED, 1)})
        if path == "/favicon.ico":
            self.send_response(204); self.headers_out(); self.send_header("Content-Length", "0"); self.end_headers(); return
        if path.startswith("/static/") or path == "/":
            if path == "/": path = "/static/index.html"
            target = (ROOT / path.lstrip("/")).resolve()
            if ROOT not in target.parents or not target.is_file(): return self.send_json(404, {"error": "not found"})
            body = target.read_bytes(); self.send_response(200); self.headers_out(); self.send_header("Content-Type", "text/html; charset=utf-8" if target.suffix == ".html" else "text/javascript; charset=utf-8" if target.suffix == ".js" else "text/css; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if not self.authorized(): return self.send_json(401, {"error": "unauthorized"})
        if self.command != "GET": return self.send_json(405, {"error": "method not allowed"})
        if path == "/api/v1/overview": return self.send_json(200, projection())
        if path == "/api/v1/telemetry/runtime": return self.send_json(200, telemetry_projection())
        if path == "/api/v1/session": return self.send_json(200, {"role": self.role(), "read_only": self.role() == "VIEWER", "commands": sorted(OPERATOR_COMMANDS if self.role() == "OPERATOR" else ADMIN_COMMANDS | OPERATOR_COMMANDS) if self.role() in READ_ROLES else []})
        if path == "/api/v1/projects":
            return self.send_json(200, {"contract": "autodev.project-view.v1", "version": "v1", "projects": projection()["projects"]})
        if path == "/api/v1/debugging":
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            run_id = query.get("run_id", [None])[0] if query.get("run_id", [None])[0] else None
            events, ok = debugging_events(run_id)
            return self.send_json(200, {"contract": "autodev.debugging.v1", "version": "v1", "run_id": run_id, "source": "LIVE" if ok else "IDLE", "events": events})
        if path == "/api/v1/runs":
            runs, _ = table_rows("runs"); return self.send_json(200, {"contract": "autodev.run-view.v1", "version": "v1", "runs": [sanitize_run(x) for x in runs]})
        if path.startswith("/api/v1/runs/") and path.endswith("/timeline"):
            run_id = urllib.parse.unquote(path[len("/api/v1/runs/"):-len("/timeline")]); view = run_view(run_id); return self.send_json(200, {"contract": "autodev.timeline-event.v1", "version": "v1", "run_id": run_id, "events": view["timeline"]})
        if path.startswith("/api/v1/runs/"):
            return self.send_json(200, run_view(urllib.parse.unquote(path[len("/api/v1/runs/"):])) )
        if path in ("/api/v1/providers", "/api/v1/runtime"):
            runtime, ok = adapter_runtime(); return self.send_json(200, {"contract": "autodev.runtime-health.v1", "version": "v1", "source": "LIVE" if ok else "UNAVAILABLE", **runtime})
        return self.send_json(404, {"error": "not found"})
    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path != "/api/v1/commands":
            return self.send_json(405, {"error": "method not allowed"})
        role = self.role()
        if role not in READ_ROLES:
            return self.send_json(401, {"error": "operator authentication required"})
        if not self.csrf_valid():
            return self.send_json(403, {"error": "csrf validation failed"})
        try:
            body = self.request_body()
            command = body.get("command")
            target = redact(body.get("target")) if isinstance(body.get("target"), dict) else {}
            validate_target(target)
            payload = body.get("payload", {})
            command, payload = validate_command(command, payload, role)
            correlation = body.get("correlation_id")
            if not isinstance(correlation, str) or not re_correlation_id(correlation):
                correlation = correlation_id(command, target)
            envelope = {"contract": "autodev.control-command.v1", "version": "v1", "command": command, "target": target, "payload": redact(payload), "actor": {"role": role}, "correlation_id": correlation}
            status, result = command_post(COMMAND_PATHS[command], envelope)
            result = redact(result)
            result.update({"contract": "autodev.command-result.v1", "command": command, "correlation_id": correlation, "audit": audit_entry(command, role, target, "ACCEPTED" if status < 300 and result.get("status") != "error" else "FAILED", payload.get("project_id"), payload.get("run_id") or payload.get("source_run_id"), correlation)})
            return self.send_json(command_result_status(status, result), result)
        except PermissionError as exc:
            return self.send_json(403, {"error": str(exc)})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return self.send_json(400, {"error": str(exc)})
    do_PUT = do_POST; do_PATCH = do_POST; do_DELETE = do_POST


def main():
    bind = os.environ.get("CONTROL_TOWER_BIND", "192.168.1.136")
    port = int(os.environ.get("CONTROL_TOWER_PORT", "8090"))
    ThreadingHTTPServer((bind, port), Handler).serve_forever()


if __name__ == "__main__": main()
