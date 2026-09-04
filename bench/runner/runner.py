#!/usr/bin/env python3
"""Reproducible MorpheusBench runner.

The runner is deliberately a thin benchmark client: n8n remains the only
control plane.  It validates and freezes task material locally, then starts
each run through ``/webhook/autodev/start`` and reads results back through the
canonical status/adapter projections.  No shell command is built from task
fields and no holdout file is loaded during development/validation runs.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from runtime.contracts import registry

ROOT = Path(__file__).resolve().parents[2]
TASK_ROOT = ROOT / "bench" / "tasks"
FIXTURE_ROOT = ROOT / "bench" / "fixtures"
DEFAULT_EVIDENCE = ROOT / "evidence" / "morpheus-bench"
CONTRACT = "autodev.benchmark-task.v1"
FACTORS = (
    "BASELINE",
    "CONTEXT_COMPILER",
    "CONTEXT_PLUS_EXPLORER",
    "EXPERIENCE_TOP1",
    "EXPERIENCE_TOP3",
)
SPLITS = ("development", "validation", "holdout")
TASK_SECURITY_PATTERNS = (
    ("TASK_POLICY_OVERRIDE", r"\bignore\s+(?:all\s+)?(?:previous|prior|system)\b"),
    ("TASK_HTML_PAYLOAD", r"<\s*(?:script|iframe|img|svg)\b|\bjavascript:|\bon\w+\s*="),
    ("TASK_MERMAID_PAYLOAD", r"\b(?:flowchart|sequenceDiagram|classDiagram|graph\s+(?:TD|LR))\b"),
    ("TASK_ROUTE_POLICY", r"\bdeepseek\b|\bpaid\b|\bbillable\b|automatic[_ -]?paid"),
    ("TASK_ARBITRARY_SHELL", r"\$\(|`[^`]+`|\b(?:bash|sh|powershell|cmd)\s+-c\b|\b(?:subprocess|os\.system)\b"),
    ("TASK_NETWORK_POLICY", r"\b(?:https?|ssh|curl|wget|socket)://|\b(?:network|internet)\b"),
    ("TASK_SECRET_READ", r"(?:/etc/|/proc/|/var/run/|\.env\b|\b(?:secret|password|token|private key|ssh key)\b)"),
)
TERMINAL_STATES = {"DONE", "PLAN_BLOCKED", "BLOCKED", "FAILED", "SPLIT_REQUIRED", "ABORTED"}
POLICIES = {
    "BASELINE": ("disabled", "disabled", "disabled"),
    "CONTEXT_COMPILER": ("compiler-v1", "disabled", "disabled"),
    "CONTEXT_PLUS_EXPLORER": ("compiler-v1", "read-only-v1", "disabled"),
    "EXPERIENCE_TOP1": ("compiler-v1", "read-only-v1", "verified-top1-v1"),
    "EXPERIENCE_TOP3": ("compiler-v1", "read-only-v1", "verified-top3-v1"),
}


class BenchmarkError(RuntimeError):
    """A fail-closed benchmark input, safety, or execution error."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def safe_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise BenchmarkError("TASK_PATH_INVALID")
    if value.startswith(("/", "\\")) or "\\" in value:
        raise BenchmarkError("TASK_PATH_INVALID")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts) or ".git" in parts:
        raise BenchmarkError("TASK_PATH_ESCAPE")
    return value


def load_fixture(fixture_ref: str) -> tuple[dict[str, str], str]:
    safe_relative_path(fixture_ref)
    if not fixture_ref.startswith("repos/") or not fixture_ref.endswith(".json"):
        raise BenchmarkError("FIXTURE_REF_INVALID")
    path = FIXTURE_ROOT / fixture_ref
    try:
        path.resolve().relative_to(FIXTURE_ROOT.resolve())
    except ValueError as exc:
        raise BenchmarkError("FIXTURE_PATH_ESCAPE") from exc
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError("FIXTURE_UNREADABLE") from exc
    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(files, dict) or not files or len(files) > 64:
        raise BenchmarkError("FIXTURE_FILES_INVALID")
    normalized: dict[str, str] = {}
    for name, content in sorted(files.items()):
        safe_relative_path(name)
        if not isinstance(content, str) or len(content.encode("utf-8")) > 128 * 1024:
            raise BenchmarkError("FIXTURE_CONTENT_INVALID")
        normalized[name] = content
    return normalized, sha256_json({"files": normalized})


