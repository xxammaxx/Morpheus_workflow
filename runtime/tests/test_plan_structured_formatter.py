"""Regression tests for dynamic OpenCode worker identity."""

import os
import sys
import tempfile
from pathlib import Path
import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "adapter"))
sys.path.insert(0, str(ROOT / "runtime"))
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


def test_worker_agent_model_tracks_dynamic_route():
    agent = adapter._agent_md(
        "plan-worker", adapter.PLAN_TOOLS, adapter.PLAN_PERMS,
        "test worker", "zen/live-model",
    )
    assert "model: zen/live-model" in agent
    assert "lmstudio/" not in agent
    assert "ollama/" not in agent
    assert adapter.PLAN_TOOLS["write"] is True
    assert adapter.PLAN_PERMS["write"] == "deny"


def test_unresolved_opencode_worker_fails_closed():
    with pytest.raises(RuntimeError, match="NO_ELIGIBLE_FREE_MODEL"):
        adapter._opencode_worker_identity({})


def test_explicit_dynamic_worker_identity_is_preserved():
    payload = {"x-metadata": {
        "execution_provider": "ollama",
        "execution_model": "qwen3.5:9b",
    }}
    assert adapter._opencode_worker_identity(payload) == ("ollama", "qwen3.5:9b")


def test_opencode_script_uses_selected_dynamic_route():
    script = adapter._opencode_script(
        "/tmp/autodev-v2-dynamic-test", "plan-worker", "model: zen/live-model",
        "Return JSON only", 30, "zen", "live-model",
    )
    assert "zen/live-model" in script
    assert "OPENCODE_CONFIG_CONTENT" in script
    assert "local_llm" not in script
    assert "LMSTUDIO" not in script
    assert "OLLAMA" not in script


def test_lmstudio_opencode_script_uses_trusted_openai_compatible_endpoint(monkeypatch):
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://192.168.1.50:1234")
    script = adapter._opencode_script(
        "/tmp/autodev-v2-lmstudio-test", "research-worker", "model: lmstudio",
        "Return JSON only", 30, "lmstudio", "llama-3.2-1b-instruct@q4_k_m",
    )
    assert "@ai-sdk/openai-compatible" in script
    assert "http://192.168.1.50:1234/v1" in script
    assert "lmstudio/llama-3.2-1b-instruct@q4_k_m" in script


def test_lmstudio_opencode_script_rejects_unsafe_endpoint(monkeypatch):
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234'$(touch /tmp/pwned)")
    with pytest.raises(RuntimeError, match="LMSTUDIO_ENDPOINT_INVALID"):
        adapter._opencode_script(
            "/tmp/autodev-v2-lmstudio-test", "research-worker", "model: lmstudio",
            "Return JSON only", 30, "lmstudio", "llama-3.2-1b-instruct@q4_k_m",
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


def test_plan_validation_does_not_invent_missing_semantics():
    missing = dict(_semantic_plan())
    missing.pop("targets")
    assert adapter._plan_scope_errors(missing)
    assert adapter._plan_scope_errors({"targets": {"files": []},
                                       "build_scope": {"allowed_files": []}})


def test_dashboard_scope_is_denied_for_runtime_builder():
    error = adapter._dashboard_scope_error({
        "build_scope": {"allowed_files": ["dashboard/control_tower.py"]},
        "targets": {"files": ["dashboard/control_tower.py"]},
    })
    assert error and "dashboard" in error
