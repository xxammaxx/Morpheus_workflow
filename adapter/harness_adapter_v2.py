#!/usr/bin/env python3
"""AutoDev Harness Adapter v2 — execution-plane boundary for the n8n control plane.

n8n (CONTROL PLANE) -> authenticated HTTP -> THIS ADAPTER (EXECUTION PLANE) -> workers

Endpoints (token-authenticated, X-Harness-Token):
  GET  /healthz
  POST /v1/jobs                    {run_id, job_id, job_type, attempt_id,
                                    input_contract, input, backend, resume_url?}
  GET  /v1/jobs/{job_id}
  POST /v1/batches                 {run_id, batch_id, jobs: [...], barrier}
  GET  /v1/batches/{batch_id}
  POST /v1/artifacts/{run_id}/{name}   (compact JSON artifacts, e.g. split/decision)
  GET  /v1/artifacts/{run_id}/{name}
  GET  /v1/status/runtime             (sanitized read-only runtime snapshot)

Properties:
  - idempotent dispatch (run_id:job_id:attempt_id), duplicate callbacks safe
  - persistent append-only ledger (fsync), restart recovery (running -> interrupted)
  - job/attempt/batch granularity; real thread concurrency for batches
  - contract validation at the boundary (input AND output)
  - canonical SHA-256 fingerprints (input/output)
  - failure classification (TEST/BUILD/LINT/CONTRACT/CONTEXT/PROVIDER/INFRA/TIMEOUT/
    SECURITY_BLOCK/UNKNOWN) — never "model incapable" for infra failures
  - callback delivery to resume_url (deduped, 3 retries)
  - metadata-first telemetry (no prompts, no blobs, no secrets in the ledger)

LLMs are workers. The adapter is NOT a controller.
"""

import datetime as dt
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.parse
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE_DIR = os.environ.get("AUTODEV_V2_STATE", "/var/lib/autodev-harness-v2")
TOKEN_FILE = os.path.join(STATE_DIR, "token")
LEDGER_FILE = os.path.join(STATE_DIR, "logs", "runs.jsonl")
BATCH_FILE = os.path.join(STATE_DIR, "logs", "batches.jsonl")
ARTIFACT_DIR = os.path.join(STATE_DIR, "artifacts")
WS_ROOT = os.path.join(STATE_DIR, "workspaces")
BIND_HOST = "192.168.1.136"
BIND_PORT = 8081
VERSION = "2.0.0"

CONTRACTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "contracts")
if os.path.isdir(CONTRACTS_DIR):
    sys.path.insert(0, os.path.dirname(CONTRACTS_DIR))
from contracts import registry  # noqa: E402
from contracts.registry import fingerprint as fp  # noqa: E402

# HAMH layer (ADR-2026-08-20). Optional at deploy time: if the hamh package
# is not deployed next to this adapter (or reachable from the repo layout),
# resolution degrades to the explicit baseline fallback and behavior stays
# exactly at the v2 baseline. Deployed layout: <adapter_dir>/hamh;
# repo layout: <adapter_dir>/../runtime/hamh.
_ADAPTER_DIR = os.path.dirname(os.path.abspath(__file__))
for _hamh_dir in (
    os.path.join(_ADAPTER_DIR, "hamh"),
    os.path.join(_ADAPTER_DIR, "..", "runtime"),
    os.path.join(_ADAPTER_DIR, "..", "runtime", "hamh"),
):
    if os.path.isdir(_hamh_dir):
        sys.path.insert(0, _hamh_dir)
try:
    from hamh import resolver as hamh_resolver  # noqa: E402
    from hamh import registry as hamh_registry  # noqa: E402
except ImportError:  # pragma: no cover - deployment without hamh
    hamh_resolver = None
    hamh_registry = None

try:
    from providers.runtime import ProviderRuntime  # noqa: E402
    from providers.protocol import (
        NoEligibleProvider,
        ProviderFailure,
        RouteRequest,
        is_deepseek_identifier,
    )  # noqa: E402
except ImportError:  # pragma: no cover - legacy deployment without providers
    ProviderRuntime = None
    NoEligibleProvider = RuntimeError
    ProviderFailure = RuntimeError
    RouteRequest = None
    is_deepseek_identifier = lambda provider, model: False

# HAMH harness registry: loaded from <STATE_DIR>/hamh/registry.json when
# present. Without a registry file the resolver keeps the explicit baseline
# fallback (current production state). The promotion authority token comes
# from the environment and is never persisted by this adapter.
HAMH_REGISTRY_FILE = os.path.join(STATE_DIR, "hamh", "registry.json")
_hamh_registry = None
if hamh_registry is not None:
    try:
        _hamh_registry = hamh_registry.HarnessRegistry(
            path=HAMH_REGISTRY_FILE,
            authority_token=os.environ.get("AUTODEV_HAMH_AUTHORITY") or None,
        )
    except Exception:  # noqa: BLE001 - a broken registry must never break dispatch
        _hamh_registry = None

_provider_runtime = ProviderRuntime() if ProviderRuntime is not None else None

# ------------------------------------------------------------------ config --
BUILDER_CTID = "8001"
BUILDER_WS_ROOT = "/var/lib/ghiw/workspaces"
LOCAL_LLM_SRC = "/var/lib/ghiw/workspaces/provider-smoke-v3/local_llm"
OPENCODE_BIN = "/opt/dev-fabric/opencode/opencode"
LMSTUDIO_URL = "http://192.168.1.195:1234"
LMSTUDIO_MODEL = "huihui-qwen3.5-9b-abliterated"
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://192.168.1.50:11434").rstrip("/")
if OLLAMA_URL.endswith("/v1"):
    OLLAMA_URL = OLLAMA_URL[:-3].rstrip("/")
OLLAMA_MODEL = "qwen3:1.7b"
# Keep the local structured formatter's model binding independent from the
# worker identity.  A worker may use an external/free route, but its model
# identifier must never leak into this local Ollama request.
OLLAMA_FORMATTER_MODEL = os.environ.get("OLLAMA_FORMATTER_MODEL", OLLAMA_MODEL)
OLLAMA_FORMATTER_TIMEOUT_S = 60
DEFAULT_TIMEOUT_S = 600
MAX_WORKERS = 6
MAX_BODY = 262144
CANONICAL_URL = "http://192.168.1.136:%d" % BIND_PORT

JOB_TYPES = {
    "baseline": "autodev.baseline.v1",
    "research.code": "autodev.research.v1",
    "research.docs": "autodev.research.v1",
    "research.tests": "autodev.research.v1",
    "plan": "autodev.plan.v1",
    "build": "autodev.build-result.v1",
    "fix": "autodev.build-result.v1",
    "verify": "autodev.verification.v1",
    "review.correctness": "autodev.review-batch.v1",
    "review.security": "autodev.review-batch.v1",
    "review.quality": "autodev.review-batch.v1",
}
VALID_BACKENDS = {"embedded", "opencode-builder-8001"}
FIXTURES = {
    "invalid_plan",
    "verify_fail_delta",
    "verify_fail_no_delta",
    "no_signature",
    "attempt_limit",
    "security_critical_blocking",
    "review_fix",
    "review_split",
    "adapter_timeout",
    "malformed_response",
}
RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
JOB_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,96}$")
REPOSITORY_REF_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

# HAMH dispatch identity fields (ADR H15): provider/model select the harness
# profile; backend routing (VALID_BACKENDS) remains UNCHANGED.
HAMH_ID_RE = re.compile(r"^[A-Za-z0-9._/-]{0,64}$")
HAMH_TASK_CLASSES = {"research", "plan", "build", "review", "verify", "baseline"}


def _task_class_of(job_type):
    """Deterministic job_type -> HAMH task_class mapping."""
    if job_type == "baseline":
        return "baseline"
    if job_type in ("build", "fix"):
        return "build"
    if job_type == "verify":
        return "verify"
    if job_type == "plan":
        return "plan"
    if job_type.startswith("research."):
        return "research"
    if job_type.startswith("review."):
        return "review"
    return "baseline"


# ------------------------------------------------------------------ state --
_lock = threading.RLock()
JOBS = {}  # job_id -> record (dict)
BATCHES = {}  # batch_id -> record
_verify_seen = {}  # run_id -> verify job count (fail-once fixtures)
_review_seen = {}  # run_id -> review round count (fail-once review fixtures)
_sem = threading.BoundedSemaphore(MAX_WORKERS)
# per-backend opencode serialization semaphore (documented Phase-D mitigation;
# previously referenced but never defined -> latent NameError on any real
# opencode dispatch. Fixed as part of the HAMH seam, ADR H15.)
_opencode_sem = threading.BoundedSemaphore(1)
_callback_lock = threading.Lock()

for _d in (STATE_DIR, os.path.join(STATE_DIR, "logs"), ARTIFACT_DIR, WS_ROOT):
    os.makedirs(_d, exist_ok=True)


def _now():
    return dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts_ms():
    return int(time.time() * 1000)


def _sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _log_line(record):
    with _lock:
        with open(LEDGER_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
            f.flush()
            os.fsync(f.fileno())


def _log_batch(record):
    with _lock:
        with open(BATCH_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
            f.flush()
            os.fsync(f.fileno())


def _load():
    """Rebuild in-memory state from the append-only ledgers (crash recovery)."""
    if os.path.exists(LEDGER_FILE):
        with open(LEDGER_FILE) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                jid = rec.get("job_id")
                if not jid:
                    continue
                old = JOBS.get(jid)
                # replay last status; running at crash time -> interrupted
                if old is None:
                    JOBS[jid] = dict(rec)
                else:
                    old.update({k: v for k, v in rec.items() if v is not None})
        for jid, rec in JOBS.items():
            if rec.get("status") in ("queued", "running"):
                rec["status"] = "interrupted"
                rec["failure_class"] = "INFRA_FAILURE"
                rec["failure_signature"] = "ADAPTER_RESTART_INTERRUPTED"
                rec["error"] = "adapter restarted while job in flight"
                rec["ended_at"] = _now()
                _log_line(
                    {
                        "_": "recovered",
                        "job_id": jid,
                        "status": "interrupted",
                        "ts": _now(),
                    }
                )
    if os.path.exists(BATCH_FILE):
        with open(BATCH_FILE) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                bid = rec.get("batch_id")
                if bid and bid not in BATCHES:
                    BATCHES[bid] = dict(rec)
    for bid, brec in BATCHES.items():
        if brec.get("status") == "running":
            brec["status"] = "interrupted"
            brec["ended_at"] = _now()


# --------------------------------------------------------------- utilities --
def err(code, message, **extra):
    out = {"status": "error", "error": {"code": code, "message": message}}
    out.update(extra)
    return out


def ok(data):
    return {"status": "ok", "data": data}


def run_cmd(argv, timeout=DEFAULT_TIMEOUT_S, cwd=None):
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, cwd=cwd
        )
    except subprocess.TimeoutExpired:
        return type("R", (), {"returncode": -9, "stdout": "", "stderr": "TIMEOUT"})()
    except FileNotFoundError:
        return type(
            "R", (), {"returncode": -1, "stdout": "", "stderr": "pct not found"}
        )()


def pct_exec(cmd, timeout=DEFAULT_TIMEOUT_S):
    return run_cmd(
        ["pct", "exec", BUILDER_CTID, "--", "bash", "-c", cmd], timeout=timeout
    )


def pct_stdout(cmd, timeout=DEFAULT_TIMEOUT_S):
    r = pct_exec(cmd, timeout)
    return (r.stdout or "").strip()


def classify_job_failure(job_type, exc):
    """Map runtime failures to failure classes — never 'model incapable' for infra."""
    msg = str(exc)
    if "Timeout" in msg or "TIMEOUT" in msg:
        return "TIMEOUT", "JOB_TIMEOUT"
    if "Connection refused" in msg or "Unreachable" in msg:
        return "PROVIDER_FAILURE", "PROVIDER_UNREACHABLE"
    if "pct" in msg or "returncode" in msg:
        return "INFRA_FAILURE", "WORKER_UNAVAILABLE"
    return "UNKNOWN", "UNCLASSIFIED"


def call_resume_url(resume_url, payload):
    """Best-effort callback to an allowlisted n8n wait resume endpoint."""
    parsed = urllib.parse.urlparse(resume_url or "")
    allowlist = os.environ.get(
        "AUTODEV_CALLBACK_ALLOWLIST", "192.168.1.52:5678,192.168.1.195:18091"
    )
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    try:
        callback_port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return None
    if "%s:%s" % (
        parsed.hostname,
        callback_port,
    ) not in {item.strip() for item in allowlist.split(",") if item.strip()}:
        return None
    callback_headers = {"Content-Type": "application/json"}
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            callback_headers["X-Harness-Token"] = f.read().strip()
    req = urllib.request.Request(
        resume_url,
        data=json.dumps(payload).encode(),
        headers=callback_headers,
        method="POST",
    )

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_args, **_kwargs):
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    for attempt in range(3):
        try:
            with opener.open(req, timeout=15) as r:
                return r.status
        except Exception:
            if attempt < 2:
                time.sleep(1 + attempt)
    return None


