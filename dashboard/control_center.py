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
    if command in {
        "PAUSE_RUN", "RESUME_RUN", "ABORT_RUN", "RETRY_STAGE", "RETRY_RUN",
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
        current = next((r for r in sorted(value["runs"], key=lambda r: r.get("updated_at") or "", reverse=True) if str(r.get("state", "")).upper() not in {"DONE", "COMPLETED"}), None)
        result.append({"project_id": project_id, "name": project.get("name") or project.get("project_name") or project_id,
                       "repository": project.get("repository_url") or project.get("repository_ref") or project_id,
                       "blueprint": project.get("blueprint_ref") or project.get("blueprint") or None,
                       "status": "BLOCKED" if "BLOCKED" in statuses else "RUNNING" if "RUNNING" in statuses else "DONE" if statuses and all(s == "DONE" for s in statuses) else "READY",
                       "current_issue": (current or {}).get("issue_number") or (current or {}).get("task_ref"),
                       "current_run": (current or {}).get("run_id"), "progress": {"done": statuses.count("DONE"), "total": len(statuses)},
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
