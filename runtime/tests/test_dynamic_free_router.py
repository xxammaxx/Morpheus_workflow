"""Acceptance matrix for the live, zero-cost, task-aware router."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers.catalog import ProviderCatalog
from providers.protocol import DeepSeekPolicyViolation, NoEligibleProvider, RouteRequest, normalized_entry, probe_eligibility
from providers.catalog import apply_policy
from providers.router import ProviderRouter
from providers.session import RunRoutingState


def model(provider, name, **kwargs):
    values = {
        "availability": True,
        "health": "HEALTHY",
        "authenticated": True,
        "account_class": "opencode-api-key",
        "cost_class": "FREE_HARD_STOP",
        "input_price": 0,
        "output_price": 0,
        "zero_cost_verified": True,
        "usage_terms_permit": True,
        "automatic_paid_fallback": False,
        "privacy_class": "ALLOWED",
        "route_exists": True,
        "route_cost_proven": True,
        "capabilities": {
            "RESEARCH_CAPABLE": True,
            "PLAN_CAPABLE": True,
            "BUILD_CAPABLE": True,
            "REVIEW_CAPABLE": True,
        },
        "free_evidence": ["CATALOG_FREE", "ACCOUNT_FREE_ELIGIBLE"],
    }
    values.update(kwargs)
    return normalized_entry(provider, name, "http://%s.invalid" % provider, **values)


def catalog(tmp_path, entries):
    result = ProviderCatalog(path=str(tmp_path / "catalog.json"), adapters={})
    result.entries = entries
    return result


def test_catalog_changes_without_source_model_list(tmp_path):
    first = catalog(tmp_path, [model("zen", "model1"), model("zen", "model2")])
    request = RouteRequest(task_class="research", run_id="run-a", task_id="task")
    assert ProviderRouter(first).select(request)["selected_model"] in {"model1", "model2"}
    second = catalog(tmp_path, [model("zen", "model2"), model("zen", "model3")])
    assert ProviderRouter(second).select(request)["selected_model"] in {"model2", "model3"}


def test_free_auth_and_deepseek_gates(tmp_path):
    entries = [
        model("zen", "free", account_class="opencode-api-key"),
        model("paid", "paid", cost_class="PAID", input_price=1, output_price=1, zero_cost_verified=False),
        model("missing", "unauthenticated", authenticated=False),
        model("deepseek", "deepseek-chat"),
    ]
    selected = ProviderRouter(catalog(tmp_path, entries)).select(RouteRequest(task_class="research"))
    assert selected["selected_provider"] == "zen"


def test_deepseek_explicit_request_fails_before_selection(tmp_path):
    deepseek = model("openrouter", "deepseek/deepseek-chat")
    assert deepseek["free_eligible"] is False
    assert deepseek["catalog_eligible"] is False
    router = ProviderRouter(catalog(tmp_path, [deepseek]))
    try:
        router.select(RouteRequest(provider="openrouter", model="deepseek/deepseek-chat"))
    except DeepSeekPolicyViolation:
        pass
    else:
        raise AssertionError("explicit DeepSeek request was not rejected")


def test_openrouter_free_suffix_is_catalog_eligible():
    entry = model("openrouter", "cohere/north-mini-code:free")
    apply_policy(entry, "openrouter", "opencode-api-key")
    assert entry["zero_cost_verified"] is True
    assert entry["free_eligible"] is False  # execution proof is still required
    assert probe_eligibility(entry) is True
    assert entry["cost_class"] == "FREE_HARD_STOP"


def test_vision_is_hard_filter(tmp_path):
    entries = [
        model("zen", "coder"),
        model(
            "zen", "vision", supports_vision=True,
            capabilities={"RESEARCH_CAPABLE": True, "VISION_CAPABLE": True},
        ),
    ]
    request = RouteRequest(
        task_class="research",
        task_profile={"requires_vision": True},
    )
    assert ProviderRouter(catalog(tmp_path, entries)).select(request)["selected_model"] == "vision"


def test_no_vision_model_fails_honestly(tmp_path):
    request = RouteRequest(task_class="research", task_profile={"requires_vision": True})
    try:
        ProviderRouter(catalog(tmp_path, [model("zen", "text-only")])).select(request)
    except NoEligibleProvider as exc:
        assert str(exc) == "NO_ELIGIBLE_FREE_PROVIDER"
    else:
        raise AssertionError("text-only model selected for vision task")


def test_tool_and_structured_gates(tmp_path):
    entries = [
        model("zen", "reasoner", capabilities={"BUILD_CAPABLE": True}),
        model(
            "zen", "builder", tool_probe="PASS",
            capabilities={"BUILD_CAPABLE": True, "TOOL_CAPABLE": True},
        ),
        model(
            "zen", "structured", structured_output_score=1.0,
            capabilities={"PLAN_CAPABLE": True, "STRUCTURED_OUTPUT_CAPABLE": True},
        ),
    ]
    router = ProviderRouter(catalog(tmp_path, entries))
    build = router.select(RouteRequest(task_class="build", task_profile={"requires_code": True, "requires_repository_tools": True}))
    assert build["selected_model"] == "builder"
    plan = router.select(RouteRequest(task_class="plan", task_profile={"requires_structured_output": True}))
    assert plan["selected_model"] == "structured"


def test_two_transport_failures_exclude_for_run_and_restart_persists(tmp_path):
    ledger = str(tmp_path / "runs.jsonl")
    router = ProviderRouter(catalog(tmp_path, [model("zen", "a"), model("zen", "b")]), state=RunRoutingState(ledger))
    router.record_transport_failure("run", "zen", "a")
    router.record_transport_failure("run", "zen", "a")
    request = RouteRequest(task_class="research", run_id="run", task_id="task")
    assert router.select(request)["selected_model"] == "b"
    restarted = ProviderRouter(router.catalog, state=RunRoutingState(ledger))
    assert restarted.select(request)["selected_model"] == "b"
    new_run = RouteRequest(task_class="research", run_id="new-run", task_id="task")
    assert restarted.select(new_run)["selected_model"] in {"a", "b"}


def test_semantic_threshold_is_task_scoped(tmp_path, monkeypatch):
    monkeypatch.setenv("MAX_SEMANTIC_FAILURES_PER_MODEL_PER_TASK", "2")
    router = ProviderRouter(catalog(tmp_path, [model("zen", "a"), model("zen", "b")]), state=RunRoutingState(str(tmp_path / "runs.jsonl")))
    router.record_semantic_failure("run", "hard-task", "zen", "a")
    assert router.select(RouteRequest(task_class="research", run_id="run", task_id="hard-task"))["selected_model"] == "a"
    router.record_semantic_failure("run", "hard-task", "zen", "a")
    assert router.select(RouteRequest(task_class="research", run_id="run", task_id="hard-task"))["selected_model"] == "b"
    assert router.select(RouteRequest(task_class="research", run_id="run", task_id="easy-task"))["selected_model"] == "a"