def deliver_callback(job_id):
    rec = JOBS.get(job_id)
    if not rec or not rec.get("resume_url") or rec.get("callback_done"):
        return
    payload = {
        "run_id": rec.get("run_id"),
        "job_id": job_id,
        "attempt_id": rec.get("attempt_id"),
        "job_type": rec.get("job_type"),
        "status": rec.get("status"),
        "result": rec.get("result"),
        "error": rec.get("error"),
    }
    with _callback_lock:
        if rec.get("callback_done"):
            return
        code = call_resume_url(rec["resume_url"], payload)
        rec["callback_done"] = code is not None
        rec["callback_http"] = code


# ------------------------------------------------------------- job plumbing --
def new_job(
    run_id,
    job_id,
    job_type,
    attempt_id,
    input_contract,
    payload,
    backend,
    resume_url=None,
    fixture=None,
    timeout_s=None,
    sleep_seconds=None,
    provider=None,
    model=None,
    model_revision=None,
    task_class=None,
    harness_resolution=None,
    route_decision=None,
):
    rec = {
        "ts": _now(),
        "run_id": run_id,
        "job_id": job_id,
        "job_type": job_type,
        "attempt_id": attempt_id,
        "status": "queued",
        "backend": backend,
        # backend-aware identity defaults keep the record consistent with
        # the harness resolution (embedded -> embedded; opencode -> lmstudio)
        "provider": provider
        or ("lmstudio" if backend == "opencode-builder-8001" else "embedded"),
        "model": model
        or (OLLAMA_MODEL if provider == "ollama" else (LMSTUDIO_MODEL if backend == "opencode-builder-8001" else "embedded")),
        "harness_provider": provider
        or ("lmstudio" if backend == "opencode-builder-8001" else "embedded"),
        "harness_model": model
        or (OLLAMA_MODEL if provider == "ollama" else (LMSTUDIO_MODEL if backend == "opencode-builder-8001" else "embedded")),
        "route_provider": (route_decision or {}).get("route_provider"),
        "route_model": (route_decision or {}).get("route_model"),
        "route_endpoint": (route_decision or {}).get("route_endpoint"),
        "route_account_class": (route_decision or {}).get("route_account_class"),
        "selected_provider": (route_decision or {}).get("selected_provider"),
        "selected_model": (route_decision or {}).get("selected_model"),
        "routing_event_id": (route_decision or {}).get("routing_event_id"),
        "route_decision": route_decision,
        "provider_execution": None,
        "model_revision": model_revision,
        "task_class": task_class,
        "harness_resolution": harness_resolution,
        "input_contract": input_contract,
        "input_fingerprint": fp(payload),
        "output_contract": JOB_TYPES.get(job_type),
        "output_fingerprint": None,
        "started_at": None,
        "ended_at": None,
        "duration_ms": None,
        "failure_class": None,
        "failure_signature": None,
        "strategy_delta": None,
        "result_ref": None,
        "error": None,
        "fixture": fixture,
        "resume_url": resume_url,
        "callback_done": False,
        "timeout_s": timeout_s or DEFAULT_TIMEOUT_S,
        "sleep_seconds": sleep_seconds,
    }
    JOBS[job_id] = rec
    _log_line(dict(rec))
    return rec


def finalize_job(
    job_id,
    status,
    result=None,
    error=None,
    failure_class=None,
    failure_signature=None,
    strategy_delta=None,
    provider=None,
    model=None,
    provider_execution=None,
):
    rec = JOBS.get(job_id)
    if not rec:
        return
    rec["status"] = status
    rec["ended_at"] = _now()
    if rec.get("started_at"):
        try:
            st = dt.datetime.strptime(rec["started_at"], "%Y-%m-%dT%H:%M:%SZ")
            en = dt.datetime.strptime(rec["ended_at"], "%Y-%m-%dT%H:%M:%SZ")
            rec["duration_ms"] = int((en - st).total_seconds() * 1000)
        except Exception:
            rec["duration_ms"] = None
    # provider/model are only overwritten when explicitly provided: the
    # dispatch-time identity (incl. HAMH resolution inputs) wins.
    if provider is not None:
        rec["provider"] = provider
    if model is not None:
        rec["model"] = model
    if provider_execution is not None:
        rec["provider_execution"] = provider_execution
        rec["selected_provider"] = provider_execution.get("selected_provider")
        rec["selected_model"] = provider_execution.get("selected_model")
        rec["actual_provider"] = provider_execution.get("actual_provider")
        rec["actual_model"] = provider_execution.get("actual_model")
        rec["resolved_model"] = provider_execution.get("actual_model")
        rec["usage"] = provider_execution.get("usage", {})
        rec["actual_cost"] = provider_execution.get("actual_cost", 0)
        rec["free_eligible"] = provider_execution.get("free_eligible", False)
        rec["execution_proof"] = provider_execution.get("execution_proof")
        rec["failover"] = provider_execution.get("failover", [])
    if result is not None:
        rec["result"] = result
        rec["output_contract"] = (
            result.get("contract") if isinstance(result, dict) else None
        )
        rec["output_fingerprint"] = fp(result) if isinstance(result, dict) else None
        rec["result_ref"] = "%s/v1/jobs/%s" % (CANONICAL_URL, job_id)
    if error is not None:
        rec["error"] = error
    if failure_class:
        rec["failure_class"] = failure_class
    if failure_signature:
        rec["failure_signature"] = failure_signature
    if strategy_delta:
        rec["strategy_delta"] = strategy_delta
    _log_line(
        {
            k: v
            for k, v in rec.items()
            if k
            in (
                "ts",
                "run_id",
                "job_id",
                "job_type",
                "attempt_id",
                "status",
                "backend",
                "provider",
                "model",
                "harness_provider",
                "harness_model",
                "route_provider",
                "route_model",
                "route_endpoint",
                "route_account_class",
                "selected_provider",
                "selected_model",
                "routing_event_id",
                "actual_provider",
                "actual_model",
                "resolved_model",
                "usage",
                "actual_cost",
                "free_eligible",
                "execution_proof",
                "failover",
                "model_revision",
                "task_class",
                "harness_id",
                "harness_version",
                "harness_fingerprint",
                "input_contract",
                "input_fingerprint",
                "output_contract",
                "output_fingerprint",
                "started_at",
                "ended_at",
                "duration_ms",
                "failure_class",
                "failure_signature",
                "strategy_delta",
                "result_ref",
                "error",
            )
        }
    )
    deliver_callback(job_id)


def run_job_thread(
    run_id,
    job_id,
    job_type,
    attempt_id,
    input_contract,
    payload,
    backend,
    resume_url=None,
    fixture=None,
    timeout_s=None,
    sleep_seconds=None,
    route_decision=None,
):
    def worker():
        with _sem:
            rec = JOBS.get(job_id)
            if rec is None or rec["status"] not in ("queued",):
                return
            rec["status"] = "running"
            rec["started_at"] = _now()
            _log_line({"job_id": job_id, "status": "running", "ts": rec["started_at"]})
            start_mono = time.monotonic()
            try:
                if backend == "embedded":
                    handler = job_embedded
                else:
                    handler = EXECUTORS[job_type]
            except KeyError:
                # NOTE: nothing acquired yet -> no _opencode_sem.release()
                # here (an unbalanced release would raise ValueError and
                # leave the job stuck in "running"; ADR H15 fix)
                finalize_job(
                    job_id,
                    "failed",
                    error="unknown job type",
                    failure_class="UNKNOWN",
                    failure_signature="UNKNOWN_JOB_TYPE",
                )
                return
            try:
                if route_decision is not None:
                    _provider_direct_completion(
                        job_id,
                        run_id,
                        job_type,
                        payload,
                        route_decision,
                        rec.get("timeout_s", DEFAULT_TIMEOUT_S),
                        attempt_id,
                    )
                    return
                if backend == "opencode-builder-8001":
                    _opencode_sem.acquire()
                try:
                    handler(
                        job_id,
                        run_id,
                        job_type,
                        payload,
                        backend,
                        fixture,
                        rec.get("timeout_s", DEFAULT_TIMEOUT_S),
                    )
                finally:
                    if backend == "opencode-builder-8001":
                        _opencode_sem.release()
            except Exception as exc:  # noqa: BLE001 - boundary catches everything
                fclass, fsign = classify_job_failure(job_type, exc)
                finalize_job(
                    job_id,
                    "failed",
                    error=str(exc)[:500],
                    failure_class=fclass,
                    failure_signature=fsign,
                )
            elapsed = time.monotonic() - start_mono
            rec = JOBS.get(job_id)
            if (
                rec is not None
                and rec.get("status") == "running"
                and elapsed > rec.get("timeout_s", DEFAULT_TIMEOUT_S)
            ):
                finalize_job(
                    job_id,
                    "failed",
                    error="job exceeded timeout of %ss" % rec.get("timeout_s"),
                    failure_class="TIMEOUT",
                    failure_signature="JOB_TIMEOUT",
                )

    threading.Thread(target=worker, daemon=True, name="job-%s" % job_id).start()


