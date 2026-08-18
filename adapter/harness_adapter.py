#!/usr/bin/env python3
"""AutoDev Harness Adapter v1 — minimal stdlib HTTP adapter (Proxmox host).

Contract endpoints (all POST, JSON, token-authenticated):
  /baseline  /research/code  /research/docs  /research/tests
  /plan  /build  /verify  /fix
  /review/correctness  /review/security  /review/quality
  GET /healthz

Execution backends:
  embedded                — deterministic canary on this host
  opencode-builder-8001   — builder CT 8001 + OpenCode 1.17.9 + LM Studio (REUSE)

Roles baseline/research/plan/build/verify/review are harness JOBS, not agents.
LLMs are workers; the n8n workflow is the deterministic controller.
"""

import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ------------------------------------------------------------------ config --
STATE_DIR = "/var/lib/autodev-harness"
TOKEN_FILE = os.path.join(STATE_DIR, "token")
LOG_FILE = os.path.join(STATE_DIR, "logs", "runs.jsonl")
WS_ROOT = os.path.join(STATE_DIR, "workspaces")
BIND_HOST = "192.168.1.136"
BIND_PORT = 8080

BUILDER_CTID = "8001"
BUILDER_WS_ROOT = "/var/lib/ghiw/workspaces"
LOCAL_LLM_SRC = "/var/lib/ghiw/workspaces/provider-smoke-v3/local_llm"
OPENCODE_BIN = "/opt/dev-fabric/opencode/opencode"
LMSTUDIO_URL = "http://192.168.1.195:1234"
LMSTUDIO_MODEL = "qwen/qwen3.5-9b"
OC_AGENT = "issue-orchestrator"

MAX_BODY = 262144
RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
CANONICAL_URL = "http://192.168.1.136:8080"

VALID_BACKENDS = {"embedded", "opencode-builder-8001"}

C_BASELINE = "harness.baseline.v1"
C_RESEARCH = "harness.research.v1"
C_PLAN = "harness.plan.v1"
C_BUILD = "harness.build-result.v1"
C_VERIFY = "harness.verification.v1"
C_FIX = "harness.fix.v1"
C_REVIEW = "harness.review.v1"

# ------------------------------------------------------------------ state --
_log_lock = threading.Lock()
_verify_state = {}  # run_id -> {"attempt": int}
_verify_state_lock = threading.Lock()

os.makedirs(os.path.join(STATE_DIR, "logs"), exist_ok=True)
os.makedirs(WS_ROOT, exist_ok=True)


def log_job(
    run_id,
    job,
    attempt,
    status,
    duration_ms,
    backend,
    provider="embedded",
    model="embedded",
):
    entry = {
        "ts": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_id": run_id,
        "job": job,
        "attempt": attempt,
        "status": status,
        "duration_ms": int(duration_ms),
        "backend": backend,
        "provider": provider,
        "model": model,
    }
    with _log_lock:
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")


def err(code, message):
    return json.dumps({"status": "error", "error": {"code": code, "message": message}})


def run_cmd(argv, timeout=600, cwd=None, env=None):
    return subprocess.run(
        argv, capture_output=True, text=True, timeout=timeout, cwd=cwd, env=env
    )


def pct_exec(cmd):
    return run_cmd(["pct", "exec", BUILDER_CTID, "--", "bash", "-c", cmd], timeout=900)


def pct_exec_stdout(cmd):
    r = pct_exec(cmd)
    return r.stdout


# ------------------------------------------------------------------ helpers --
def host_workspace(run_id):
    ws = os.path.join(WS_ROOT, run_id)
    os.makedirs(os.path.join(ws, "src"), exist_ok=True)
    os.makedirs(os.path.join(ws, "tests"), exist_ok=True)
    return ws


def builder_workspace(run_id):
    ws = os.path.join(BUILDER_WS_ROOT, "autodev-" + run_id)
    pct_exec_stdout("mkdir -p '%s/src' '%s/tests'" % (ws, ws))
    return ws