def task_hash(task: dict[str, Any]) -> str:
    unsigned = dict(task)
    unsigned.pop("task_hash", None)
    return sha256_json(unsigned)


def validate_task_security(task: dict[str, Any]) -> None:
    """Reject hostile task content before it can reach a canonical run."""
    content = canonical_json({
        key: task.get(key)
        for key in ("instruction", "input", "acceptance_criteria", "verifier")
    })
    for code, pattern in TASK_SECURITY_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            raise BenchmarkError(code)


def load_task(path: Path, split: str) -> dict[str, Any]:
    try:
        task = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"TASK_UNREADABLE:{path.name}") from exc
    if not isinstance(task, dict) or task.get("split") != split:
        raise BenchmarkError(f"TASK_SPLIT_MISMATCH:{path.name}")
    required = {"contract", "version", "task_id", "split", "task_class", "instruction", "input", "setup", "execution_mode", "allowed_tools", "forbidden_actions", "acceptance_criteria", "verifier", "timeout_seconds", "max_attempts", "mutation_policy", "cleanup", "expected_failure_classes", "fixture_hash", "task_hash"}
    missing = sorted(required - set(task))
    if missing:
        raise BenchmarkError(f"TASK_FIELDS_MISSING:{path.name}:{','.join(missing)}")
    if task["contract"] != CONTRACT or task["version"] != "v1":
        raise BenchmarkError(f"TASK_CONTRACT_INVALID:{path.name}")
    contract_result = registry.validate(task, CONTRACT)
    if not contract_result["ok"]:
        raise BenchmarkError(f"TASK_SCHEMA_INVALID:{path.name}:{contract_result['errors'][:5]}")
    if task["task_class"] not in {"STRUCTURED_OUTPUT", "REPOSITORY_NAVIGATION", "READ_ONLY_ANALYSIS", "TOOL_SELECTION", "SMALL_CODE_CHANGE", "FAILURE_RECOVERY"}:
        raise BenchmarkError(f"TASK_CLASS_INVALID:{path.name}")
    if task["execution_mode"] == "read_only" and task["mutation_policy"].get("scope") != "none":
        raise BenchmarkError(f"TASK_READ_ONLY_MUTATION_POLICY:{path.name}")
    if task["execution_mode"] == "fixture_mutation" and task["mutation_policy"].get("scope") != "fixture_only":
        raise BenchmarkError(f"TASK_FIXTURE_MUTATION_POLICY:{path.name}")
    if task["mutation_policy"].get("production_mutation") is not False:
        raise BenchmarkError(f"TASK_PRODUCTION_MUTATION:{path.name}")
    if task["cleanup"].get("required") is not True:
        raise BenchmarkError(f"TASK_CLEANUP_REQUIRED:{path.name}")
    validate_task_security(task)
    files, fixture_digest = load_fixture(task["setup"]["fixture_ref"])
    if task["fixture_hash"] != fixture_digest:
        raise BenchmarkError(f"FIXTURE_HASH_MISMATCH:{path.name}")
    if task["task_hash"] != task_hash(task):
        raise BenchmarkError(f"TASK_HASH_MISMATCH:{path.name}")
    result = copy.deepcopy(task)
    result["_fixture_files"] = files
    result["_source_path"] = str(path.relative_to(ROOT))
    return result


def load_task_set(split: str, *, allow_holdout: bool = False) -> list[dict[str, Any]]:
    if split not in SPLITS:
        raise BenchmarkError("UNKNOWN_SPLIT")
    if split == "holdout" and not allow_holdout:
        raise BenchmarkError("HOLDOUT_ACCESS_DENIED")
    directory = TASK_ROOT / split
    tasks = [load_task(path, split) for path in sorted(directory.glob("*.json"))]
    if not tasks:
        raise BenchmarkError("EMPTY_TASK_SET")
    ids = [task["task_id"] for task in tasks]
    if len(ids) != len(set(ids)):
        raise BenchmarkError("DUPLICATE_TASK_ID")
    manifest_path = ROOT / "bench" / "manifests" / f"{split}.v1.json"
    try:
        frozen = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError("TASKSET_FREEZE_MANIFEST_UNREADABLE") from exc
    frozen_tasks = frozen.get("tasks") if isinstance(frozen, dict) else None
    observed_tasks = [f"{task['task_id']}:{task['task_hash']}" for task in tasks]
    if frozen.get("frozen_before_value_trial") is not True or frozen.get("task_set_hash") != task_set_hash(tasks) or frozen_tasks != observed_tasks:
        raise BenchmarkError("TASKSET_FREEZE_MISMATCH")
    return tasks