def _provider_direct_completion(
    job_id, run_id, job_type, payload, route_decision, timeout_s, attempt_id
):
    """Execute the selected free route and persist only redacted proof fields."""
    if _provider_runtime is None:
        raise NoEligibleProvider("NO_ELIGIBLE_FREE_PROVIDER")
    task_class = _task_class_of(job_type)
    request = RouteRequest(
        provider=route_decision.get("selected_provider", ""),
        model=route_decision.get("selected_model", ""),
        task_class=task_class,
        privacy_class="ALLOWED",
        free_first=True,
    )
    messages = [
        {"role": "user", "content": str(payload.get("task_description", ""))[:12000]}
    ]
    execution = _provider_runtime.invoke_with_failover(
        request,
        messages,
        task_class,
        timeout_s,
        attempt_id,
    )
    proof = execution.execution_proof
    text = execution.response.text[:12000]
    if job_type.startswith("research."):
        area = job_type.split(".", 1)[1]
        result = {
            "contract": "autodev.research.v1",
            "version": "v1",
            "run_id": run_id,
            "areas": {
                "code": text if area == "code" else "",
                "docs": text if area == "docs" else "",
                "tests": text if area == "tests" else "",
            },
            "findings": [],
            "recommendations": [],
            "parallelism": {"jobs": [], "overlap_proven": False},
        }
    else:
        result = {
            "contract": JOB_TYPES.get(job_type),
            "version": "v1",
            "run_id": run_id,
            "summary": text,
        }
    validation = registry.validate(result, result.get("contract"))
    if not validation["ok"]:
        raise RuntimeError("provider output contract invalid")
    result["x-metadata"] = {"provider_execution": True}
    finalize_job(job_id, "completed", result=result, provider_execution=proof)


# ------------------------------------------------------------ embedded jobs --
def _embedded_result(job_type, fixture, payload):
    """Deterministic outputs for tests/canaries. Real work happens in opencode."""
    if fixture == "malformed_response":
        return None, {"ok": False, "errors": ["fixture malformed_response"]}
    if job_type == "baseline":
        return {
            "contract": "autodev.baseline.v1",
            "version": "v1",
            "run_id": payload.get("run_id"),
            "repository": {
                "identity": "embedded-canary",
                "head": "abc1234",
                "branch": "main",
                "working_tree_clean": True,
                "build_system": "python",
                "test_system": "pytest",
                "relevant_files": ["src/greeter.py", "tests/test_greeter.py"],
                "constraints": [],
            },
            "read_only_proof": {"sentinel_absent": True, "git_status_unchanged": True},
        }, None
    if job_type.startswith("research."):
        area = job_type.split(".")[1]
        return {
            "contract": "autodev.research.v1",
            "version": "v1",
            "run_id": payload.get("run_id"),
            "areas": {
                "code": "note: %s area (embedded canary)" % area,
                "docs": "note: %s area (embedded canary)" % area,
                "tests": "note: %s area (embedded canary)" % area,
            },
            "findings": [],
            "recommendations": [],
            "parallelism": {"jobs": [], "overlap_proven": False},
        }, None
    if job_type == "plan":
        if fixture == "invalid_plan":
            # schema-valid contract with WRONG run_id -> the deterministic plan
            # gate must reject it (PLAN_RUN_ID_MISMATCH / PLAN_REJECTED)
            return {
                "contract": "autodev.plan.v1",
                "version": "v1",
                "run_id": "wrong-run-mismatch",
                "repository_head": "abc1234",
                "targets": {"files": ["src/greeter.py"], "symbols": ["greet"]},
                "acceptance_criteria": ["greet('Welt') == 'Hello, Welt!'"],
                "required_tests": ["tests/test_greeter.py"],
                "risks": [],
                "build_scope": {
                    "allowed_files": ["src/greeter.py", "tests/test_greeter.py"]
                },
                "context": {"fingerprint": "c" * 64, "research_summary": "x"},
                "safety": {
                    "sentinel_absent": True,
                    "repo_unchanged": True,
                    "write_attempts": 0,
                },
            }, None
        return {
            "contract": "autodev.plan.v1",
            "version": "v1",
            "run_id": payload.get("run_id"),
            "repository_head": "abc1234",
            "targets": {"files": ["src/greeter.py"], "symbols": ["greet"]},
            "acceptance_criteria": ["greet('Welt') == 'Hello, Welt!'"],
            "required_tests": ["tests/test_greeter.py"],
            "risks": [],
            "build_scope": {
                "allowed_files": ["src/greeter.py", "tests/test_greeter.py"]
            },
            "context": {"fingerprint": "c" * 64, "research_summary": "embedded canary"},
            "safety": {
                "sentinel_absent": True,
                "repo_unchanged": True,
                "write_attempts": 0,
            },
        }, None
    if job_type in ("build", "fix"):
        files = payload.get("targets", {}).get("files", []) or ["src/greeter.py"]
        return {
            "contract": "autodev.build-result.v1",
            "version": "v1",
            "run_id": payload.get("run_id"),
            "attempt_id": payload.get("attempt_id"),
            "status": "success",
            "changed_files": [{"path": f, "change": "add", "size": 120} for f in files],
            "summary": "embedded build ok",
            "test_results": {"passed": 2, "failed": 0},
        }, None
    if job_type == "verify":
        # fail-once fixtures: the first verify for a run fails, later verifies
        # (fix loop) pass so the loop converges; attempt_limit fails every verify
        run_key = str(payload.get("run_id") or "")
        with _lock:
            _verify_seen[run_key] = _verify_seen.get(run_key, 0) + 1
            verify_no = _verify_seen[run_key]
        if (
            fixture in ("verify_fail_delta", "verify_fail_no_delta", "no_signature")
            and verify_no > 1
        ):
            return {
                "contract": "autodev.verification.v1",
                "version": "v1",
                "run_id": payload.get("run_id"),
                "passed": True,
                "checks": [
                    {
                        "name": "unit",
                        "type": "unit",
                        "passed": True,
                        "detail": "2 passed",
                    },
                    {
                        "name": "build",
                        "type": "build",
                        "passed": True,
                        "detail": "compile ok",
                    },
                    {
                        "name": "scope",
                        "type": "invariant",
                        "passed": True,
                        "detail": "in scope",
                    },
                ],
                "failure_class": None,
                "failure_signature": None,
                "new_evidence": [],
            }, None
        if fixture == "verify_fail_delta":
            return {
                "contract": "autodev.verification.v1",
                "version": "v1",
                "run_id": payload.get("run_id"),
                "passed": False,
                "checks": [
                    {
                        "name": "unit",
                        "type": "unit",
                        "passed": False,
                        "detail": "test_returns_hello FAILED",
                    }
                ],
                "failure_class": "TEST_FAILURE",
                "failure_signature": "sig-" + _sha("test_returns_hello FAILED")[:16],
                "new_evidence": [
                    "test_returns_hello FAILED: expected 'Hello, Welt!' got 'Hello Welt'"
                ],
            }, None
        if fixture == "verify_fail_no_delta":
            return {
                "contract": "autodev.verification.v1",
                "version": "v1",
                "run_id": payload.get("run_id"),
                "passed": False,
                "checks": [
                    {"name": "unit", "type": "unit", "passed": False, "detail": "x"}
                ],
                "failure_class": "TEST_FAILURE",
                "failure_signature": "sig-" + _sha("x")[:16],
                "new_evidence": [],
            }, None
        if fixture == "attempt_limit":
            # always fails (with evidence) -> exercises the attempt-limit retry path
            return {
                "contract": "autodev.verification.v1",
                "version": "v1",
                "run_id": payload.get("run_id"),
                "passed": False,
                "checks": [
                    {
                        "name": "unit",
                        "type": "unit",
                        "passed": False,
                        "detail": "test_returns_hello FAILED (attempt limit)",
                    }
                ],
                "failure_class": "TEST_FAILURE",
                "failure_signature": "sig-" + _sha("attempt limit")[:16],
                "new_evidence": ["test_returns_hello FAILED: persistent failure"],
            }, None
        if fixture == "no_signature":
            return {
                "contract": "autodev.verification.v1",
                "version": "v1",
                "run_id": payload.get("run_id"),
                "passed": False,
                "checks": [
                    {"name": "unit", "type": "unit", "passed": False, "detail": "x"}
                ],
                "failure_class": "TEST_FAILURE",
                "failure_signature": None,
                "new_evidence": [],
            }, None
        return {
            "contract": "autodev.verification.v1",
            "version": "v1",
            "run_id": payload.get("run_id"),
            "passed": True,
            "checks": [
                {"name": "unit", "type": "unit", "passed": True, "detail": "2 passed"},
                {
                    "name": "build",
                    "type": "build",
                    "passed": True,
                    "detail": "compile ok",
                },
                {
                    "name": "scope",
                    "type": "invariant",
                    "passed": True,
                    "detail": "in scope",
                },
            ],
            "failure_class": None,
            "failure_signature": None,
            "new_evidence": [],
        }, None
    if job_type.startswith("review."):
        area = job_type.split(".")[1]
        run_key = str(payload.get("run_id") or "")
        if fixture in ("review_fix", "review_split"):
            with _lock:
                _review_seen[run_key] = _review_seen.get(run_key, 0) + 1
                review_no = _review_seen[run_key]
            if review_no > 1:
                # later review rounds pass (fix loop converges)
                return {
                    "contract": "autodev.review-batch.v1",
                    "version": "v1",
                    "run_id": payload.get("run_id"),
                    "reviews": [{"category": area, "verdict": "PASS", "findings": []}],
                    "blocked": False,
                    "blocking_findings": [],
                    "parallelism": {"jobs": [], "overlap_proven": False},
                }, None
        if fixture == "security_critical_blocking":
            return {
                "contract": "autodev.review-batch.v1",
                "version": "v1",
                "run_id": payload.get("run_id"),
                "reviews": [
                    {
                        "category": area,
                        "verdict": "FAIL",
                        "findings": [
                            {
                                "category": "security",
                                "severity": "CRITICAL",
                                "confidence": "HIGH",
                                "blocking": True,
                                "rule": "SEC-001",
                                "evidence": {
                                    "file": "src/greeter.py",
                                    "symbol": "greet",
                                    "line_range": "1-10",
                                },
                                "recommendation": "remove hardcoded secret",
                            }
                        ],
                    }
                ],
                "blocked": True,
                "blocking_findings": [],
                "parallelism": {"jobs": [], "overlap_proven": False},
            }, None
        if fixture == "review_fix":
            return {
                "contract": "autodev.review-batch.v1",
                "version": "v1",
                "run_id": payload.get("run_id"),
                "reviews": [
                    {
                        "category": area,
                        "verdict": "FAIL",
                        "findings": [
                            {
                                "category": "quality",
                                "severity": "MEDIUM",
                                "confidence": "MEDIUM",
                                "blocking": False,
                                "rule": "QUAL-001",
                                "evidence": {
                                    "file": "src/greeter.py",
                                    "symbol": "greet",
                                },
                                "recommendation": "use f-string for clarity",
                            }
                        ],
                    }
                ],
                "blocked": False,
                "blocking_findings": [],
                "parallelism": {"jobs": [], "overlap_proven": False},
            }, None
        if fixture == "review_split":
            return {
                "contract": "autodev.review-batch.v1",
                "version": "v1",
                "run_id": payload.get("run_id"),
                "reviews": [
                    {
                        "category": area,
                        "verdict": "FAIL",
                        "findings": [
                            {
                                "category": "correctness",
                                "severity": "LOW",
                                "confidence": "LOW",
                                "blocking": False,
                                "rule": "REVIEW-SPLIT-REQUEST",
                                "evidence": {"file": "src/greeter.py"},
                                "recommendation": "split into subtasks: formatting and logic",
                            }
                        ],
                    }
                ],
                "blocked": False,
                "blocking_findings": [],
                "parallelism": {"jobs": [], "overlap_proven": False},
            }, None
        return {
            "contract": "autodev.review-batch.v1",
            "version": "v1",
            "run_id": payload.get("run_id"),
            "reviews": [{"category": area, "verdict": "PASS", "findings": []}],
            "blocked": False,
            "blocking_findings": [],
            "parallelism": {"jobs": [], "overlap_proven": False},
        }, None
    return None, {"ok": False, "errors": ["unsupported job type %s" % job_type]}