def list_files(base, sub=""):
    files = []
    root = os.path.join(base, sub)
    if os.path.isdir(root):
        for dirpath, _dirs, names in os.walk(root):
            for n in sorted(names):
                p = os.path.relpath(os.path.join(dirpath, n), base)
                files.append(p)
    return files


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def write_text(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


GREETER_OK = """def greet(name):
    return f"Hello, {name}!"
"""

GREETER_BROKEN = """def greet(name):
    return f"Hello {name}"
"""

TEST_OK = """import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from greeter import greet


class TestGreeter(unittest.TestCase):
    def test_returns_hello(self):
        self.assertEqual(greet("Welt"), "Hello, Welt!")

    def test_accepts_empty(self):
        self.assertEqual(greet(""), "Hello, !")


if __name__ == "__main__":
    unittest.main()
"""


def base_plan(run_id, task, repository):
    return {
        "contract": C_PLAN,
        "run_id": run_id,
        "plan": {
            "targets": [
                "Create src/greeter.py implementing greet(name) returning 'Hello, <name>!'",
                "Create tests/test_greeter.py with 2 passing unittest assertions",
            ],
            "acceptance_criteria": [
                "greet('Welt') returns 'Hello, Welt!'",
                "all tests in tests/ pass",
            ],
            "required_tests": ["test_returns_hello", "test_accepts_empty"],
            "risks": [
                "scope creep into unrelated paths",
                "secret-like content in source",
            ],
            "build_scope": {
                "paths": ["src/greeter.py", "tests/test_greeter.py"],
                "forbidden_paths": [".env*", "*.key", "*.pem"],
                "description": "bounded canary: greeter module + unit tests",
                "task": task[:200],
                "repository": repository,
            },
        },
    }


# ------------------------------------------------------------- job handlers --
def job_baseline(payload):
    run_id = payload["run_id"]
    backend = payload.get("execution_backend", "embedded")
    repository = payload.get("repository") or "local-canary/greeter"
    if backend == "opencode-builder-8001":
        ws = builder_workspace(run_id)
        files = [
            l
            for l in pct_exec_stdout(
                "find '%s' -type f -not -path '*/.*' | sed 's#^%s/##' | sort" % (ws, ws)
            ).splitlines()
            if l
        ]
        workspace = ws
        provider, model = "local_lmstudio", LMSTUDIO_MODEL
    else:
        ws = host_workspace(run_id)
        files = list_files(ws)
        workspace = ws
        provider, model = "embedded", "embedded"
    return {
        "contract": C_BASELINE,
        "run_id": run_id,
        "task": payload.get("task", ""),
        "repository": repository,
        "fixture": payload.get("fixture"),
        "execution_backend": backend,
        "config": {
            "adapter_base_url": payload.get("config", {}).get(
                "adapter_base_url", CANONICAL_URL
            )
        },
        "baseline": {
            "repository": repository,
            "workspace": workspace,
            "files": files,
            "existing_targets": [],
            "head": hashlib.sha256(("\n".join(files)).encode()).hexdigest()[:16],
            "observed_at": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "observability": {"provider": provider, "model": model},
    }


def job_research(payload, focus):
    run_id = payload["run_id"]
    backend = payload.get("execution_backend", "embedded")
    if backend == "opencode-builder-8001":
        ws = builder_workspace(run_id)
        provider, model = "local_lmstudio", LMSTUDIO_MODEL
        if focus == "code":
            files = [
                l
                for l in pct_exec_stdout(
                    "find '%s/src' -type f 2>/dev/null | sed 's#^%s/##' | sort"
                    % (ws, ws)
                ).splitlines()
                if l
            ]
        elif focus == "docs":
            files = [
                l
                for l in pct_exec_stdout(
                    "find '%s' -maxdepth 2 -type f \\( -name '*.md' -o -name '*.txt' \\) | sed 's#^%s/##' | sort"
                    % (ws, ws)
                ).splitlines()
                if l
            ]
        else:
            files = [
                l
                for l in pct_exec_stdout(
                    "find '%s/tests' -type f 2>/dev/null | sed 's#^%s/##' | sort"
                    % (ws, ws)
                ).splitlines()
                if l
            ]
        findings = [{"path": p, "kind": focus, "observed": True} for p in files]
    else:
        ws = host_workspace(run_id)
        provider, model = "embedded", "embedded"
        if focus == "code":
            files = [p for p in list_files(ws) if p.startswith("src/")]
        elif focus == "docs":
            files = [p for p in list_files(ws) if p.endswith((".md", ".txt"))]
        else:
            files = [p for p in list_files(ws) if p.startswith("tests/")]
        findings = [{"path": p, "kind": focus, "observed": True} for p in files]
    empty = len(findings) == 0
    return {
        "contract": C_RESEARCH,
        "run_id": run_id,
        "job": "research/" + focus,
        "research_focus": payload.get("research_focus", focus),
        "task": payload.get("task", ""),
        "repository": payload.get("repository", ""),
        "fixture": payload.get("fixture"),
        "execution_backend": backend,
        "config": {
            "adapter_base_url": payload.get("config", {}).get(
                "adapter_base_url", CANONICAL_URL
            )
        },
        "findings": findings,
        "empty": empty,
        "observability": {"provider": provider, "model": model},
    }


def job_plan(payload):
    run_id = payload["run_id"]
    plan = base_plan(run_id, payload.get("task", ""), payload.get("repository", ""))
    if payload.get("fixture") == "invalid_plan":
        plan["plan"]["acceptance_criteria"] = []
    plan["fixture"] = payload.get("fixture")
    plan["execution_backend"] = payload.get("execution_backend", "embedded")
    plan["config"] = {
        "adapter_base_url": payload.get("config", {}).get(
            "adapter_base_url", CANONICAL_URL
        )
    }
    return plan


def job_build(payload):
    run_id = payload["run_id"]
    backend = payload.get("execution_backend", "embedded")
    fixture = payload.get("fixture")
    plan = payload.get("plan") or {}
    t0 = time.time()
    if backend == "opencode-builder-8001":
        ws = builder_workspace(run_id)
        changed = job_build_opencode(run_id, ws, fixture)
        provider, model, status = "local_lmstudio", LMSTUDIO_MODEL, "completed"
    else:
        ws = host_workspace(run_id)
        content = (
            GREETER_BROKEN
            if fixture
            in (
                "verify_fail_delta",
                "verify_fail_no_delta",
                "no_signature",
                "attempt_limit",
            )
            else GREETER_OK
        )
        write_text(os.path.join(ws, "src", "greeter.py"), content)
        write_text(os.path.join(ws, "tests", "test_greeter.py"), TEST_OK)
        changed = ["src/greeter.py", "tests/test_greeter.py"]
        provider, model, status = "embedded", "embedded", "completed"
    dur = time.time() - t0
    log_job(
        run_id,
        "build",
        payload.get("attempt", 1),
        status,
        dur * 1000,
        backend,
        provider,
        model,
    )
    return {
        "contract": C_BUILD,
        "run_id": run_id,
        "task": payload.get("task", ""),
        "repository": payload.get("repository", ""),
        "fixture": fixture,
        "execution_backend": backend,
        "config": {
            "adapter_base_url": payload.get("config", {}).get(
                "adapter_base_url", CANONICAL_URL
            )
        },
        "build": {
            "status": status,
            "changed_paths": changed,
            "workspace": ws,
            "summary": "build job applied plan targets"
            if status == "completed"
            else "build job failed",
            "attempt": payload.get("attempt", 1),
        },
        "observability": {"provider": provider, "model": model},
    }


def job_build_opencode(run_id, ws, fixture):
    """Real OpenCode run on builder 8001 via existing local_llm overlay (REUSE)."""
    broken = fixture in (
        "verify_fail_delta",
        "verify_fail_no_delta",
        "no_signature",
        "attempt_limit",
    )
    variant = (
        "the return value MUST be 'Hello {name}' WITHOUT the trailing exclamation mark"
        if broken
        else "the return value MUST be exactly 'Hello, {name}!' with comma and exclamation mark"
    )
    prompt = (
        "You are building a bounded canary. Workspace: current directory. "
        "Create src/greeter.py with a function greet(name) where %s. "
        "Create tests/test_greeter.py with two unittest tests: test_returns_hello "
        "(greet('Welt') == 'Hello, Welt!') and test_accepts_empty (greet('') == 'Hello, !'). "
        "Tests import with: from greeter import greet (the harness runs PYTHONPATH=src). "
        "Every file MUST end with a trailing newline. "
        "Touch ONLY src/greeter.py and tests/test_greeter.py. Do not read other files, "
        "do not commit, do not push, do not use network."
    ) % variant
    script = (
        "set -e; cd '%s'; "
        "mkdir -p .opencode/agents; "
        "cat > .opencode/agents/harness-worker.md << 'EOFAGENT'\n"
        "---\n"
        "description: Bounded harness canary worker. Writes only the files named in the task prompt.\n"
        "model: lmstudio/%s\n"
        "temperature: 0\n"
        "tools:\n"
        "  bash: false\n"
        "  edit: true\n"
        "  read: true\n"
        "  write: true\n"
        "  list: false\n"
        "  grep: false\n"
        "  glob: false\n"
        "  webfetch: false\n"
        "  task: false\n"
        "  skill: false\n"
        "  question: false\n"
        "  todowrite: false\n"
        "permission:\n"
        "  edit: allow\n"
        "  write: allow\n"
        "  bash: deny\n"
        "---\n"
        "You are a bounded canary builder. Use ONLY the edit/write tools to create exactly "
        "the files named in the task. Never read other files. Never run commands. Never use "
        "the network. Never commit or push. Produce minimal, correct code.\n"
        "EOFAGENT\n"
        "cp -r '%s' ./local_llm 2>/dev/null || true; "
        "export GHIW_LOCAL_LLM_ENABLED=true "
        "GHIW_LMSTUDIO_BASE_URL='%s' GHIW_LMSTUDIO_MODEL_ID='%s' "
        "GHIW_LMSTUDIO_TIMEOUT_SECONDS=180 GHIW_LOCAL_LLM_CONTEXT_LIMIT=8192 "
        "GHIW_LOCAL_LLM_MAX_ATTEMPTS=1 GHIW_LOCAL_LLM_CONCURRENCY=1; "
        'export OPENCODE_CONFIG_CONTENT="$(python3 -m local_llm.opencode_cli)"; '
        "export PATH='/opt/dev-fabric/opencode:/usr/local/bin:/usr/bin:/bin'; "
        "%s run --agent harness-worker --model 'lmstudio/%s' --format json %s"
        " > build.jsonl 2> build.stderr"
    ) % (
        ws,
        LMSTUDIO_MODEL,
        LOCAL_LLM_SRC,
        LMSTUDIO_URL,
        LMSTUDIO_MODEL,
        OPENCODE_BIN,
        LMSTUDIO_MODEL,
        json.dumps(prompt),
    )
    r = pct_exec(script)
    out = (r.stdout or "").strip()
    if out:
        sys.stderr.write(
            "[build-opencode] rc=%s stdout=%s\n" % (r.returncode, out[:500])
        )
    ls = pct_exec_stdout(
        "find '%s' -type f -not -path '*/local_llm/*' -not -path '*/.*' | sed 's#^%s/##' | sort"
        % (ws, ws)
    )
    changed = [
        l for l in ls.splitlines() if l and not l.startswith(("build.", "local_llm"))
    ]
    return changed


def job_verify(payload):
    run_id = payload["run_id"]
    backend = payload.get("execution_backend", "embedded")
    fixture = payload.get("fixture")
    attempt = int(payload.get("attempt", 1))
    with _verify_state_lock:
        _verify_state.setdefault(run_id, {"attempt": attempt})
        seen = _verify_state[run_id].get("attempt", attempt)
        _verify_state[run_id]["attempt"] = max(seen, attempt)
    t0 = time.time()
    out = ""

    # Fixture-driven verification outcomes (deterministic negative tests)
    if fixture == "verify_fail_delta" and attempt <= 1:
        passed = False
        failure_signature = "assertion_mismatch:greet_missing_comma"
        strategy_delta = "rewrite src/greeter.py to return 'Hello, {name}!' (comma + exclamation mark)"
        checks = [
            {
                "name": "unit_tests",
                "passed": False,
                "detail": "fixture: first-attempt failure with strategy delta",
            }
        ]
    elif fixture == "attempt_limit":
        passed = False
        failure_signature = "assertion_mismatch:greet_missing_comma"
        strategy_delta = "rewrite src/greeter.py to return 'Hello, {name}!' (comma + exclamation mark)"
        checks = [
            {
                "name": "unit_tests",
                "passed": False,
                "detail": "fixture: persistent failure (attempt limit scenario)",
            }
        ]
    elif fixture == "verify_fail_no_delta":
        passed = False
        failure_signature = "assertion_mismatch:greet_missing_comma"
        strategy_delta = None
        checks = [
            {
                "name": "unit_tests",
                "passed": False,
                "detail": "fixture: failure without strategy delta",
            }
        ]
    elif fixture == "no_signature":
        passed = False
        failure_signature = None
        strategy_delta = "rewrite src/greeter.py to return 'Hello, {name}!'"
        checks = [
            {
                "name": "unit_tests",
                "passed": False,
                "detail": "fixture: failure without signature",
            }
        ]
    else:
        # Real verification: run the unit tests
        if backend == "opencode-builder-8001":
            ws = builder_workspace(run_id)
            r = pct_exec("cd '%s' && PYTHONPATH=src python3 tests/test_greeter.py" % ws)
            out = (r.stdout or "") + (r.stderr or "")
            passed = r.returncode == 0
        else:
            ws = host_workspace(run_id)
            env = dict(os.environ, PYTHONPATH=os.path.join(ws, "src"))
            r = run_cmd(
                ["python3", "tests/test_greeter.py"], timeout=120, cwd=ws, env=env
            )
            out = (r.stdout or "") + (r.stderr or "")
            passed = r.returncode == 0
        failure_signature = (
            None
            if passed
            else (
                "test_suite_failure:"
                + (out.strip().splitlines()[-1][:80] if out.strip() else "no_output")
            )
        )
        strategy_delta = (
            None if passed else "run tests, fix code so all assertions pass"
        )
        checks = [
            {
                "name": "unit_tests",
                "passed": passed,
                "detail": out[:300] if not passed else "all tests passed",
            }
        ]

    dur = time.time() - t0
    provider = "local_lmstudio" if backend == "opencode-builder-8001" else "embedded"
    model = LMSTUDIO_MODEL if backend == "opencode-builder-8001" else "embedded"
    status = "passed" if passed else "failed"
    log_job(run_id, "verify", attempt, status, dur * 1000, backend, provider, model)
    return {
        "contract": C_VERIFY,
        "run_id": run_id,
        "task": payload.get("task", ""),
        "repository": payload.get("repository", ""),
        "fixture": fixture,
        "execution_backend": backend,
        "attempt": attempt,
        "max_attempts": payload.get("max_attempts", 2),
        "config": {
            "adapter_base_url": payload.get("config", {}).get(
                "adapter_base_url", CANONICAL_URL
            )
        },
        "verification": {
            "passed": passed,
            "failure_signature": failure_signature,
            "strategy_delta": strategy_delta,
            "checks": checks,
            "attempt": attempt,
        },
        "observability": {"provider": provider, "model": model},
    }


def job_fix(payload):
    run_id = payload["run_id"]
    backend = payload.get("execution_backend", "embedded")
    fixture = payload.get("fixture")
    attempt = int(payload.get("attempt", 1))
    delta = payload.get("strategy_delta") or "apply minimal fix"
    t0 = time.time()
    if backend == "opencode-builder-8001":
        ws = builder_workspace(run_id)
        prompt = (
            "Fix the failing tests. Strategy delta: %s. Workspace: current directory. "
            "Tests import with: from greeter import greet (harness runs PYTHONPATH=src). "
            "Touch ONLY src/greeter.py and tests/test_greeter.py. Do not read other files, "
            "do not commit, do not push."
        ) % delta
        script = (
            "set -e; cd '%s'; "
            "export GHIW_LOCAL_LLM_ENABLED=true "
            "GHIW_LMSTUDIO_BASE_URL='%s' GHIW_LMSTUDIO_MODEL_ID='%s' "
            "GHIW_LMSTUDIO_TIMEOUT_SECONDS=180 GHIW_LOCAL_LLM_CONTEXT_LIMIT=8192 "
            "GHIW_LOCAL_LLM_MAX_ATTEMPTS=1 GHIW_LOCAL_LLM_CONCURRENCY=1; "
            'export OPENCODE_CONFIG_CONTENT="$(python3 -m local_llm.opencode_cli)"; '
            "export PATH='/opt/dev-fabric/opencode:/usr/local/bin:/usr/bin:/bin'; "
            "%s run --agent harness-worker --model 'lmstudio/%s' --format json %s"
            " > fix.jsonl 2> fix.stderr"
        ) % (
            ws,
            LMSTUDIO_URL,
            LMSTUDIO_MODEL,
            OPENCODE_BIN,
            LMSTUDIO_MODEL,
            json.dumps(prompt),
        )
        pct_exec(script)
        ls = pct_exec_stdout(
            "find '%s' -type f -not -path '*/local_llm/*' -not -path '*/.*' | sed 's#^%s/##' | sort"
            % (ws, ws)
        )
        changed = [
            l
            for l in ls.splitlines()
            if l and not l.startswith(("build.", "fix.", "local_llm"))
        ]
        provider, model = "local_lmstudio", LMSTUDIO_MODEL
    else:
        ws = host_workspace(run_id)
        write_text(os.path.join(ws, "src", "greeter.py"), GREETER_OK)
        changed = ["src/greeter.py"]
        provider, model = "embedded", "embedded"
    dur = time.time() - t0
    log_job(run_id, "fix", attempt, "applied", dur * 1000, backend, provider, model)
    return {
        "contract": C_FIX,
        "run_id": run_id,
        "task": payload.get("task", ""),
        "repository": payload.get("repository", ""),
        "fixture": fixture,
        "execution_backend": backend,
        "max_attempts": payload.get("max_attempts", 2),
        "config": {
            "adapter_base_url": payload.get("config", {}).get(
                "adapter_base_url", CANONICAL_URL
            )
        },
        "fix": {
            "applied": True,
            "changed_paths": changed,
            "strategy_delta_applied": delta[:200],
            "attempt": attempt,
        },
        "observability": {"provider": provider, "model": model},
    }


SECRET_RE = re.compile(
    r"(api[_-]?key|password|passwd|secret|token|bearer)\s*[=:]\s*[\"'][^\"']+[\"']",
    re.I,
)


def job_review(payload, kind):
    run_id = payload["run_id"]
    backend = payload.get("execution_backend", "embedded")
    fixture = payload.get("fixture")
    verification = payload.get("verification") or {}
    passed = bool(verification.get("passed", True))
    t0 = time.time()

    if kind == "security" and fixture == "security_critical_blocking":
        review = {
            "status": "FAIL",
            "severity": "CRITICAL",
            "blocking": True,
            "recommendation": "BLOCK",
            "findings": [
                {
                    "path": "src/greeter.py",
                    "message": "fixture: hardcoded credential pattern detected",
                }
            ],
        }
    elif kind == "quality" and fixture == "review_fix":
        review = {
            "status": "FAIL",
            "severity": "LOW",
            "blocking": False,
            "recommendation": "FIX",
            "findings": [
                {"path": "src/greeter.py", "message": "fixture: missing docstring"}
            ],
        }
    elif kind == "correctness" and fixture == "review_split":
        review = {
            "status": "FAIL",
            "severity": "MEDIUM",
            "blocking": False,
            "recommendation": "SPLIT",
            "findings": [
                {
                    "path": "tests/",
                    "message": "fixture: test coverage too large for single task",
                }
            ],
        }
    else:
        # Real rule-based review
        if backend == "opencode-builder-8001":
            ws = builder_workspace(run_id)
            files = {}
            for p in ["src/greeter.py", "tests/test_greeter.py"]:
                c = pct_exec_stdout("cat '%s/%s' 2>/dev/null" % (ws, p))
                if c:
                    files[p] = c
        else:
            ws = host_workspace(run_id)
            files = {
                p: read_text(os.path.join(ws, p)) or ""
                for p in ["src/greeter.py", "tests/test_greeter.py"]
            }
        findings = []
        if kind == "correctness":
            src = files.get("src/greeter.py", "")
            tests = files.get("tests/test_greeter.py", "")
            if "def greet" not in src:
                findings.append(
                    {"path": "src/greeter.py", "message": "greet function missing"}
                )
            if "test_returns_hello" not in tests:
                findings.append(
                    {
                        "path": "tests/test_greeter.py",
                        "message": "test_returns_hello missing",
                    }
                )
            status = "PASS" if passed and not findings else "FAIL"
            severity = "MEDIUM" if findings else "INFO"
            blocking = bool(findings)
            recommendation = "FIX" if findings else "PASS"
        elif kind == "security":
            for p, c in files.items():
                m = SECRET_RE.search(c)
                if m:
                    findings.append(
                        {"path": p, "message": "secret-like pattern detected"}
                    )
            status = "FAIL" if findings else "PASS"
            severity = "CRITICAL" if findings else "INFO"
            blocking = bool(findings)
            recommendation = "BLOCK" if findings else "PASS"
        else:  # quality
            src = files.get("src/greeter.py", "")
            if "TODO" in src or "FIXME" in src:
                findings.append(
                    {"path": "src/greeter.py", "message": "TODO/FIXME markers present"}
                )
            if src and not src.endswith("\n"):
                findings.append(
                    {"path": "src/greeter.py", "message": "missing trailing newline"}
                )
            status = "FAIL" if findings else "PASS"
            severity = "LOW" if findings else "INFO"
            blocking = False
            recommendation = "FIX" if findings else "PASS"
        review = {
            "status": status,
            "severity": severity,
            "blocking": blocking,
            "recommendation": recommendation,
            "findings": findings,
        }

    dur = time.time() - t0
    provider = "local_lmstudio" if backend == "opencode-builder-8001" else "embedded"
    model = LMSTUDIO_MODEL if backend == "opencode-builder-8001" else "embedded"
    log_job(
        run_id,
        "review/" + kind,
        payload.get("attempt", 1),
        "reviewed",
        dur * 1000,
        backend,
        provider,
        model,
    )
    return {
        "contract": C_REVIEW,
        "run_id": run_id,
        "job": "review/" + kind,
        "task": payload.get("task", ""),
        "repository": payload.get("repository", ""),
        "fixture": fixture,
        "execution_backend": backend,
        "config": {
            "adapter_base_url": payload.get("config", {}).get(
                "adapter_base_url", CANONICAL_URL
            )
        },
        "review": review,
        "observability": {"provider": provider, "model": model},
    }


# ------------------------------------------------------------------ http ----
class Handler(BaseHTTPRequestHandler):
    server_version = "AutoDevHarnessAdapter/1.0"
    protocol_version = "HTTP/1.1"

    def _auth_ok(self):
        return self.headers.get("X-Harness-Token") == TOKEN

    def _send(self, code, obj):
        body = obj.encode() if isinstance(obj, str) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/healthz", "/"):
            self._send(
                200,
                {"status": "ok", "service": "autodev-harness-adapter", "version": "v1"},
            )
        else:
            self._send(404, err("NOT_FOUND", self.path))

    def do_POST(self):
        if not self._auth_ok():
            self._send(401, err("UNAUTHORIZED", "missing or invalid X-Harness-Token"))
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0 or length > MAX_BODY:
                self._send(400, err("BAD_BODY", "body size out of range"))
                return
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self._send(400, err("INVALID_JSON", "body must be valid JSON"))
            return
        run_id = payload.get("run_id")
        if not isinstance(run_id, str) or not RUN_ID_RE.match(run_id):
            self._send(
                400, err("INVALID_RUN_ID", "run_id must match [A-Za-z0-9_-]{1,64}")
            )
            return
        backend = payload.get("execution_backend", "embedded")
        if backend not in VALID_BACKENDS:
            self._send(
                400,
                err(
                    "INVALID_BACKEND",
                    "execution_backend must be one of %s" % sorted(VALID_BACKENDS),
                ),
            )
            return

        path = self.path.split("?")[0]
        routes = {
            "/baseline": lambda p: job_baseline(p),
            "/research/code": lambda p: job_research(p, "code"),
            "/research/docs": lambda p: job_research(p, "docs"),
            "/research/tests": lambda p: job_research(p, "tests"),
            "/plan": lambda p: job_plan(p),
            "/build": lambda p: job_build(p),
            "/verify": lambda p: job_verify(p),
            "/fix": lambda p: job_fix(p),
            "/review/correctness": lambda p: job_review(p, "correctness"),
            "/review/security": lambda p: job_review(p, "security"),
            "/review/quality": lambda p: job_review(p, "quality"),
        }
        fn = routes.get(path)
        if fn is None:
            self._send(404, err("NOT_FOUND", path))
            return
        try:
            self._send(200, fn(payload))
        except subprocess.TimeoutExpired:
            self._send(504, err("JOB_TIMEOUT", "job exceeded time limit"))
        except Exception as e:  # noqa: BLE001
            self._send(500, err("JOB_ERROR", "%s: %s" % (type(e).__name__, e)[:300]))

    def log_message(self, fmt, *args):
        pass


def main():
    global TOKEN
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            TOKEN = f.read().strip()
    except OSError:
        print("FATAL: token file missing at %s" % TOKEN_FILE, file=sys.stderr)
        sys.exit(1)
    if not TOKEN:
        print("FATAL: empty token", file=sys.stderr)
        sys.exit(1)
    srv = ThreadingHTTPServer((BIND_HOST, BIND_PORT), Handler)
    print(
        "autodev-harness-adapter listening on %s:%s" % (BIND_HOST, BIND_PORT),
        flush=True,
    )
    srv.serve_forever()


if __name__ == "__main__":
    main()
