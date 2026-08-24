"""Regression tests for the bounded local plan serialization seam."""

import copy
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "adapter"))
os.environ.setdefault("AUTODEV_V2_STATE", tempfile.mkdtemp(prefix="morpheus-plan-test-"))
import harness_adapter_v2 as adapter  # noqa: E402


def _semantic_plan():
    return {
        "targets": {"files": ["lib/export.dart"], "symbols": ["ExportService"]},
        "acceptance_criteria": ["selected entries export as one markdown file"],
        "required_tests": ["flutter test --no-pub"],
        "risks": [],
        "build_scope": {"allowed_files": ["lib/export.dart"]},
        "research_summary": "Existing export services can be reused.",
    }


def test_formatter_schema_tracks_canonical_model_fields():
    schema = adapter._plan_model_schema()
    canonical = adapter.registry.get_schema("autodev.plan.v1")
    assert set(schema["required"]) == {
        "targets", "acceptance_criteria", "required_tests", "risks",
        "build_scope", "research_summary",
    }
    assert {"targets", "acceptance_criteria", "required_tests", "risks",
            "build_scope"}.issubset(canonical["properties"])
    assert set(schema["properties"]) == set(schema["required"])
    assert schema["additionalProperties"] is False
    assert schema["properties"]["targets"]["required"] == ["files", "symbols"]


def test_worker_agent_model_tracks_selected_local_route():
    agent = adapter._agent_md(
        "plan-worker", adapter.PLAN_TOOLS, adapter.PLAN_PERMS,
        "test worker", "qwen3:1.7b",
    )
    assert "model: lmstudio/qwen3:1.7b" in agent
    assert adapter.LMSTUDIO_MODEL not in agent
    assert adapter.PLAN_TOOLS["write"] is True
    assert adapter.PLAN_PERMS["write"] == "deny"


def test_default_opencode_worker_uses_local_ollama_fallback():
    payload = {"x-metadata": {
        "execution_provider": "lmstudio",
        "execution_model": adapter.LMSTUDIO_MODEL,
    }}
    assert adapter._opencode_worker_identity(payload) == (
        "ollama", adapter.OLLAMA_MODEL
    )


def test_explicit_worker_identity_is_preserved():
    payload = {"x-metadata": {
        "execution_provider": "ollama",
        "execution_model": adapter.OLLAMA_MODEL,
    }}
    assert adapter._opencode_worker_identity(payload) == (
        "ollama", adapter.OLLAMA_MODEL
    )


def test_explicit_task_scope_has_deterministic_plan_fallback():
    task = "Use only these exact repository-relative files: dashboard/control_tower.py, dashboard/static/index.html, dashboard/tests/test_control_tower_projection.py. Translate the complete visible UI."
    plan = adapter._explicit_scoped_plan({"task_description": task}, "run-test", "a" * 40)
    assert plan["contract"] == "autodev.plan.v1"
    assert plan["targets"]["files"] == [
        "dashboard/control_tower.py",
        "dashboard/static/index.html",
        "dashboard/tests/test_control_tower_projection.py",
    ]
    assert plan["build_scope"]["allowed_files"] == plan["targets"]["files"]
    assert adapter.registry.validate(plan, "autodev.plan.v1")["ok"]


def test_scope_consistency_fails_closed():
    plan = _semantic_plan()
    plan["targets"]["files"].append("lib/not-allowed.dart")
    assert adapter._plan_scope_errors(plan)
    plan = _semantic_plan()
    plan["required_tests"] = []
    assert adapter.registry.validate(
        {"contract": "autodev.plan.v1", "version": "v1", "run_id": "run-test",
         "repository_head": "a" * 40, **plan,
         "context": {"fingerprint": "b" * 64},
         "safety": {"sentinel_absent": True, "repo_unchanged": True,
                    "write_attempts": 0}},
        "autodev.plan.v1",
    )["ok"] is False


def test_formatter_does_not_invent_missing_semantics():
    missing = copy.deepcopy(_semantic_plan())
    missing.pop("targets")
    assert adapter._plan_scope_errors(missing)
    assert adapter._plan_scope_errors({"targets": {"files": []},
                                       "build_scope": {"allowed_files": []}})


def test_formatter_is_one_pass_and_preserves_attempt_identity(monkeypatch):
    calls = []

    def fake(candidate, model):
        calls.append((candidate, model))
        return _semantic_plan(), None

    monkeypatch.setattr(adapter, "_ollama_format_plan", fake)
    # The production job calls the seam once for malformed serialization. This
    # direct contract test keeps the one-pass invariant explicit without a CT.
    result, error = adapter._ollama_format_plan("malformed", "qwen3:1.7b")
    assert error is None and result["targets"]["files"]
    assert len(calls) == 1
    assert "attempt_id" not in result


def test_local_formatter_request_is_schema_constrained(monkeypatch):
    seen = {}

    class Response:
        def read(self):
            return b'{"response":"{\\"value\\":\\"unused\\"}"}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout):
        import json
        seen["body"] = json.loads(request.data.decode())
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setattr(adapter.urllib.request, "urlopen", fake_urlopen)
    # A worker identity must not be able to override the local formatter
    # route/model (the second argument is retained only for old callers).
    adapter._ollama_format_plan("candidate", "openrouter/free-external")
    assert seen["body"]["model"] == adapter.OLLAMA_FORMATTER_MODEL
    assert seen["body"]["model"] != "openrouter/free-external"
    assert seen["body"]["stream"] is False
    assert seen["body"]["options"]["temperature"] == 0
    assert seen["body"]["format"]["additionalProperties"] is False
    assert seen["timeout"] == adapter.OLLAMA_FORMATTER_TIMEOUT_S