def job_embedded(job_id, run_id, job_type, payload, backend, fixture, timeout_s):
    rec = JOBS.get(job_id) or {}
    sleep_s = rec.get("sleep_seconds")
    if sleep_s:
        time.sleep(min(float(sleep_s), max(timeout_s - 1, 0.5)))
    if fixture == "adapter_timeout":
        time.sleep(3)  # longer than the injected tiny timeout
        return
    result, invalid = _embedded_result(job_type, fixture, payload)
    if invalid is not None:
        finalize_job(
            job_id,
            "failed",
            error="contract invalid: %s" % invalid["errors"][:1],
            failure_class="CONTRACT_FAILURE",
            failure_signature="CONTRACT_INVALID",
        )
        return
    v = registry.validate(result, result.get("contract"))
    if not v["ok"]:
        finalize_job(
            job_id,
            "failed",
            error="output contract invalid: %s" % v["errors"][:2],
            failure_class="CONTRACT_FAILURE",
            failure_signature="CONTRACT_INVALID",
        )
        return
    # attach metadata for the ledger
    result["x-metadata"] = {"backend": backend}
    finalize_job(job_id, "completed", result=result)


# ------------------------------------------------------- opencode-builder ---
def _ws(run_id):
    return os.path.join(BUILDER_WS_ROOT, "autodev-v2-%s" % run_id)


def _agent_md(name, tools, permissions, blurb, model=None):
    return (
        "---\n"
        "description: %s\n"
        "model: lmstudio/%s\n"
        "temperature: 0\n"
        "tools:\n%s"
        "permission:\n%s"
        "---\n"
        "You are a bounded harness worker (%s). Follow the task text exactly.\n"
        % (
            blurb,
            model or LMSTUDIO_MODEL,
            "".join(
                "  %s: %s\n" % (k, "true" if v else "false") for k, v in tools.items()
            ),
            "".join("  %s: %s\n" % (k, v) for k, v in permissions.items()),
            name,
        )
    )


PLAN_TOOLS = {
    "read": True,
    "glob": True,
    "grep": True,
    "list": True,
    "bash": False,
    "edit": False,
    # Expose the tool so OpenCode can emit the required denied sentinel
    # attempt; PLAN_PERMS keeps execution fail-closed.
    "write": True,
    "webfetch": False,
    "task": False,
    "skill": False,
    "question": False,
    "todowrite": False,
}
PLAN_PERMS = {
    "read": "allow",
    "glob": "allow",
    "grep": "allow",
    "list": "allow",
    "bash": "deny",
    "edit": "deny",
    "write": "deny",
    "webfetch": "deny",
    "task": "deny",
    "skill": "deny",
    "question": "deny",
    "todowrite": "deny",
}
RESEARCH_TOOLS = dict(PLAN_TOOLS)
RESEARCH_PERMS = dict(PLAN_PERMS)
BUILD_TOOLS = {
    "read": True,
    "edit": True,
    "write": True,
    "list": True,
    "bash": False,
    "glob": True,
    "grep": True,
    "webfetch": False,
    "task": False,
    "skill": False,
    "question": False,
    "todowrite": False,
}
BUILD_PERMS = {
    "read": "allow",
    "edit": "allow",
    "write": "allow",
    "glob": "allow",
    "grep": "allow",
    "list": "allow",
    "bash": "deny",
    "webfetch": "deny",
    "task": "deny",
    "skill": "deny",
    "question": "deny",
    "todowrite": "deny",
}


def _opencode_script(ws, agent_name, agent_md, prompt, timeout_s, provider=None, model=None):
    provider = provider or "lmstudio"
    worker_url = OLLAMA_URL if provider == "ollama" else LMSTUDIO_URL
    worker_model = model or (OLLAMA_MODEL if provider == "ollama" else LMSTUDIO_MODEL)
    return (
        "set -e; cd '%s'; "
        "mkdir -p .opencode/agents; "
        "cat > .opencode/agents/%s.md << 'EOFAGENT'\n%s\nEOFAGENT\n"
        "cp -r '%s' ./local_llm 2>/dev/null || true; "
        "export GHIW_LOCAL_LLM_ENABLED=true "
        "GHIW_LMSTUDIO_BASE_URL='%s' GHIW_LMSTUDIO_MODEL_ID='%s' "
        "GHIW_LMSTUDIO_TIMEOUT_SECONDS=%d GHIW_LOCAL_LLM_CONTEXT_LIMIT=32768 "
        "GHIW_LOCAL_LLM_MAX_ATTEMPTS=1 GHIW_LOCAL_LLM_CONCURRENCY=1; "
        'export OPENCODE_CONFIG_CONTENT="$(python3 -m local_llm.opencode_cli)"; '
        "export PATH='/opt/dev-fabric/opencode:/usr/local/bin:/usr/bin:/bin'; "
        "%s run --agent %s --model 'lmstudio/%s' --format json %s "
        "> build.jsonl 2> build.stderr"
    ) % (
        ws,
        agent_name,
        agent_md,
        LOCAL_LLM_SRC,
        worker_url,
        worker_model,
        int(timeout_s),
        OPENCODE_BIN,
        agent_name,
        worker_model,
        json.dumps(prompt),
    )


def _worker_identity(payload):
    metadata = payload.get("x-metadata") or {}
    return metadata.get("execution_provider"), metadata.get("execution_model")


def _parse_opencode_jsonl(ws):
    """Return (assistant_text, tool_events) parsed from build.jsonl."""
    path = os.path.join(ws, "build.jsonl")
    text_parts, tool_events = [], []
    # build.jsonl lives inside the isolated builder CT, not on the adapter
    # host. Read it through the existing pct boundary rather than checking
    # the host filesystem (which silently made valid plans look missing).
    raw = pct_stdout("cat '%s' 2>/dev/null || true" % path)
    if not raw:
        return "", []
    for line in raw.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("type") == "message":
                msg = ev.get("message", {})
                if msg.get("role") == "assistant":
                    content = msg.get("content")
                    if isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                text_parts.append(part.get("text", ""))
                    elif isinstance(content, str):
                        text_parts.append(content)
            elif ev.get("type") == "text":
                part = ev.get("part") or {}
                content = part.get("text")
                if isinstance(content, str):
                    text_parts.append(content)
            elif ev.get("type") == "tool":
                tool = ev.get("tool", {})
                name = tool.get("name") or tool.get("tool") or "?"
                tool_events.append(name)
                if ev.get("state") == "error":
                    tool_events.append("error:" + name)
            elif ev.get("type") == "permission":
                perm = ev.get("permission", {})
                tool_events.append(
                    "denied:%s" % (perm.get("tool") or perm.get("reason") or "?")
                )
            elif ev.get("type") == "denied":
                tool_events.append("denied:%s" % (ev.get("tool") or "?"))
            elif ev.get("type") == "error":
                tool_events.append("error:%s" % str(ev.get("error"))[:80])
    return "\n".join(text_parts), tool_events


def _extract_json(text):
    """Extract the first balanced JSON object from a string (fence-aware)."""
    import re as _re

    # strip markdown fences if present
    m = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, _re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except ValueError:
            pass
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except ValueError:
                        return None
    return None


def _write_attempts(tool_events):
    writes = [e for e in tool_events if e in ("edit", "write")]
    denied = [e for e in tool_events if e.startswith("denied")]
    return len(writes), len(denied)


def _plan_model_schema():
    """Derive the model-owned plan shape from the canonical contract.

    Adapter-owned identity, context and safety fields are deliberately not
    exposed to the model.  The two stricter semantic requirements below are
    the formatter boundary, not a change to autodev.plan.v1.
    """
    canonical = copy.deepcopy(registry.get_schema("autodev.plan.v1"))
    owned = {"targets", "acceptance_criteria", "required_tests", "risks",
             "build_scope"}
    schema = {
        "type": "object",
        "required": ["targets", "acceptance_criteria", "required_tests",
                      "risks", "build_scope", "research_summary"],
        "properties": {},
        "additionalProperties": False,
    }
    for name in owned:
        if name in canonical.get("properties", {}):
            schema["properties"][name] = canonical["properties"][name]
    # research_summary is adapter-context content, represented as a model
    # field for serialization but never used to manufacture plan semantics.
    schema["properties"]["research_summary"] = {
        "type": "string", "maxLength": 4000
    }
    schema["properties"]["targets"]["required"] = ["files", "symbols"]
    schema["properties"]["targets"]["properties"]["symbols"] = {
        "type": "array", "items": {"type": "string"}
    }
    schema["properties"]["build_scope"]["properties"]["allowed_files"]["minItems"] = 1
    # Ollama's structured-output compiler accepts the JSON Schema structural
    # subset used by the contract, but some deployed versions reject string
    # length annotations while loading the model vocabulary. Canonical
    # validation below still enforces those limits.
    def strip_ollama_annotations(value):
        if isinstance(value, dict):
            value.pop("maxLength", None)
            value.pop("minLength", None)
            for child in value.values():
                strip_ollama_annotations(child)
        elif isinstance(value, list):
            for child in value:
                strip_ollama_annotations(child)
    strip_ollama_annotations(schema)
    return schema


def _ollama_format_plan(candidate_text, model=None):
    """Perform exactly one local, no-tools serialization pass."""
    if not isinstance(candidate_text, str) or not candidate_text.strip():
        return None, "formatter candidate is empty"
    # The formatter receives only the candidate text, with common credential
    # forms redacted before it leaves the adapter process.
    candidate_text = re.sub(
        r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,}]+",
        r"\1=<redacted>", candidate_text,
    )
    prompt = (
        "Transform the supplied planning result into the JSON schema. "
        "Do not add implementation targets, tests, acceptance criteria, or "
        "risks that are not supported by the supplied plan. If mandatory "
        "semantic information is absent, return an object with the affected "
        "required arrays empty; do not guess. Return JSON only.\n\n"
        "SUPPLIED PLAN:\n%s"
    ) % candidate_text[:16000]
    body = json.dumps({
        # ``model`` remains an ignored compatibility argument for direct
        # callers from older tests; formatter routing is always explicit and
        # local, never inherited from the worker model.
        "model": OLLAMA_FORMATTER_MODEL,
        "prompt": prompt,
        "format": _plan_model_schema(),
        "stream": False,
        "options": {"temperature": 0},
    }).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL + "/api/generate", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_FORMATTER_TIMEOUT_S) as response:
            raw = json.loads(response.read().decode("utf-8"))
        text = raw.get("response", "") if isinstance(raw, dict) else ""
        obj = _extract_json(text)
        if not isinstance(obj, dict):
            return None, "formatter response is not parseable JSON"
        return obj, None
    except Exception as exc:  # noqa: BLE001 - fail closed at the contract boundary
        return None, "formatter request failed: %s" % type(exc).__name__


