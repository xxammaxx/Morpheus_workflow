"""Provider-free canonical admission and preflight/dispatch equivalence."""

import copy
import os
import sys

sys.path.insert(0, os.fspath(__import__("pathlib").Path(__file__).resolve().parents[1]))

from providers.catalog import ProviderCatalog
from providers.capabilities import classify_task
from providers.protocol import (
    RouteRequest,
    evaluate_route_admission,
    free_eligibility,
    normalized_entry,
)
from providers.router import ProviderRouter
from providers.runtime import ProviderRuntime


def request(provider="opencode", model="big-pickle", task_class="plan"):
    return RouteRequest(
        provider=provider,
        model=model,
        task_class=task_class,
        task_profile=classify_task({"task_class": task_class}, task_class),
        privacy_class="ALLOWED",
        free_first=True,
    )


def entry(**changes):
    values = {
        "availability": True,
        "health": "HEALTHY",
        "authenticated": True,
        "account_class": "verified-free-account",
        "cost_class": "FREE_HARD_STOP",
        "input_price": 0,
        "output_price": 0,
        "zero_cost_verified": True,
        "usage_terms_permit": True,
        "automatic_paid_fallback": False,
        "privacy_class": "ALLOWED",
        "route_exists": True,
        "route_cost_proven": True,
        "free_evidence": ["CATALOG_FREE", "ACCOUNT_FREE_ELIGIBLE"],
        "capabilities": {"PLAN_CAPABLE": True, "STRUCTURED_OUTPUT_CAPABLE": True},
        "structured_output_score": 1.0,
        "probe_attempted": False,
        "promoted_free_eligible": False,
        "actual_cost_proof": None,
        "quarantined": False,
        "provider": "opencode",
        "model": "big-pickle",
        "endpoint": "http://provider.invalid/v1",
    }
    values.update(changes)
    return normalized_entry(values.pop("provider"), values.pop("model"), values.pop("endpoint"), **values)


def test_status_false_green_is_not_routable():
    item = entry(probe_attempted=True, promoted_free_eligible=False)
    free_eligibility(item, require_execution=False)
    assert item["free_eligible"] is True
    result = evaluate_route_admission(request(), item)
    assert result["eligible"] is False
    assert {reason["code"] for reason in result["reasons"]} == {"PROBE_NOT_ELIGIBLE", "PROMOTION_NOT_ELIGIBLE"}


def test_exact_valid_plan_matches_router():
    item = entry()
    result = evaluate_route_admission(request(), item)
    catalog = ProviderCatalog(path="/tmp/morpheus-admission-test-catalog.json", adapters={})
    catalog.entries = [item]
    selected = ProviderRouter(catalog).select(request())
    assert result["eligible"] is True
    assert (selected["selected_provider"], selected["selected_model"]) == ("opencode", "big-pickle")


def test_capability_and_policy_gates_are_explained():
    for changes, code in (
        ({"capabilities": {"PLAN_CAPABLE": False, "STRUCTURED_OUTPUT_CAPABLE": True}}, "PLAN_CAPABILITY_MISSING"),
        ({"capabilities": {"PLAN_CAPABLE": True, "STRUCTURED_OUTPUT_CAPABLE": False}}, "STRUCTURED_OUTPUT_CAPABILITY_MISSING"),
        ({"structured_output_score": 0.79}, "STRUCTURED_OUTPUT_SCORE_TOO_LOW"),
        ({"quarantined": True}, "MODEL_QUARANTINED"),
        ({"provider": "deepseek", "model": "deepseek-chat"}, "DEEPSEEK_RETIRED"),
        ({"cost_class": "PAID", "input_price": 1, "output_price": 1}, "COST_CLASS_NOT_FREE"),
    ):
        result = evaluate_route_admission(request(changes.get("provider", "opencode"), changes.get("model", "big-pickle")), entry(**changes))
        assert result["eligible"] is False
        assert code in {reason["code"] for reason in result["reasons"]}


def test_preflight_refresh_equivalence(monkeypatch, tmp_path):
    catalog = ProviderCatalog(path=os.fspath(tmp_path / "catalog.json"), adapters={})
    catalog.entries = [entry()]
    runtime = ProviderRuntime(catalog=catalog)
    monkeypatch.setattr(catalog, "refresh_live", lambda: catalog.entries.__setitem__(0, entry(structured_output_score=0.5)) or {"refresh": "PASS"})
    preflight = runtime.preflight(request(), refresh=True)
    router_result = ProviderRouter(catalog).candidates(request())
    assert preflight["eligible"] is False
    assert router_result == []
    assert any(reason["code"] == "STRUCTURED_OUTPUT_SCORE_TOO_LOW" for reason in preflight["reasons"])


def test_exact_route_has_no_substitution():
    catalog = ProviderCatalog(path="/tmp/morpheus-admission-test-catalog-2.json", adapters={})
    catalog.entries = [entry(provider="ollama", model="other")]
    runtime = ProviderRuntime(catalog=catalog)
    result = runtime.preflight(request(), refresh=False)
    assert result["eligible"] is False
    assert result["reasons"][0]["code"] == "MODEL_NOT_IN_CATALOG"