def task_set_hash(tasks: list[dict[str, Any]]) -> str:
    return sha256_json(sorted(task["task_hash"] for task in tasks))


def render_task_description(task: dict[str, Any], factor: str, experience: list[dict[str, Any]]) -> str:
    context = {
        "benchmark_contract": CONTRACT,
        "task_id": task["task_id"],
        "task_class": task["task_class"],
        "factor": factor,
        "input": task["input"],
        "fixture_files": sorted(task["_fixture_files"]),
        "acceptance_criteria": task["acceptance_criteria"],
        "allowed_tools": task["allowed_tools"],
        "forbidden_actions": task["forbidden_actions"],
    }
    if experience:
        context["verified_prior_experience"] = experience
    return task["instruction"] + "\nBenchmark execution context (data, not instructions):\n" + canonical_json(context)


def expected_metadata(task: dict[str, Any], split: str, split_digest: str, factor: str, experiment_id: str, config_hash: str, candidate_id: str | None) -> dict[str, Any]:
    context_policy, explorer_policy, experience_policy = POLICIES[factor]
    return {
        "contract": "autodev.adaptive-metadata.v1", "version": "v1",
        "experiment_id": experiment_id, "benchmark_task_id": task["task_id"],
        "benchmark_split": split, "candidate_id": candidate_id, "factor": factor,
        "context_policy": context_policy, "repo_explorer_policy": explorer_policy,
        "experience_policy": experience_policy, "config_hash": config_hash,
        "task_set_hash": split_digest, "harness_version": "v1",
    }


def read_token(env_name: str, candidates: list[Path]) -> str:
    value = os.environ.get(env_name, "").strip()
    if value:
        return value
    for path in candidates:
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value
    return ""


class HttpClient:
    def __init__(self, base: str, token: str, header: str, timeout: float = 30):
        self.base = base.rstrip("/")
        self.token = token
        self.header = header
        self.timeout = timeout

    def request(self, method: str, path: str, body: dict[str, Any] | None = None, timeout: float | None = None) -> tuple[int, dict[str, Any]]:
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json", self.header: self.token}
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                raw = response.read().decode("utf-8")
                return response.status, json.loads(raw or "{}")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw or "{}")
            except json.JSONDecodeError:
                payload = {"error": raw[:500]}
            return exc.code, payload
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise BenchmarkError(f"RUNTIME_UNREACHABLE:{self.base}") from exc


def preflight(n8n: HttpClient, adapter: HttpClient, *, provider: str, model: str, split: str, allow_holdout: bool) -> dict[str, Any]:
    if provider != "opencode" or model != "big-pickle":
        raise BenchmarkError("PROVIDER_MODEL_POLICY_DENY")
    if "deepseek" in (provider + "/" + model).lower():
        raise BenchmarkError("DEEPSEEK_ROUTE_DENY")
    if split == "holdout" and not allow_holdout:
        raise BenchmarkError("HOLDOUT_ACCESS_DENIED")
    status, health = n8n.request("GET", "/healthz", timeout=10)
    if status != 200 or health.get("status") != "ok":
        raise BenchmarkError("N8N_UNHEALTHY")
    status, health = adapter.request("GET", "/healthz", timeout=10)
    if status != 200 or health.get("status") != "ok":
        raise BenchmarkError("ADAPTER_UNHEALTHY")
    status, runtime = adapter.request("GET", "/v1/status/runtime", timeout=15)
    if status != 200:
        raise BenchmarkError("ADAPTER_RUNTIME_STATUS_UNAVAILABLE")
    runtime = runtime.get("data", runtime) if isinstance(runtime, dict) else {}
    if runtime.get("automatic_paid_agent_escalation") is not False:
        raise BenchmarkError("AUTOMATIC_PAID_ESCALATION_NOT_DISABLED")
    entries = runtime.get("providers") or []
    matching = [entry for entry in entries if entry.get("provider") == provider and entry.get("model") == model]
    if not matching or not any(entry.get("free_eligible") and entry.get("cost_class") in {"FREE_HARD_STOP", "LOCAL_ZERO_COST"} and entry.get("health") == "HEALTHY" for entry in matching):
        raise BenchmarkError("ZERO_COST_ROUTE_NOT_PROVEN")
    if any("deepseek" in json.dumps(entry).lower() for entry in entries):
        raise BenchmarkError("DEEPSEEK_CATALOG_CONTAMINATION")
    return {"n8n": "PASS", "adapter": "PASS", "zero_cost_route": "PASS", "provider": provider, "model": model, "runtime": runtime}