def _plan_scope_errors(plan):
    errors = []
    targets = plan.get("targets", {})
    scope = plan.get("build_scope", {})
    target_files = targets.get("files", []) if isinstance(targets, dict) else []
    allowed = scope.get("allowed_files", []) if isinstance(scope, dict) else []
    if not target_files:
        errors.append("$.targets.files: must have at least 1 item")
    if not allowed:
        errors.append("$.build_scope.allowed_files: must have at least 1 item")
    outside = [path for path in target_files if path not in allowed]
    if outside:
        errors.append("$.build_scope: targets outside allowed_files: %s" % ", ".join(outside[:10]))
    return errors


def _git_state(ws):
    head = pct_stdout("cd '%s' && git rev-parse HEAD 2>/dev/null || echo NOCOMMIT" % ws)
    # Ignore harness bookkeeping when assessing read-only plan mutations.
    status = pct_stdout(
        "cd '%s' && git status --porcelain 2>/dev/null | "
        "grep -vE '^(.. )?\\.(opencode|plan-canary-sentinel)(/|$)|^(.. )?local_llm(/|$)|^(.. )?(build\\.jsonl|build\\.stderr)$' || true"
        % ws
    )
    branch = pct_stdout(
        "cd '%s' && git branch --show-current 2>/dev/null || echo main" % ws
    )
    return head.strip(), status, branch.strip()


def _ensure_workspace(run_id, repository_ref=None):
    """Create a clean worker workspace, materializing the requested repo.

    External acceptance jobs must inspect the target repository, not the
    historical empty canary stub. The remote's symbolic HEAD determines the
    default branch, so repositories using ``master`` remain supported.
    """
    ws = _ws(run_id)
    if repository_ref:
        if not REPOSITORY_REF_RE.fullmatch(repository_ref):
            raise RuntimeError("invalid repository_ref")
        repo_url = "https://github.com/%s.git" % repository_ref
        current = pct_stdout("cd '%s' 2>/dev/null && git remote get-url origin 2>/dev/null || true" % ws)
        expected_url = "https://github.com/%s.git" % repository_ref
        if current.rstrip("/") != expected_url.rstrip("/"):
            tmp = ws + ".checkout"
            pct_exec("rm -rf '%s' '%s'" % (tmp, ws))
            clone = (
                "set -e; branch=$(git ls-remote --symref '%s' HEAD | "
                "awk '/^ref:/ {sub(\"refs/heads/\", \"\", $2); print $2; exit}'); "
                "test -n \"$branch\"; git clone --depth 1 --branch \"$branch\" '%s' '%s'"
            ) % (repo_url, repo_url, tmp)
            result = pct_exec(clone)
            if result.returncode != 0:
                raise RuntimeError("repository checkout failed: %s" % (result.stderr or "")[:300])
            pct_exec("mv '%s' '%s'" % (tmp, ws))
        return ws
    pct_exec(
        "mkdir -p '%s' && cd '%s' && "
        "git init -q 2>/dev/null; git config user.email harness@local; "
        "git config user.name harness; "
        "mkdir -p src tests; "
        "test -f .gitkeep_src || touch src/.gitkeep; "
        "test -f .gitkeep_tests || touch tests/.gitkeep; "
        "git add -A && git commit -qm init 2>/dev/null || true" % (ws, ws)
    )
    return ws


def job_baseline(job_id, run_id, job_type, payload, backend, fixture, timeout_s):
    ws = _ensure_workspace(run_id, payload.get("repository_ref"))
    head, status, branch = _git_state(ws)
    if len(head) < 7:
        head = "workspace-" + str(run_id)[:48]
    if not branch:
        branch = "main"
    files = pct_stdout(
        "cd '%s' && find . -type f -not -path './.git/*' "
        "-not -path './local_llm/*' -not -path './.opencode/*' | "
        "sed 's#^./##' | sort | head -50" % ws
    )
    build_system, test_system = "unknown", "unknown"
    probe = pct_stdout(
        "cd '%s' && ls pyproject.toml package.json setup.py Makefile 2>/dev/null || true"
        % ws
    )
    if "pyproject.toml" in probe or "setup.py" in probe:
        build_system, test_system = "python", "pytest"
    elif "package.json" in probe:
        build_system, test_system = "node", "node --test"
    result = {
        "contract": "autodev.baseline.v1",
        "version": "v1",
        "run_id": run_id,
        "repository": {
            "identity": "builder-8001:" + ws,
            "head": head[:40],
            "branch": branch,
            "working_tree_clean": not bool(status.strip()),
            "build_system": build_system,
            "test_system": test_system,
            "relevant_files": [l for l in files.splitlines() if l][:50],
            "constraints": [
                "read-only baseline; no mutations",
                "allowed writes restricted to plan build_scope",
            ],
        },
        "read_only_proof": {
            "sentinel_absent": True,
            "git_status_unchanged": not bool(status.strip()),
        },
    }
    v = registry.validate(result, "autodev.baseline.v1")
    if not v["ok"]:
        finalize_job(
            job_id,
            "failed",
            error="output contract invalid: %s" % v["errors"][:2],
            failure_class="CONTRACT_FAILURE",
            failure_signature="CONTRACT_INVALID",
        )
        return
    result["x-metadata"] = {"backend": backend}
    finalize_job(job_id, "completed", result=result)


def job_research(job_id, run_id, job_type, payload, backend, fixture, timeout_s):
    ws = _ensure_workspace(run_id, payload.get("repository_ref"))
    area = job_type.split(".")[1]
    prompt = (
        "You are a read-only research worker. Workspace: current directory. "
        "Research the '%s' aspect of this task: %s\n"
        "You may READ, glob, grep, list files. You must NOT write, edit, run commands "
        "or use the network. "
        "Respond with ONLY a JSON object of this exact shape:\n"
        '{"note": "<max 2500 chars, factual findings about the %s aspect>"}\n'
        "No markdown fences, no extra text."
    ) % (area, payload.get("task_description", ""), area)
    script = _opencode_script(
        ws,
        "research-worker",
        _agent_md(
            "research-worker",
            RESEARCH_TOOLS,
            RESEARCH_PERMS,
            "Read-only research worker",
            _worker_identity(payload)[1],
        ),
        prompt,
        timeout_s,
        *_worker_identity(payload),
    )
    pct_exec(script, timeout=timeout_s)
    text, events = _parse_opencode_jsonl(ws)
    note = text.strip()
    obj = _extract_json(text)
    if isinstance(obj, dict) and isinstance(obj.get("note"), str):
        note = obj["note"]
    note = note[:4000]
    result = {
        "contract": "autodev.research.v1",
        "version": "v1",
        "run_id": run_id,
        "areas": {
            "code": note if area == "code" else "",
            "docs": note if area == "docs" else "",
            "tests": note if area == "tests" else "",
        },
        "findings": [],
        "recommendations": [],
        "parallelism": {"jobs": [], "overlap_proven": False},
    }
    v = registry.validate(result, "autodev.research.v1")
    if not v["ok"]:
        finalize_job(
            job_id,
            "failed",
            error="output contract invalid: %s" % v["errors"][:2],
            failure_class="CONTRACT_FAILURE",
            failure_signature="CONTRACT_INVALID",
        )
        return
    result["x-metadata"] = {"backend": backend}
    finalize_job(job_id, "completed", result=result)


def job_plan(job_id, run_id, job_type, payload, backend, fixture, timeout_s):
    ws = _ensure_workspace(run_id, payload.get("repository_ref"))
    head_before, status_before, _ = _git_state(ws)
    research = (payload.get("x-metadata") or {}).get("research")
    research_context = ""
    if isinstance(research, dict) and research.get("contract") == "autodev.research.v1":
        # The orchestrator passes the already contract-validated research
        # result through the existing issue x-metadata extension field.
        research_context = "\nValidated research context:\n%s\n" % json.dumps(
            research, ensure_ascii=False, sort_keys=True
        )[:4000]
    prompt = (
        "/no_think\n"
        "You are a read-only planning worker. Task: %s\n"
        "%s"
        "The read-only policy and sentinel-deny preflight are already verified. "
        "Do not call write, edit, task, bash, or any tool; do not access the network. "
        "Return JSON immediately, with concrete non-empty targets and allowed_files "
        "supported by the task/research. Never include .plan-canary-sentinel.\n"
        "Schema: {\"targets\":{\"files\":[\"path\"],\"symbols\":[]},"
        "\"acceptance_criteria\":[\"criterion\"],\"required_tests\":[\"test\"],"
        "\"risks\":[],\"build_scope\":{\"allowed_files\":[\"path\"]},"
        "\"research_summary\":\"brief evidence\"}"
    ) % (payload.get("task_description", ""), research_context)
    script = _opencode_script(
        ws,
        "plan-worker",
        _agent_md(
            "plan-worker", PLAN_TOOLS, PLAN_PERMS,
            "Read-only planning worker", _worker_identity(payload)[1],
        ),
        prompt,
        timeout_s,
        *_worker_identity(payload),
    )
    pct_exec(script, timeout=timeout_s)
    text, events = _parse_opencode_jsonl(ws)
    obj = _extract_json(text)
    head_after, status_after, _ = _git_state(ws)
    sentinel_present = bool(
        pct_stdout("cd '%s' && ls .plan-canary-sentinel 2>/dev/null || true" % ws)
    )
    writes, denied = _write_attempts(events)
    formatter_used = False
    formatter_error = None
    parse_failed = not isinstance(obj, dict)
    if not isinstance(obj, dict):
        obj, formatter_error = _ollama_format_plan(text)
        formatter_used = True
    if not isinstance(obj, dict):
        obj = {}
    plan = {
        "contract": "autodev.plan.v1",
        "version": "v1",
        "run_id": run_id,
        "repository_head": head_after[:40],
        "targets": {
            "files": obj.get("targets", {}).get("files", []),
            "symbols": obj.get("targets", {}).get("symbols", []),
        },
        "acceptance_criteria": obj.get("acceptance_criteria", []),
        "required_tests": obj.get("required_tests", []),
        "risks": obj.get("risks", []),
        "build_scope": {
            "allowed_files": obj.get("build_scope", {}).get("allowed_files", [])
        },
        "context": {
            "fingerprint": fp(payload),
            "research_summary": obj.get("research_summary", "")[:4000],
        },
        "safety": {
            "sentinel_absent": not sentinel_present,
            "repo_unchanged": head_before == head_after
            and status_before == status_after,
            "write_attempts": writes,
            "denied_events": denied,
        },
    }
    v = registry.validate(plan, "autodev.plan.v1")
    consistency_errors = _plan_scope_errors(plan)
    if plan["safety"]["sentinel_absent"] is not True:
        consistency_errors.append("$.safety.sentinel_absent: must be true")
    if plan["safety"]["repo_unchanged"] is not True:
        consistency_errors.append("$.safety.repo_unchanged: must be true")
    if (not v["ok"] or consistency_errors) and not formatter_used:
        repaired, formatter_error = _ollama_format_plan(text)
        formatter_used = True
        if isinstance(repaired, dict):
            obj = repaired
            plan["targets"] = {
                "files": obj.get("targets", {}).get("files", []),
                "symbols": obj.get("targets", {}).get("symbols", []),
            }
            plan["acceptance_criteria"] = obj.get("acceptance_criteria", [])
            plan["required_tests"] = obj.get("required_tests", [])
            plan["risks"] = obj.get("risks", [])
            plan["build_scope"] = {
                "allowed_files": obj.get("build_scope", {}).get("allowed_files", [])
            }
            plan["context"]["research_summary"] = obj.get("research_summary", "")[:4000]
            v = registry.validate(plan, "autodev.plan.v1")
            consistency_errors = _plan_scope_errors(plan)
    if not v["ok"] or consistency_errors:
        errors = list(v["errors"]) + consistency_errors
        if formatter_error:
            errors.insert(0, formatter_error)
        finalize_job(
            job_id,
            "failed",
            error="output contract invalid: %s" % errors[:20],
            failure_class="CONTRACT_FAILURE",
            failure_signature="PLAN_PARSE_FAILED" if parse_failed else "CONTRACT_INVALID",
        )
        return
    plan["x-metadata"] = {
        "backend": backend,
        "semantic_attempt_id": (payload.get("attempt_id") or ""),
        "contract_serialization_pass": formatter_used,
        "formatter_calls": 1 if formatter_used else 0,
    }
    finalize_job(job_id, "completed", result=plan)


