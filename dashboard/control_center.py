"""Pure control-center policies and projections.

This module deliberately has no persistence and no execution side effects.  It
keeps the browser-facing BFF honest: n8n remains the command authority and
Data Tables remain the system of record.
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import urlparse


NO_SECOND_CONTROL_PLANE = True
NO_SECOND_RUN_STATE_SOR = True
RUNTIME_DASHBOARD_WRITES = 0
MORPHEUS_RUNTIME_DASHBOARD_ACCESS = False

OPERATOR_COMMANDS = frozenset({
    "START_PROJECT", "START_ISSUE", "START_REPO_ANALYSIS", "START_BLUEPRINT_PROJECT",
    "PAUSE_RUN", "RESUME_RUN", "ABORT_RUN", "RETRY_STAGE", "RETRY_RUN",
    "EXCLUDE_MODEL_FOR_RUN", "EXCLUDE_PROVIDER_FOR_RUN", "APPROVE_HUMAN_GATE",
})
ADMIN_COMMANDS = frozenset({
    "RUN_ROUTER_TEST", "RUN_MCP_TEST", "RUN_SYSTEM_TEST", "REFRESH_CATALOG",
    "SYNC_CREDENTIALS",
})
READ_ROLES = frozenset({"VIEWER", "OPERATOR", "ADMIN"})
COMMAND_ROLES = {"OPERATOR": OPERATOR_COMMANDS, "ADMIN": OPERATOR_COMMANDS | ADMIN_COMMANDS}

COMMAND_PATHS = {name: "/webhook/autodev/control" for name in OPERATOR_COMMANDS | ADMIN_COMMANDS}
COMMAND_PATHS.update({"START_ISSUE": "/webhook/autodev/start"})

ROUTER_TESTS = frozenset({
    "Dynamischer Router", "Modellkatalog", "Free Pool", "Credential-Erkennung",
    "Capability Filter", "Tool Routing", "Vision Routing", "Structured Output",
    "Transport Failover", "Semantic Failover", "Run Blacklist",
    "Paid Fallback Sperre", "DeepSeek Sperre",
})

SECRET_KEYS = re.compile(r"(?:authorization|cookie|token|secret|password|api[_-]?key|private[_-]?key|ssh[_-]?key|credential|reasoning|chain.?of.?thought)", re.I)
REASONING_KEYS = {"reasoning_content", "reasoning", "chain_of_thought", "chain-of-thought", "thoughts"}
TARGET_KEYS = frozenset({"run_id", "project_id", "issue_number"})
CONTINUATION_FIELDS = frozenset({
    "project_id", "source_run_id", "run_id", "issue_number",
    "continuation_reason", "requested_action",
})
CONTINUATION_TERMINAL_STATES = frozenset({
    "DONE", "COMPLETED", "ABORTED", "BLOCKED", "FAILED", "PAUSED", "PLAN_BLOCKED",
})
ACTIVE_RUN_STATES = frozenset({
    "ACCEPTED", "BASELINING", "RESEARCHING", "PLANNING", "BUILDING",
    "VERIFYING", "REVIEWING", "DECIDING", "RUNNING", "ACTIVE",
})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def correlation_id(command: str, target: dict | None = None) -> str:
    raw = f"{command}:{target or {}}:{utc_now()}".encode()
    return "ct-" + hashlib.sha256(raw).hexdigest()[:20]


def role_for_token(token: str, operator_token: str, admin_token: str, viewer_token: str) -> str | None:
    if token and admin_token and _constant_time(token, admin_token):
        return "ADMIN"
    if token and operator_token and _constant_time(token, operator_token):
        return "OPERATOR"
    # Backwards compatibility: the former viewer token can operate as an
    # operator only when explicitly opted in.  Default remains read-only.
    if token and viewer_token and _constant_time(token, viewer_token):
        return "OPERATOR" if operator_token == viewer_token else "VIEWER"
    return None


def _constant_time(left: str, right: str) -> bool:
    import hmac
    return hmac.compare_digest(left, right)


def validate_repository_url(value: object) -> str:
    if not isinstance(value, str) or len(value) > 512:
        raise ValueError("repository_url must be a string of at most 512 characters")
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname != "github.com" or not parsed.path.strip("/"):
        raise ValueError("repository_url must be an https GitHub URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("repository_url may not contain credentials or query data")
    return value.rstrip("/")


def validate_issue_ref(value: object) -> str:
    if isinstance(value, int) and value > 0:
        return str(value)
    if isinstance(value, str) and (re.fullmatch(r"#?[1-9][0-9]{0,8}", value) or re.fullmatch(r"https://github\.com/[^/]+/[^/]+/issues/[1-9][0-9]{0,8}", value)):
        return value
    raise ValueError("issue must be an issue number or GitHub issue URL")


def validate_blueprint(markdown: object) -> str:
    if not isinstance(markdown, str) or not markdown.strip():
        raise ValueError("blueprint_md is required")
    if len(markdown.encode("utf-8")) > 512_000:
        raise ValueError("blueprint_md exceeds the 512 KiB limit")
    return markdown


def validate_target(target: object) -> dict:
    """Validate the non-routing target metadata accepted by the command contract."""
    if target is None:
        return {}
    if not isinstance(target, dict) or len(target) > len(TARGET_KEYS):
        raise ValueError("target must be a small JSON object")
    for key, value in target.items():
        if key not in TARGET_KEYS:
            raise ValueError("target key is not allowed")
        if not isinstance(value, (str, int)) or isinstance(value, bool):
            raise ValueError("target values must be scalar identifiers")
        if not re.fullmatch(r"[A-Za-z0-9_.:#-]{1,96}", str(value)):
            raise ValueError("target value is invalid")
    return target


def _validate_identifier(value: object, name: str, pattern: str = r"[A-Za-z0-9_.:#-]{1,96}") -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{name} is required")
    result = str(value)
    if not re.fullmatch(pattern, result):
        raise ValueError(f"{name} is invalid")
    return result


def _validate_bounded_text(value: object, name: str, maximum: int = 240) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(char) < 32 and char not in "\t" for char in value):
        raise ValueError(f"{name} must be a short bounded instruction")
    return value.strip()


def validate_command(command: object, payload: object, role: str) -> tuple[str, dict]:
    if role not in COMMAND_ROLES:
        raise PermissionError("role is not allowed to issue commands")
    if not isinstance(command, str) or command not in COMMAND_PATHS:
        raise ValueError("unsupported command")
    if command not in COMMAND_ROLES[role]:
        raise PermissionError("command requires ADMIN role")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict) or len(payload) > 32:
        raise ValueError("payload must be a JSON object")
    for key in payload:
        if not isinstance(key, str) or key.startswith("__") or len(key) > 64:
            raise ValueError("invalid payload key")
    if command == "RESUME_RUN":
        unknown = set(payload) - CONTINUATION_FIELDS
        if unknown:
            raise ValueError("continuation payload field is not allowed")
        payload["project_id"] = _validate_identifier(payload.get("project_id"), "project_id")
        payload["source_run_id"] = _validate_identifier(
            payload.get("source_run_id") or payload.get("run_id"),
            "source_run_id",
            r"run-[A-Za-z0-9_-]{1,60}",
        )
        if payload.get("issue_number") is not None:
            payload["issue_number"] = _validate_identifier(payload["issue_number"], "issue_number")
        payload["continuation_reason"] = _validate_bounded_text(payload.get("continuation_reason"), "continuation_reason")
        payload["requested_action"] = _validate_bounded_text(payload.get("requested_action"), "requested_action")
        payload.pop("run_id", None)
    if command in {
        "PAUSE_RUN", "ABORT_RUN", "RETRY_STAGE", "RETRY_RUN",
        "EXCLUDE_MODEL_FOR_RUN", "EXCLUDE_PROVIDER_FOR_RUN", "APPROVE_HUMAN_GATE",
    } and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", str(payload.get("run_id", ""))):
        raise ValueError("run_id is required")
    if command == "EXCLUDE_MODEL_FOR_RUN":
        model = str(payload.get("model", ""))
        if not re.fullmatch(r"[A-Za-z0-9._/-]{1,128}", model):
            raise ValueError("model is required")
        if "deepseek" in model.lower():
            raise ValueError("DeepSeek is retired")
    if command == "EXCLUDE_PROVIDER_FOR_RUN":
        provider = str(payload.get("provider", ""))
        if not re.fullmatch(r"[A-Za-z0-9._/-]{1,64}", provider):
            raise ValueError("provider is required")
        if "deepseek" in provider.lower():
            raise ValueError("DeepSeek is retired")
    if command == "RUN_ROUTER_TEST" and payload.get("test") not in ROUTER_TESTS:
        raise ValueError("unknown router diagnostic")
    if command == "RUN_MCP_TEST" and not re.fullmatch(r"[A-Za-z0-9._-]{1,96}", str(payload.get("test", ""))):
        raise ValueError("MCP server name is required")
    if any("deepseek" in str(payload.get(key, "")).lower() for key in ("provider", "model")):
        raise ValueError("DeepSeek is retired")
    if command in {"START_ISSUE", "START_PROJECT", "START_REPO_ANALYSIS", "START_BLUEPRINT_PROJECT"}:
        if "repository_url" in payload:
            payload["repository_url"] = validate_repository_url(payload["repository_url"])
        if command == "START_ISSUE":
            validate_issue_ref(payload.get("issue"))
        if command in {"START_BLUEPRINT_PROJECT", "START_PROJECT"} and payload.get("blueprint_md") is not None:
            validate_blueprint(payload["blueprint_md"])
    for key in payload:
        if SECRET_KEYS.search(key) and key not in {"credential_type"}:
            raise ValueError("secret-bearing payload fields are not accepted")
    return command, payload


def audit_entry(command: str, role: str, target: dict, result: str, project_id: str | None, run_id: str | None, correlation: str) -> dict:
    return {"timestamp": utc_now(), "actor": "control-tower", "role": role, "command": command,
            "target": target, "project_id": project_id, "run_id": run_id,
            "result": result, "correlation_id": correlation}


def redact(value, key: str = ""):
    if key in REASONING_KEYS or SECRET_KEYS.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {k: redact(v, k) for k, v in value.items() if k not in REASONING_KEYS}
    if isinstance(value, list):
        return [redact(item, key) for item in value]
    return value


def blueprint_projection(markdown: str) -> dict:
    """Extract durable blueprint intent without turning it into a prompt."""
    headings = {}
    current = None
    for line in markdown.splitlines():
        match = re.match(r"^#{1,3}\s+(.+?)\s*$", line)
        if match:
            current = match.group(1).strip().lower()
            headings.setdefault(current, [])
        elif current and line.strip():
            headings[current].append(line.strip())
    aliases = {
        "project_goal": ("ziel", "projektziel", "goal", "objective"),
        "scope": ("scope",), "non_scope": ("nicht-scope", "non-scope", "out of scope"),
        "requirements": ("anforderungen", "requirements"), "architecture": ("architektur", "architecture"),
        "milestones": ("meilensteine", "milestones"), "acceptance_criteria": ("acceptance criteria", "akzeptanzkriterien"),
        "risks": ("risiken", "risks"), "dependencies": ("abhängigkeiten", "dependencies"),
    }
    result = {key: [] for key in aliases}
    for key, names in aliases.items():
        for name in names:
            if name in headings:
                result[key] = headings[name]
                break
    result["title"] = next((line.lstrip("# ").strip() for line in markdown.splitlines() if line.startswith("#")), "Unbenanntes Projekt")
    result["valid"] = bool(result["project_goal"] or result["requirements"] or result["acceptance_criteria"])
    result["format"] = ".md"
    return result


def classify_issue(issue: dict) -> str:
    explicit = str(issue.get("morpheus_status", issue.get("status", ""))).upper()
    if explicit in {"READY", "RUNNING", "BLOCKED", "DONE", "OBSOLETE", "DUPLICATE", "UNKNOWN"}:
        return explicit
    if issue.get("duplicate_of") or issue.get("duplicate"):
        return "DUPLICATE"
    if issue.get("closed") or str(issue.get("state", "")).lower() == "closed":
        return "DONE"
    if issue.get("blocked") or issue.get("blocked_by"):
        return "BLOCKED"
    return "READY" if issue.get("changes_expected", True) else "UNKNOWN"


def project_projection(project_rows: list[dict], issue_rows: list[dict], run_rows: list[dict]) -> list[dict]:
    grouped = defaultdict(lambda: {"issues": [], "runs": []})
    for row in project_rows:
        grouped[str(row.get("project_id") or row.get("id") or row.get("repository_ref") or "unknown")]["project"] = row
    for row in issue_rows:
        grouped[str(row.get("project_id") or row.get("repository_ref") or "unknown")]["issues"].append(row)
    for row in run_rows:
        project_id = str(row.get("project_id") or row.get("repository_ref") or "unknown")
        grouped[project_id]["runs"].append(row)
    result = []
    for project_id, value in grouped.items():
        project = value.get("project", {})
        issues = value["issues"]
        if not issues:
            issues = [{"status": "RUNNING" if any(str(r.get("state", "")).upper() in {"RUNNING", "ACTIVE", "BUILDING", "PLANNING"} for r in value["runs"]) else "UNKNOWN"}]
        statuses = [classify_issue(issue) for issue in issues]
        def run_key(run):
            timestamp = run.get("updated_at") or run.get("ended_at") or run.get("created_at")
            try:
                parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError, OverflowError):
                return datetime.min.replace(tzinfo=timezone.utc)

        runs = sorted(value["runs"], key=run_key, reverse=True)
        latest = runs[0] if runs else None
        active_runs = [r for r in runs if str(r.get("state", "")).upper() in ACTIVE_RUN_STATES]
        active = active_runs[0] if active_runs else None
        latest_state = str((latest or {}).get("state", "UNKNOWN")).upper()
        continuation_allowed = bool(latest and not active and latest_state in CONTINUATION_TERMINAL_STATES)
        history = [{key: r.get(key) for key in (
            "run_id", "project_id", "issue_number", "state", "current_job", "decision",
            "reason_code", "created_at", "updated_at", "ended_at", "source_run_id",
            "created_via", "continuation_reason", "requested_action", "requested_by",
            "correlation_id",
        ) if key in r} for r in runs]
        last_outcome = (latest or {}).get("reason_code") or (latest or {}).get("decision") or latest_state
        result.append({"project_id": project_id, "name": project.get("name") or project.get("project_name") or project_id,
                       "repository": project.get("repository_url") or project.get("repository_ref") or project_id,
                       "blueprint": project.get("blueprint_ref") or project.get("blueprint") or None,
                       "status": "RUNNING" if active else "BLOCKED" if "BLOCKED" in statuses else "DONE" if statuses and all(s == "DONE" for s in statuses) else "READY",
                       "current_issue": (active or latest or {}).get("issue_number") or (active or latest or {}).get("task_ref"),
                       "current_run": (active or latest or {}).get("run_id"),
                       "latest_run_id": (latest or {}).get("run_id"),
                       "active_run_id": (active or {}).get("run_id"),
                       "active_run_conflict": bool(active_runs),
                       "is_active": bool(active),
                       "continuation_allowed": continuation_allowed,
                       "continuation_blocked_reason": "PROJECT_ACTIVE_RUN_CONFLICT" if active else ("CONTINUATION_NOT_ALLOWED" if not continuation_allowed else None),
                       "last_outcome": last_outcome,
                       "run_history": history,
                       "progress": {"done": statuses.count("DONE"), "total": len(statuses)},
                       "issue_counts": {key: statuses.count(key) for key in ("READY", "RUNNING", "BLOCKED", "DONE", "REVIEW", "UNKNOWN")},
                       "issues": [redact({**issue, "morpheus_status": classify_issue(issue)}) for issue in issues]})
    return sorted(result, key=lambda x: x["name"])


def reassessment(issues: list[dict], blueprint: dict | None = None, mode: str = "MANUAL") -> dict:
    classified = [{**issue, "morpheus_status": classify_issue(issue)} for issue in issues]
    ready = [i for i in classified if i["morpheus_status"] == "READY"]
    blocked = [i for i in classified if i["morpheus_status"] == "BLOCKED"]
    open_items = [i for i in classified if i["morpheus_status"] not in {"DONE", "OBSOLETE", "DUPLICATE"}]
    coverage = bool(blueprint and blueprint.get("valid") and not open_items)
    status = "PROJECT_DONE" if coverage else "BLOCKED" if blocked and not ready else "READY" if ready else "UNKNOWN"
    return {"status": status, "mode": mode if mode in {"AUTO", "MANUAL"} else "MANUAL", "ready": ready,
            "blocked": blocked, "next_issue": ready[0] if mode == "AUTO" and ready else None,
            "blueprint_coverage": coverage, "issues": classified}


def continuation_policy(project: dict | None, runs: list[dict], issues: list[dict], request: dict) -> dict:
    """Pure, read-only mirror of the n8n continuation eligibility contract."""
    project_id = str(request.get("project_id", ""))
    source_run_id = str(request.get("source_run_id") or request.get("run_id") or "")
    correlation = str(request.get("correlation_id", ""))
    if not project or str(project.get("project_id", "")) != project_id:
        return {"allowed": False, "code": "PROJECT_NOT_FOUND"}
    duplicate = next((run for run in runs if str(run.get("correlation_id", "")) == correlation and run.get("created_via") == "CONTROL_TOWER_CONTINUATION"), None)
    if duplicate:
        return {"allowed": False, "code": "DUPLICATE_REQUEST", "existing_run_id": duplicate.get("run_id")}
    active = next((run for run in runs if str(run.get("state", "")).upper() in ACTIVE_RUN_STATES), None)
    if active:
        return {"allowed": False, "code": "PROJECT_ACTIVE_RUN_CONFLICT", "active_run_id": active.get("run_id")}
    source = next((run for run in runs if str(run.get("run_id", "")) == source_run_id), None)
    if not source or str(source.get("project_id", "")) != project_id or str(source.get("state", "")).upper() not in CONTINUATION_TERMINAL_STATES:
        return {"allowed": False, "code": "CONTINUATION_NOT_ALLOWED"}
    issue_number = request.get("issue_number")
    selected_issue = None
    if issue_number is not None and str(issue_number) != "":
        selected_issue = next((issue for issue in issues if str(issue.get("issue_number") or issue.get("number") or "") == str(issue_number)), None)
        if not selected_issue or classify_issue(selected_issue) in {"OBSOLETE", "DUPLICATE"}:
            return {"allowed": False, "code": "ISSUE_NOT_FOUND"}
    return {"allowed": True, "code": None, "source_run": source, "issue": selected_issue}