def experience_for(tasks: list[dict[str, Any]], evidence_dir: Path, task: dict[str, Any], factor: str) -> list[dict[str, Any]]:
    if factor not in {"EXPERIENCE_TOP1", "EXPERIENCE_TOP3"}:
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(evidence_dir.glob("**/*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if record.get("split") != "development" or record.get("verification_result") != "PASS":
            continue
        if record.get("task_id") == task["task_id"] or record.get("task_id") not in {item["task_id"] for item in tasks}:
            continue
        entries.append({"task_id": record["task_id"], "task_class": record.get("task_class"), "lesson": record.get("failure_class") or "verified successful bounded strategy"})
    if not entries:
        raise BenchmarkError("EXPERIENCE_SOURCE_EMPTY")
    return entries[: (1 if factor == "EXPERIENCE_TOP1" else 3)]


def local_fixture_verifier(task: dict[str, Any], root: Path) -> tuple[bool, str]:
    verifier = task["verifier"]
    if verifier["type"] != "fixture_diff":
        return True, "NOT_APPLICABLE"
    expected = verifier.get("expected_files") or {}
    for relative, content in expected.items():
        safe_relative_path(relative)
        actual_path = root / relative
        try:
            actual_path.resolve().relative_to(root.resolve())
            actual = actual_path.read_text(encoding="utf-8")
        except (OSError, ValueError) as exc:
            return False, f"FIXTURE_READ_FAILED:{relative}:{exc}"
        if actual != content:
            return False, f"FIXTURE_EXPECTED_DIFF_NOT_APPLIED:{relative}"
    return True, "PASS"


def materialize_local_fixture(task: dict[str, Any]) -> Path:
    directory = Path(tempfile.mkdtemp(prefix="morpheus-bench-"))
    for relative, content in task["_fixture_files"].items():
        safe_relative_path(relative)
        destination = directory / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    return directory


def _job(adapter: HttpClient, run_id: str, job_type: str, number: int = 1) -> dict[str, Any]:
    path = "/v1/jobs/" + urllib.parse.quote(f"{run_id}:{job_type}:{number}", safe="")
    status, payload = adapter.request("GET", path, timeout=15)
    return payload.get("data") if status == 200 and isinstance(payload.get("data"), dict) else {}


def verify_canonical(task: dict[str, Any], state: dict[str, Any], jobs: list[dict[str, Any]], metadata: dict[str, Any]) -> tuple[str, str]:
    expected_route = (metadata.get("expected_provider", "opencode"), metadata.get("expected_model", "big-pickle"))
    route_jobs = [job for job in jobs if job.get("job_type") in {"baseline", "research.code", "research.docs", "research.tests", "plan", "build", "verify"}]
    for job in route_jobs:
        selected = (job.get("selected_provider"), job.get("selected_model"))
        actual = (job.get("actual_provider"), job.get("actual_model"))
        if selected != expected_route or actual != selected:
            return "FAIL", "ROUTE_IDENTITY_MISMATCH"
    expected_state = task["verifier"].get("required_state", "DONE")
    if state.get("state") != expected_state:
        return "FAIL", f"TERMINAL_STATE:{state.get('state')}"
    observed = [job.get("adaptive_metadata") for job in jobs if job.get("adaptive_metadata")]
    if observed and any(item != metadata for item in observed):
        return "FAIL", "ADAPTIVE_METADATA_CORRELATION"
    plan = next((job.get("result") for job in jobs if job.get("job_type") == "plan" and isinstance(job.get("result"), dict)), None)
    if task["verifier"]["type"] in {"plan_contract", "repository_evidence"}:
        if not isinstance(plan, dict) or plan.get("contract") != "autodev.plan.v1":
            return "FAIL", "PLAN_RESULT_MISSING_OR_INVALID"
        files = set((plan.get("targets") or {}).get("files") or [])
        if not set(task["verifier"].get("required_files", [])).issubset(files):
            return "FAIL", "REPOSITORY_EVIDENCE_FILES_MISSING"
        symbols = set((plan.get("targets") or {}).get("symbols") or [])
        required_symbols = set(task["verifier"].get("required_symbols", []))
        if required_symbols and not required_symbols.issubset(symbols):
            return "FAIL", "REPOSITORY_EVIDENCE_SYMBOLS_MISSING"
    if task["verifier"]["type"] == "fixture_diff":
        build = next((job.get("result") for job in jobs if job.get("job_type") == "build" and isinstance(job.get("result"), dict)), None)
        changed = {item.get("path") for item in (build or {}).get("changed_files", [])}
        allowed = set(task["mutation_policy"].get("allowed_paths", []))
        if not changed or not changed.issubset(allowed):
            return "FAIL", "FIXTURE_DIFF_SCOPE_OR_EMPTY"
    return "PASS", "PASS"


def run_one(task: dict[str, Any], *, split: str, split_digest: str, factor: str, experiment_id: str, candidate_id: str | None, n8n: HttpClient, adapter: HttpClient, evidence_dir: Path, provider: str, model: str, repository_ref: str, max_wait: int, experience: list[dict[str, Any]]) -> dict[str, Any]:
    config = {"provider": provider, "model": model, "factor": factor, "policies": POLICIES[factor], "max_attempts": task["max_attempts"], "timeout_seconds": task["timeout_seconds"], "verifier": task["verifier"], "runtime_generation": "canonical-n8n"}
    config_digest = sha256_json(config)
    metadata = expected_metadata(task, split, split_digest, factor, experiment_id, config_digest, candidate_id)
    identity = f"{experiment_id}:{task['task_id']}:{factor}:{config_digest}"
    result_path = evidence_dir / "runs" / (identity.replace(":", "_") + ".json")
    if result_path.exists():
        existing = json.loads(result_path.read_text(encoding="utf-8"))
        if existing.get("identity") != identity:
            raise BenchmarkError("IDEMPOTENCY_IDENTITY_COLLISION")
        existing["replay"] = "REPLAY_EXISTING"
        return existing
    if split == "holdout" and any("holdout" in path.parts for path in evidence_dir.glob("**/*")):
        raise BenchmarkError("HOLDOUT_EXPERIENCE_LEAKAGE")
    local_fixture = materialize_local_fixture(task)
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    run_id = "run-mb-" + hashlib.sha256(identity.encode()).hexdigest()[:20]
    wire_task = {
        "run_id": run_id, "task_ref": f"morpheusbench:{split}:{task['task_id']}",
        "repository_ref": repository_ref, "workspace": f"morpheusbench-{task['task_id']}",
        "task_description": render_task_description(task, factor, experience),
        "acceptance_hint": canonical_json({"verifier": task["verifier"], "task_hash": task["task_hash"], "fixture_hash": task["fixture_hash"]}) + "\nBENCHMARK_FIXTURE_JSON:" + canonical_json({"files": task["_fixture_files"]}),
        "max_attempts": task["max_attempts"], "changes_expected": task["execution_mode"] == "fixture_mutation",
        "no_change_required": task["execution_mode"] == "read_only", "x-metadata": {
            "adaptive_metadata": metadata,
            "route_policy": "FAIL_CLOSED",
            "expected_provider": provider,
            "expected_model": model,
        },
    }
    body = {"task": wire_task, "provider": provider, "model": model, "backend": "opencode-builder-8001", "adaptive_metadata": metadata, "benchmark_fixture": {"files": task["_fixture_files"]}}
    status_code = None
    terminal: dict[str, Any] = {}
    failure = None
    try:
        status_code, response = n8n.request("POST", "/webhook/autodev/start", body, timeout=30)
        if status_code not in (200, 202) or response.get("run_id") != run_id:
            raise BenchmarkError("CANONICAL_N8N_INTAKE_FAILED")
        deadline = time.monotonic() + max_wait
        while time.monotonic() < deadline:
            _, terminal = n8n.request("GET", "/webhook/autodev/status?run_id=" + urllib.parse.quote(run_id, safe="-"), timeout=15)
            if terminal.get("state") in TERMINAL_STATES:
                break
            time.sleep(5)
        if terminal.get("state") not in TERMINAL_STATES:
            raise BenchmarkError("CANONICAL_RUN_TIMEOUT")
        jobs = [_job(adapter, run_id, job_type) for job_type in ("baseline", "research", "plan", "build", "verify", "review")]
        jobs = [job for job in jobs if job]
        actual_costs = [job.get("actual_cost") for job in jobs if job.get("actual_cost") is not None]
        if any(float(cost) != 0 for cost in actual_costs):
            raise BenchmarkError("PAID_REQUEST_DETECTED")
        verification, detail = verify_canonical(task, terminal, jobs, metadata)
        metrics = {"input_tokens": "UNKNOWN", "output_tokens": "UNKNOWN", "total_tokens": "UNKNOWN", "tool_calls": "UNKNOWN", "search_calls": "UNKNOWN", "retries": "UNKNOWN", "wall_clock_ms": "UNKNOWN", "first_pass_success": verification == "PASS", "task_success": verification == "PASS", "verification_pass": verification == "PASS"}
        if jobs:
            durations = [job.get("duration_ms") for job in jobs if isinstance(job.get("duration_ms"), int)]
            if durations:
                metrics["wall_clock_ms"] = sum(durations)
        record = {"identity": identity, "experiment_id": experiment_id, "task_id": task["task_id"], "task_class": task["task_class"], "task_hash": task["task_hash"], "fixture_hash": task["fixture_hash"], "split": split, "factor": factor, "config_hash": config_digest, "run_id": run_id, "project_id": terminal.get("project_id", "UNKNOWN"), "correlation_id": terminal.get("correlation_id", "UNKNOWN"), "provider": provider, "model": model, "actual_provider": next((job.get("actual_provider") for job in jobs if job.get("actual_provider")), "UNKNOWN"), "actual_model": next((job.get("actual_model") for job in jobs if job.get("actual_model")), "UNKNOWN"), "actual_cost": 0 if actual_costs else "UNKNOWN", "started_at": started, "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(), "terminal_state": terminal.get("state"), "verification_result": verification, "failure_class": None if verification == "PASS" else detail, "metrics": metrics, "adaptive_metadata": metadata, "result_hash": ""}
        route_job = next((job for job in jobs if job.get("actual_provider") or job.get("actual_model")), {})
        record.update({
            "requested_provider": provider,
            "requested_model": model,
            "selected_provider": route_job.get("selected_provider", "UNKNOWN"),
            "selected_model": route_job.get("selected_model", "UNKNOWN"),
            "route_match": detail != "ROUTE_IDENTITY_MISMATCH" and verification == "PASS",
        })
    except BenchmarkError as exc:
        failure = str(exc)
        record = {"identity": identity, "experiment_id": experiment_id, "task_id": task["task_id"], "task_class": task["task_class"], "task_hash": task["task_hash"], "fixture_hash": task["fixture_hash"], "split": split, "factor": factor, "config_hash": config_digest, "run_id": run_id if status_code in (200, 202) else "UNKNOWN", "provider": provider, "model": model, "requested_provider": provider, "requested_model": model, "selected_provider": "UNKNOWN", "selected_model": "UNKNOWN", "actual_provider": "UNKNOWN", "actual_model": "UNKNOWN", "route_match": False, "actual_cost": "UNKNOWN", "started_at": started, "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(), "terminal_state": terminal.get("state", "UNKNOWN"), "verification_result": "ABORTED", "failure_class": failure, "metrics": {"input_tokens": "UNKNOWN", "output_tokens": "UNKNOWN", "total_tokens": "UNKNOWN", "tool_calls": "UNKNOWN", "search_calls": "UNKNOWN", "retries": "UNKNOWN", "wall_clock_ms": "UNKNOWN", "first_pass_success": "UNKNOWN", "task_success": "UNKNOWN", "verification_pass": "UNKNOWN"}, "adaptive_metadata": metadata}
    finally:
        shutil.rmtree(local_fixture, ignore_errors=False)
    record["result_hash"] = sha256_json({key: value for key, value in record.items() if key != "result_hash"})
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return record


def run_batch(args: argparse.Namespace) -> list[dict[str, Any]]:
    allow_holdout = args.split == "holdout" and args.phase == "holdout"
    tasks = load_task_set(args.split, allow_holdout=allow_holdout)
    split_hash = task_set_hash(tasks)
    if args.task_id:
        selected = [task for task in tasks if task["task_id"] == args.task_id]
        if not selected:
            raise BenchmarkError("TASK_ID_NOT_IN_SPLIT")
        tasks = selected
    evidence_dir = Path(args.evidence_dir).resolve()
    if args.optimizer and args.split == "holdout":
        raise BenchmarkError("OPTIMIZER_HOLDOUT_DENY")
    if args.factor not in FACTORS:
        raise BenchmarkError("UNKNOWN_FACTOR")
    n8n_token = read_token("MORPHEUS_N8N_TOKEN", [ROOT / ".secrets" / "autodev_api_token"])
    adapter_token = read_token("MORPHEUS_HARNESS_TOKEN", [Path("/var/lib/autodev-harness-v2/token"), ROOT / ".secrets" / "harness_token_v2", ROOT / ".secrets" / "harness_token"])
    if not n8n_token or not adapter_token:
        raise BenchmarkError("RUNTIME_TOKEN_UNAVAILABLE")
    n8n = HttpClient(args.n8n_url, n8n_token, "X-AutoDev-Token")
    adapter = HttpClient(args.adapter_url, adapter_token, "X-Harness-Token")
    preflight(n8n, adapter, provider=args.provider, model=args.model, split=args.split, allow_holdout=allow_holdout)
    experience_tasks = [] if args.split == "holdout" else tasks
    results = []
    for task in tasks:
        experience = experience_for(experience_tasks, evidence_dir, task, args.factor)
        results.append(run_one(task, split=args.split, split_digest=split_hash, factor=args.factor, experiment_id=args.experiment_id, candidate_id=args.candidate_id, n8n=n8n, adapter=adapter, evidence_dir=evidence_dir, provider=args.provider, model=args.model, repository_ref=args.repository_ref, max_wait=args.max_wait, experience=experience))
    manifest = {"experiment_id": args.experiment_id, "head": os.environ.get("MORPHEUS_BENCH_HEAD", "UNKNOWN"), "task_set_hash": split_hash, "split": args.split, "factor": args.factor, "provider": args.provider, "model": args.model, "config_hashes": sorted({result["config_hash"] for result in results}), "started_at": results[0]["started_at"] if results else None, "finished_at": results[-1]["finished_at"] if results else None, "result_hash": sha256_json(results), "runtime_versions": {"n8n": "UNKNOWN", "control_tower": "UNKNOWN", "adapter": "UNKNOWN"}}
    manifest_dir = evidence_dir / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"{args.experiment_id}-{args.split}-{args.factor}.json"
    if manifest_path.exists() and manifest_path.read_text(encoding="utf-8") != json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n":
        raise BenchmarkError("MANIFEST_IMMUTABILITY_VIOLATION")
    if not manifest_path.exists():
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return results


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=SPLITS, required=True)
    parser.add_argument("--factor", choices=FACTORS, required=True)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--candidate-id")
    parser.add_argument("--task-id", help="Run exactly one task; useful for bounded smoke tests")
    parser.add_argument("--phase", choices=("development", "validation", "holdout"), default="development")
    parser.add_argument("--provider", default="opencode")
    parser.add_argument("--model", default="big-pickle")
    parser.add_argument("--repository-ref", default="xxammaxx/Morpheus_workflow")
    parser.add_argument("--n8n-url", default="http://192.168.1.52:5678")
    parser.add_argument("--adapter-url", default="http://192.168.1.136:8081")
    parser.add_argument("--evidence-dir", default=str(DEFAULT_EVIDENCE))
    parser.add_argument("--max-wait", type=int, default=900)
    parser.add_argument("--optimizer", action="store_true")
    return parser


def main() -> int:
    args = parser().parse_args()
    try:
        results = run_batch(args)
    except BenchmarkError as exc:
        print(json.dumps({"status": "ABORTED", "failure_class": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({"status": "PASS" if all(item.get("verification_result") == "PASS" for item in results) else "NO_VALUE_OR_FAILURE", "tasks": len(results), "results": results}, ensure_ascii=False, sort_keys=True))
    return 0 if all(item.get("verification_result") == "PASS" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