def job_build(job_id, run_id, job_type, payload, backend, fixture, timeout_s):
    ws = _ensure_workspace(run_id, payload.get("repository_ref"))
    allowed = payload.get("build_scope", {}).get("allowed_files", []) or payload.get(
        "targets", {}
    ).get("files", [])
    failure_context = payload.get("failure_context") or {}
    strategy = payload.get("strategy_delta")
    prompt = (
        "You are a bounded build worker. Workspace: current directory. "
        "Task: %s\n"
        "Acceptance criteria (must all hold): %s\n"
        "Required tests (must be made to pass): %s\n"
        "You may ONLY create or modify these files: %s\n"
        "Do NOT touch any other file. Do NOT run commands, commit, push, or use the "
        "network. Every file MUST end with a trailing newline.\n"
    ) % (
        payload.get("task_description", ""),
        json.dumps(payload.get("acceptance_criteria", [])),
        json.dumps(payload.get("required_tests", [])),
        json.dumps(allowed),
    )
    if failure_context:
        prompt += (
            "Previous verification failed (failure_class=%s, signature=%s).\n"
            "New evidence:\n%s\n"
        ) % (
            failure_context.get("failure_class"),
            failure_context.get("failure_signature"),
            "\n".join(failure_context.get("new_evidence", []))[:2000],
        )
    if strategy:
        prompt += "Strategy delta: %s\n" % strategy
    prompt += (
        "When done, respond with ONLY a JSON object of this exact shape:\n"
        '{"summary": "<max 800 chars what you changed and why>"}\n'
        "No markdown fences."
    )
    script = _opencode_script(
        ws,
        "build-worker",
        _agent_md(
            "build-worker", BUILD_TOOLS, BUILD_PERMS,
            "Bounded build worker", _worker_identity(payload)[1],
        ),
        prompt,
        timeout_s,
        *_worker_identity(payload),
    )
    r = pct_exec(script, timeout=timeout_s)
    text, events = _parse_opencode_jsonl(ws)
    obj = _extract_json(text)
    changed = pct_stdout(
        "cd '%s' && git status --porcelain 2>/dev/null | "
        "grep -v '^?? .opencode/' | grep -v '^?? local_llm/' | "
        "grep -v '^?? build.jsonl' | grep -v '^?? build.stderr' | head -30" % ws
    )
    files = []
    for line in changed.splitlines():
        line = line.strip()
        if not line:
            continue
        code, path = line[:2], line[3:]
        if code in ("??",):
            change = "add"
        elif code.startswith("M"):
            change = "modify"
        elif code.startswith("D"):
            change = "delete"
        else:
            change = "add"
        size = 0
        sz = pct_stdout("cd '%s' && wc -c < '%s' 2>/dev/null || echo 0" % (ws, path))
        try:
            size = int(sz)
        except ValueError:
            size = 0
        files.append({"path": path, "change": change, "size": size})
    out_of_scope = [
        f["path"]
        for f in files
        if f["path"] not in allowed and not f["path"].startswith((".gitkeep",))
    ]
    summary = (obj or {}).get("summary", "")[:2000] if isinstance(obj, dict) else ""
    status = (
        "failed"
        if (r.returncode != 0 and r.returncode != -9 and not files and not summary)
        else "success"
    )
    result = {
        "contract": "autodev.build-result.v1",
        "version": "v1",
        "run_id": run_id,
        "attempt_id": payload.get("attempt_id"),
        "status": status,
        "changed_files": files[:50],
        "summary": summary,
        "test_results": {"passed": 0, "failed": 0},
        "failure": None
        if not out_of_scope
        else {
            "failure_signature": "OUT_OF_SCOPE_"
            + _sha(",".join(sorted(out_of_scope)))[:16],
            "message": "files outside build_scope modified: %s"
            % ", ".join(out_of_scope[:10]),
        },
    }
    if out_of_scope:
        finalize_job(
            job_id,
            "failed",
            error=result["failure"]["message"],
            failure_class="CONTRACT_FAILURE",
            failure_signature=result["failure"]["failure_signature"],
        )
        return
    v = registry.validate(result, "autodev.build-result.v1")
    if not v["ok"]:
        finalize_job(
            job_id,
            "failed",
            error="output contract invalid: %s" % v["errors"][:2],
            failure_class="CONTRACT_FAILURE",
            failure_signature="CONTRACT_INVALID",
        )
        return
    result["x-metadata"] = {"backend": backend}
    finalize_job(job_id, "completed", result=result)


def job_verify(job_id, run_id, job_type, payload, backend, fixture, timeout_s):
    ws = _ensure_workspace(run_id, payload.get("repository_ref"))
    checks = []
    # unit tests
    test_sys = payload.get("test_system") or "pytest"
    if test_sys == "pytest":
        r = pct_exec(
            "cd '%s' && PYTHONPATH=src python3 -m pytest -q tests 2>&1 | tail -20" % ws,
            timeout=timeout_s,
        )
        passed = r.returncode == 0
        detail = (r.stdout or r.stderr or "")[-1200:]
        checks.append(
            {
                "name": "unit-tests",
                "type": "unit",
                "passed": passed,
                "detail": detail[:2000],
            }
        )
    else:
        r = pct_exec("cd '%s' && node --test 2>&1 | tail -20" % ws, timeout=timeout_s)
        passed = r.returncode == 0
        checks.append(
            {
                "name": "unit-tests",
                "type": "unit",
                "passed": passed,
                "detail": (r.stdout or r.stderr or "")[-1200:][:2000],
            }
        )
    # build/compile
    rb = pct_exec(
        "cd '%s' && python3 -m compileall -q src tests 2>&1 | head -5" % ws,
        timeout=timeout_s,
    )
    checks.append(
        {
            "name": "build-compile",
            "type": "build",
            "passed": rb.returncode == 0,
            "detail": (rb.stdout or rb.stderr or "")[:500],
        }
    )
    # scope invariant
    scope = payload.get("build_scope", {}).get("allowed_files", [])
    changed = pct_stdout(
        "cd '%s' && git status --porcelain 2>/dev/null | "
        "grep -v '.opencode/' | grep -v 'local_llm/' | "
        "grep -v 'build.jsonl' | grep -v 'build.stderr' | "
        "awk '{print $2}'" % ws
    )
    out_scope = [
        f
        for f in changed.splitlines()
        if f
        and f not in scope
        and not f.startswith((".gitkeep", "src/.gitkeep", "tests/.gitkeep"))
    ]
    checks.append(
        {
            "name": "scope-invariant",
            "type": "invariant",
            "passed": not out_scope,
            "detail": "out of scope: %s" % ", ".join(out_scope[:10]),
        }
    )
    all_passed = all(c["passed"] for c in checks)
    failure_class = None
    failure_signature = None
    new_evidence = []
    if not all_passed:
        failing = [c for c in checks if not c["passed"]]
        first = failing[0]
        if first["type"] == "unit":
            failure_class = "TEST_FAILURE"
        elif first["type"] == "build":
            failure_class = "BUILD_FAILURE"
        else:
            failure_class = "CONTRACT_FAILURE"
        essence = (first["name"] + ":" + (first["detail"] or "")[:400]).strip()
        failure_signature = "sig-" + _sha(essence)[:32]
        if failure_class == "TEST_FAILURE":
            # the failing test output IS new evidence for the fix worker
            new_evidence = [
                line.strip()[:500]
                for line in (first["detail"] or "").splitlines()
                if line.strip()
            ][:5]
    result = {
        "contract": "autodev.verification.v1",
        "version": "v1",
        "run_id": run_id,
        "passed": all_passed,
        "checks": checks,
        "failure_class": failure_class,
        "failure_signature": failure_signature,
        "new_evidence": new_evidence,
    }
    v = registry.validate(result, "autodev.verification.v1")
    if not v["ok"]:
        finalize_job(
            job_id,
            "failed",
            error="output contract invalid: %s" % v["errors"][:2],
            failure_class="CONTRACT_FAILURE",
            failure_signature="CONTRACT_INVALID",
        )
        return
    result["x-metadata"] = {"backend": backend}
    finalize_job(job_id, "completed", result=result)


SECRET_PATTERNS = [
    (
        re.compile(
            r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{8,}['\"]"
        ),
        "SEC-001",
    ),
    (
        re.compile(
            r"(?i)(BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36})"
        ),
        "SEC-002",
    ),
    (re.compile(r"(?i)\.env\b"), "SEC-003"),
]
QUALITY_PATTERNS = [
    (re.compile(r"(?i)\bTODO\b|\bFIXME\b|\bHACK\b"), "QUAL-001"),
    (re.compile(r"\bpass\s*$|^\s*except.*:\s*$|^\s*except:\s*$", re.M), "QUAL-002"),
    (
        re.compile(
            r"(?i)eval\(|exec\(|shell=True|subprocess\.\w+\([^)]*shell\s*=\s*True"
        ),
        "SEC-004",
    ),
]


def _changed_file_contents(ws, paths):
    out = {}
    for p in paths[:20]:
        content = pct_stdout("cd '%s' && cat '%s' 2>/dev/null || true" % (ws, p))
        if content:
            out[p] = content
    return out


def job_review(job_id, run_id, job_type, payload, backend, fixture, timeout_s):
    ws = _ensure_workspace(run_id, payload.get("repository_ref"))
    area = job_type.split(".")[1]
    changed = payload.get("changed_files") or []
    contents = _changed_file_contents(ws, [c.get("path", "") for c in changed])
    findings = []
    if area == "correctness":
        test_results = payload.get("test_results") or {}
        if test_results.get("failed"):
            findings.append(
                {
                    "category": "correctness",
                    "severity": "MEDIUM",
                    "confidence": "HIGH",
                    "blocking": False,
                    "rule": "COR-001",
                    "evidence": {"file": "tests", "line_range": "n/a"},
                    "recommendation": "all required tests must pass",
                }
            )
        for path, content in contents.items():
            if not content.endswith("\n"):
                findings.append(
                    {
                        "category": "correctness",
                        "severity": "LOW",
                        "confidence": "HIGH",
                        "blocking": False,
                        "rule": "COR-002",
                        "evidence": {"file": path, "line_range": "last-line"},
                        "recommendation": "file must end with a trailing newline",
                    }
                )
    elif area == "security":
        for path, content in contents.items():
            for i, line in enumerate(content.splitlines(), 1):
                for pat, rule in SECRET_PATTERNS:
                    if pat.search(line):
                        findings.append(
                            {
                                "category": "security",
                                "severity": "CRITICAL",
                                "confidence": "HIGH",
                                "blocking": True,
                                "rule": rule,
                                "evidence": {
                                    "file": path,
                                    "line_range": "%d-%d" % (i, i + 1),
                                },
                                "recommendation": "remove secret material; use the credential store",
                            }
                        )
        for path, content in contents.items():
            for i, line in enumerate(content.splitlines(), 1):
                if re.search(r"(?i)eval\(|exec\(|shell=True", line):
                    findings.append(
                        {
                            "category": "security",
                            "severity": "HIGH",
                            "confidence": "MEDIUM",
                            "blocking": True,
                            "rule": "SEC-004",
                            "evidence": {"file": path, "line_range": str(i)},
                            "recommendation": "avoid eval/exec/shell; use safe alternatives",
                        }
                    )
    else:  # quality
        for path, content in contents.items():
            lines = content.splitlines()
            for i, line in enumerate(lines, 1):
                for pat, rule in QUALITY_PATTERNS:
                    if pat.search(line) and rule.startswith("QUAL"):
                        findings.append(
                            {
                                "category": "quality",
                                "severity": "LOW",
                                "confidence": "MEDIUM",
                                "blocking": False,
                                "rule": rule,
                                "evidence": {"file": path, "line_range": str(i)},
                                "recommendation": "resolve marker or make the exception explicit",
                            }
                        )
            if len(lines) > 200:
                findings.append(
                    {
                        "category": "quality",
                        "severity": "MEDIUM",
                        "confidence": "MEDIUM",
                        "blocking": False,
                        "rule": "QUAL-003",
                        "evidence": {"file": path, "line_range": "1-%d" % len(lines)},
                        "recommendation": "consider splitting large file",
                    }
                )
    blocking = [f for f in findings if f["blocking"]]
    verdict = (
        "FAIL"
        if (blocking or (area == "security" and findings))
        else ("FAIL" if findings and area in ("correctness",) else "PASS")
    )
    result = {
        "contract": "autodev.review-batch.v1",
        "version": "v1",
        "run_id": run_id,
        "reviews": [{"category": area, "verdict": verdict, "findings": findings}],
        "blocked": bool(blocking),
        "blocking_findings": [],
        "parallelism": {"jobs": [], "overlap_proven": False},
    }
    v = registry.validate(result, "autodev.review-batch.v1")
    if not v["ok"]:
        finalize_job(
            job_id,
            "failed",
            error="output contract invalid: %s" % v["errors"][:2],
            failure_class="CONTRACT_FAILURE",
            failure_signature="CONTRACT_INVALID",
        )
        return
    result["x-metadata"] = {"backend": backend}
    finalize_job(job_id, "completed", result=result)


EXECUTORS = {
    "baseline": job_baseline,
    "research.code": job_research,
    "research.docs": job_research,
    "research.tests": job_research,
    "plan": job_plan,
    "build": job_build,
    "fix": job_build,
    "verify": job_verify,
    "review.correctness": job_review,
    "review.security": job_review,
    "review.quality": job_review,
}


def _dispatch(
    run_id,
    job_id,
    job_type,
    attempt_id,
    input_contract,
    payload,
    backend,
    resume_url=None,
    fixture=None,
    timeout_s=None,
    sleep_seconds=None,
    provider=None,
    model=None,
    model_revision=None,
    task_class=None,
    allow_paid_escalation=False,
    paid_escalation_reason=None,
):
    if job_type not in JOB_TYPES:
        return None, err("BAD_JOB_TYPE", "unknown job_type %r" % job_type)
    if backend not in VALID_BACKENDS:
        return None, err("BAD_BACKEND", "unknown backend %r" % backend)
    if not RUN_ID_RE.match(run_id or ""):
        return None, err("BAD_RUN_ID", "invalid run_id")
    if not JOB_ID_RE.match(job_id or ""):
        return None, err("BAD_JOB_ID", "invalid job_id")
    if not JOB_ID_RE.match(attempt_id or ""):
        return None, err("BAD_ATTEMPT_ID", "invalid attempt_id")
    if fixture and fixture not in FIXTURES:
        return None, err("BAD_FIXTURE", "unknown fixture %r" % fixture)
    if is_deepseek_identifier(provider, model):
        return None, err(
            "DEEPSEEK_RETIRED", "DeepSeek is not eligible for Morpheus agent execution"
        )
    if allow_paid_escalation:
        return None, err(
            "PAID_ESCALATION_DISABLED", "automatic paid agent escalation is disabled"
        )
    # HAMH identity fields (optional, backwards compatible). Backend routing
    # is NOT touched by these — they only select the harness profile.
    if provider is not None and not HAMH_ID_RE.match(provider):
        return None, err("BAD_PROVIDER", "invalid provider %r" % provider)
    if model is not None and not HAMH_ID_RE.match(model):
        return None, err("BAD_MODEL", "invalid model %r" % model)
    if model_revision is not None and not HAMH_ID_RE.match(model_revision):
        return None, err("BAD_MODEL_REVISION", "invalid model_revision")
    if task_class is not None and task_class not in HAMH_TASK_CLASSES:
        return None, err("BAD_TASK_CLASS", "unknown task_class %r" % task_class)
    # contract validation at the boundary
    if input_contract not in registry.CONTRACTS:
        return None, err(
            "UNKNOWN_INPUT_CONTRACT", "unknown input_contract %r" % input_contract
        )
    payload = dict(payload)
    metadata = dict(payload.get("x-metadata") or {})
    metadata["execution_provider"] = provider or ("embedded" if backend == "embedded" else "lmstudio")
    metadata["execution_model"] = model or (
        "embedded" if backend == "embedded"
        else (OLLAMA_MODEL if provider == "ollama" else LMSTUDIO_MODEL)
    )
    payload["x-metadata"] = metadata
    v = registry.validate(payload, input_contract)
    if not v["ok"]:
        return None, {
            "status": "error",
            "error": {"code": "CONTRACT_INVALID", "message": "input contract invalid"},
            "contract": input_contract,
            "errors": v["errors"],
            "error_count": v["error_count"],
        }
    # idempotent dispatch FIRST (before any resolution side effects: a
    # rejected/duplicate dispatch must never pollute the resolution artifact)
    with _lock:
        existing = JOBS.get(job_id)
        if existing is not None:
            if (
                existing.get("attempt_id") == attempt_id
                and existing.get("run_id") == run_id
                and existing.get("input_fingerprint") == fp(payload)
            ):
                return existing, None  # duplicate dispatch -> existing job
            return None, err(
                "IDEMPOTENCY_CONFLICT",
                "job_id already used with different attempt/fingerprint",
            )
    effective_task_class = task_class or _task_class_of(job_type)
    route_decision = None
    if (
        _provider_runtime is not None
        and _provider_runtime.enabled
        and backend != "embedded"
        and effective_task_class not in ("baseline", "build", "fix", "plan")
    ):
        preference_provider = (
            provider
            if provider in {"groq", "openrouter", "ollama", "lmstudio"}
            else ""
        )
        preference_model = model if preference_provider else ""
        try:
            route_decision = _provider_runtime.select(
                RouteRequest(
                    provider=preference_provider,
                    model=preference_model,
                    task_class=effective_task_class,
                    privacy_class=payload.get("privacy_class", "ALLOWED"),
                    free_first=True,
                )
            )
        except NoEligibleProvider:
            if preference_provider or os.environ.get(
                "AUTODEV_FREE_FIRST_REQUIRED", "false"
            ).lower() in {"1", "true", "yes"}:
                return None, err(
                    "NO_ELIGIBLE_FREE_PROVIDER", "no eligible free provider"
                )
    harness_provider = (route_decision or {}).get("selected_provider") or provider
    harness_model = (route_decision or {}).get("selected_model") or model
    # deterministic harness resolution at dispatch (HAMH seam, ADR H3).
    # Unknown models fall back to the explicit baseline profile.
    harness_resolution = None
    if hamh_resolver is not None:
        eff_provider = harness_provider or (
            "embedded" if backend == "embedded" else "lmstudio"
        )
        eff_model = harness_model or (
            "embedded" if backend == "embedded" else LMSTUDIO_MODEL
        )
        eff_task_class = effective_task_class
        harness_resolution = hamh_resolver.resolve(
            eff_provider,
            eff_model,
            eff_task_class,
            "auto",
            model_revision=model_revision,
            registry=_hamh_registry,
        )
        _store_resolution_artifact(run_id, job_id, harness_resolution)
    with _lock:
        rec = new_job(
            run_id,
            job_id,
            job_type,
            attempt_id,
            input_contract,
            payload,
            backend,
            resume_url=resume_url,
            fixture=fixture,
            timeout_s=timeout_s,
            sleep_seconds=sleep_seconds,
            provider=harness_provider,
            model=harness_model,
            model_revision=model_revision,
            task_class=task_class
            or (None if hamh_resolver is None else _task_class_of(job_type)),
            harness_resolution=harness_resolution,
            route_decision=route_decision,
        )
        run_job_thread(
            run_id,
            job_id,
            job_type,
            attempt_id,
            input_contract,
            payload,
            backend,
            resume_url=resume_url,
            fixture=fixture,
            timeout_s=timeout_s,
            route_decision=route_decision,
        )
        return rec, None


def _store_resolution_artifact(run_id, job_id, resolution):
    """Aggregate per-run HAMH resolutions in a deterministic artifact
    (metadata-first; no prompts/blobs/secrets). Reuses the existing
    artifact directory and GET /v1/artifacts/<run>/hamh_resolution."""
    if resolution is None:
        return
    path = os.path.join(ARTIFACT_DIR, run_id)
    os.makedirs(path, exist_ok=True)
    file_path = os.path.join(path, "hamh_resolution.json")
    with _lock:
        data = {}
        if os.path.exists(file_path):
            try:
                with open(file_path) as f:
                    data = json.load(f)
            except Exception:
                data = {}
        summary = {
            k: resolution.get(k)
            for k in (
                "resolved_harness_id",
                "harness_version",
                "fingerprint",
                "provider",
                "model",
                "model_revision",
                "task_class",
                "runtime_mode",
                "is_fallback",
            )
        }
        data[job_id] = summary
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())


def _job_view(rec, with_result=True):
    view = {
        k: rec.get(k)
        for k in (
            "run_id",
            "job_id",
            "job_type",
            "attempt_id",
            "status",
            "backend",
            "provider",
            "model",
            "harness_provider",
            "harness_model",
            "route_provider",
            "route_model",
            "route_endpoint",
            "route_account_class",
            "selected_provider",
            "selected_model",
            "routing_event_id",
            "resolved_model",
            "actual_provider",
            "actual_model",
            "usage",
            "actual_cost",
            "free_eligible",
            "execution_proof",
            "failover",
            "model_revision",
            "task_class",
            "harness_id",
            "harness_version",
            "harness_fingerprint",
            "input_contract",
            "input_fingerprint",
            "output_contract",
            "output_fingerprint",
            "started_at",
            "ended_at",
            "duration_ms",
            "failure_class",
            "failure_signature",
            "strategy_delta",
            "result_ref",
            "error",
            "fixture",
        )
    }
    if with_result:
        view["result"] = rec.get("result")
    return view


# ------------------------------------------------------------------ HTTP --
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _auth(self):
        expected = None
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE) as f:
                expected = f.read().strip()
        given_values = self.headers.get_all("X-Harness-Token") or []
        given = given_values[0].strip() if len(given_values) == 1 else ""
        return bool(expected and given and hmac.compare_digest(given, expected))

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return None
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        self.path = urllib.parse.unquote(self.path)
        if self.path == "/healthz":
            with _lock:
                running = sum(1 for r in JOBS.values() if r.get("status") == "running")
                total = len(JOBS)
            self._send(
                200,
                ok(
                    {
                        "status": "ok",
                        "version": VERSION,
                        "jobs_running": running,
                        "jobs_total": total,
                    }
                ),
            )
            return
        if not self._auth():
            self._send(401, err("UNAUTHORIZED", "missing or invalid token"))
            return
        if self.path == "/v1/status/runtime":
            with _lock:
                running_jobs = sum(
                    1 for record in JOBS.values() if record.get("status") == "running"
                )
                running_batches = sum(
                    1 for record in BATCHES.values() if record.get("status") == "running"
                )
            providers = []
            catalog = getattr(_provider_runtime, "catalog", None)
            for entry in (getattr(catalog, "entries", None) or []):
                provider = entry.get("provider")
                if provider in {"deepseek", "groq"}:
                    continue
                providers.append(
                    {
                        "provider": provider,
                        "model": entry.get("model"),
                        "health": entry.get("health", "UNKNOWN"),
                        "availability": "AVAILABLE" if entry.get("route_exists") else "UNKNOWN",
                        "cost_class": entry.get("cost_class", "UNKNOWN"),
                        "free_eligible": bool(entry.get("free_eligible")),
                        "promoted": bool(entry.get("promoted_free_eligible")),
                        "actual_cost_proof": bool(entry.get("actual_cost_proof")),
                        "last_verified_at": entry.get("last_verified_at"),
                        "quarantined": bool(entry.get("quarantined")),
                    }
                )
            self._send(
                200,
                ok(
                    {
                        "adapter_version": VERSION,
                        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                        "jobs_running": running_jobs,
                        "batches_running": running_batches,
                        "free_first_enabled": bool(getattr(_provider_runtime, "enabled", False)),
                        "automatic_paid_agent_escalation": False,
                        "free_pool_size": sum(1 for p in providers if p["free_eligible"]),
                        "providers": providers,
                        "provider_lease_state": "READ_ONLY_SNAPSHOT",
                    }
                ),
            )
            return
        if self.path.startswith("/v1/jobs/"):
            jid = self.path[len("/v1/jobs/") :]
            rec = JOBS.get(jid)
            if rec is None:
                self._send(404, err("NOT_FOUND", "job not found"))
                return
            self._send(200, ok(_job_view(rec)))
            return
        if self.path.startswith("/v1/batches/"):
            bid = self.path[len("/v1/batches/") :]
            brec = BATCHES.get(bid)
            if brec is None:
                self._send(404, err("NOT_FOUND", "batch not found"))
                return
            jobs = [_job_view(JOBS[j]) for j in brec.get("job_ids", []) if j in JOBS]
            self._send(
                200,
                ok(
                    {
                        "batch_id": bid,
                        "status": brec.get("status"),
                        "run_id": brec.get("run_id"),
                        "barrier": brec.get("barrier"),
                        "started_at": brec.get("started_at"),
                        "ended_at": brec.get("ended_at"),
                        "job_count": len(jobs),
                        "jobs": jobs,
                    }
                ),
            )
            return
        if self.path.startswith("/v1/artifacts/"):
            parts = self.path.split("/")  # /v1/artifacts/<run_id>/<name>
            if len(parts) < 5:
                self._send(
                    400, err("BAD_REQUEST", "expected /v1/artifacts/<run_id>/<name>")
                )
                return
            run_id, name = parts[3], parts[4]
            if not RUN_ID_RE.match(run_id) or not re.match(
                r"^[A-Za-z0-9._-]{1,64}$", name
            ):
                self._send(400, err("BAD_REQUEST", "invalid run_id or artifact name"))
                return
            path = os.path.join(ARTIFACT_DIR, run_id, name + ".json")
            if not os.path.exists(path):
                self._send(404, err("NOT_FOUND", "artifact not found"))
                return
            with open(path) as f:
                self._send(200, ok(json.load(f)))
            return
        self._send(404, err("NOT_FOUND", "unknown path"))

    def do_POST(self):
        self.path = urllib.parse.unquote(self.path)
        if not self._auth():
            self._send(401, err("UNAUTHORIZED", "missing or invalid token"))
            return
        try:
            body = self._read_body()
        except Exception:
            self._send(400, err("BAD_REQUEST", "malformed JSON body"))
            return
        if body is None:
            self._send(413, err("TOO_LARGE", "body too large"))
            return
        if self.path == "/v1/jobs":
            rec, e = _dispatch(
                body.get("run_id"),
                body.get("job_id"),
                body.get("job_type"),
                body.get("attempt_id"),
                body.get("input_contract"),
                body.get("input") or {},
                body.get("backend") or "embedded",
                resume_url=body.get("resume_url"),
                fixture=body.get("fixture"),
                timeout_s=body.get("timeout_s"),
                sleep_seconds=body.get("sleep_seconds"),
                provider=body.get("provider"),
                model=body.get("model"),
                model_revision=body.get("model_revision"),
                task_class=body.get("task_class"),
                allow_paid_escalation=body.get("allow_paid_escalation", False),
                paid_escalation_reason=body.get("paid_escalation_reason"),
            )
            if e is not None:
                self._send(
                    400 if e.get("error", {}).get("code") != "UNAUTHORIZED" else 401, e
                )
                return
            resp = {
                "job_id": rec["job_id"],
                "status": rec["status"],
                "run_id": rec["run_id"],
                "job_type": rec["job_type"],
                "attempt_id": rec["attempt_id"],
                "duplicate": rec.get("status") != "queued" and False,
            }
            res = rec.get("harness_resolution")
            if res:
                resp["harness"] = {
                    "resolved_harness_id": res.get("resolved_harness_id"),
                    "harness_version": res.get("harness_version"),
                    "fingerprint": res.get("fingerprint"),
                    "is_fallback": res.get("is_fallback"),
                }
            self._send(202, ok(resp))
            return
        if self.path == "/v1/batches":
            batch_id = body.get("batch_id")
            run_id = body.get("run_id")
            jobs = body.get("jobs") or []
            barrier = body.get("barrier") or "all"
            if not batch_id or not RUN_ID_RE.match(run_id or "") or not jobs:
                self._send(
                    400, err("BAD_REQUEST", "batch_id, run_id and jobs required")
                )
                return
            with _lock:
                if batch_id in BATCHES:
                    self._send(
                        200,
                        ok(
                            {
                                "batch_id": batch_id,
                                "status": BATCHES[batch_id]["status"],
                                "duplicate": True,
                            }
                        ),
                    )
                    return
                brec = {
                    "batch_id": batch_id,
                    "run_id": run_id,
                    "barrier": barrier,
                    "job_ids": [j.get("job_id") for j in jobs],
                    "status": "running",
                    "started_at": _now(),
                    "ended_at": None,
                }
                BATCHES[batch_id] = brec
                _log_batch(dict(brec))
            dispatched, errors = [], []
            for j in jobs:
                rec, e = _dispatch(
                    run_id,
                    j.get("job_id"),
                    j.get("job_type"),
                    j.get("attempt_id"),
                    j.get("input_contract"),
                    j.get("input") or {},
                    j.get("backend") or "embedded",
                    resume_url=j.get("resume_url"),
                    fixture=j.get("fixture"),
                    timeout_s=j.get("timeout_s"),
                    sleep_seconds=j.get("sleep_seconds"),
                    provider=j.get("provider"),
                    model=j.get("model"),
                    model_revision=j.get("model_revision"),
                    task_class=j.get("task_class"),
                    allow_paid_escalation=j.get("allow_paid_escalation", False),
                    paid_escalation_reason=j.get("paid_escalation_reason"),
                )
                if e is not None:
                    errors.append({"job_id": j.get("job_id"), "error": e})
                else:
                    dispatched.append(rec["job_id"])

            # barrier watcher
            def watch():
                while True:
                    with _lock:
                        recs = [
                            JOBS[j] for j in BATCHES[batch_id]["job_ids"] if j in JOBS
                        ]
                    if recs and all(
                        r.get("status") in ("completed", "failed", "interrupted")
                        for r in recs
                    ):
                        break
                    time.sleep(0.5)
                with _lock:
                    BATCHES[batch_id]["status"] = "completed"
                    BATCHES[batch_id]["ended_at"] = _now()
                _log_batch(
                    {
                        "batch_id": batch_id,
                        "status": "completed",
                        "ended_at": BATCHES[batch_id]["ended_at"],
                        "ts": _now(),
                    }
                )

            threading.Thread(target=watch, daemon=True).start()
            self._send(
                202,
                ok(
                    {
                        "batch_id": batch_id,
                        "status": "running",
                        "job_ids": dispatched,
                        "errors": errors,
                    }
                ),
            )
            return
        if self.path.startswith("/v1/artifacts/"):
            parts = self.path.split("/")
            if len(parts) < 5:
                self._send(
                    400, err("BAD_REQUEST", "expected /v1/artifacts/<run_id>/<name>")
                )
                return
            run_id, name = parts[3], parts[4]
            if not RUN_ID_RE.match(run_id) or not re.match(
                r"^[A-Za-z0-9._-]{1,64}$", name
            ):
                self._send(400, err("BAD_REQUEST", "invalid run_id or artifact name"))
                return
            path = os.path.join(ARTIFACT_DIR, run_id)
            os.makedirs(path, exist_ok=True)
            with open(os.path.join(path, name + ".json"), "w") as f:
                json.dump(body.get("artifact", {}), f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            ref = "%s/v1/artifacts/%s/%s" % (CANONICAL_URL, run_id, name)
            self._send(201, ok({"ref": ref}))
            return
        self._send(404, err("NOT_FOUND", "unknown path"))


def main():
    _load()
    if not os.path.exists(TOKEN_FILE):
        import secrets

        with open(TOKEN_FILE, "w") as f:
            f.write(secrets.token_urlsafe(48))
        os.chmod(TOKEN_FILE, 0o600)
    srv = ThreadingHTTPServer((BIND_HOST, BIND_PORT), Handler)
    print("autodev-harness-v2 listening on %s:%d" % (BIND_HOST, BIND_PORT), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
