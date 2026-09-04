"""Provider-free proof that explicit route requests cannot fail over."""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.fspath(Path(__file__).resolve().parents[1]))

from providers.catalog import ProviderCatalog
from providers.protocol import NoEligibleProvider, RouteRequest, normalized_entry
from providers.router import ProviderRouter


def entry(provider, model):
    return normalized_entry(
        provider,
        model,
        "http://provider.invalid/v1",
        availability=True,
        health="HEALTHY",
        authenticated=True,
        account_class="local",
        cost_class="LOCAL_ZERO_COST",
        input_price=0,
        output_price=0,
        zero_cost_verified=True,
        usage_terms_permit=True,
        automatic_paid_fallback=False,
        privacy_class="ALLOWED",
        route_exists=True,
        route_cost_proven=True,
        capabilities={"PLAN_CAPABLE": True, "STRUCTURED_OUTPUT_CAPABLE": True},
        structured_output_score=1.0,
        free_evidence=["CATALOG_FREE"],
    )


def test_exact_request_filters_all_alternates(tmp_path):
    catalog = ProviderCatalog(path=os.fspath(tmp_path / "catalog.json"), adapters={})
    catalog.entries = [
        entry("opencode", "big-pickle"),
        entry("lmstudio", "ministral"),
        entry("openrouter", "openrouter/free"),
        entry("ollama", "llama3"),
    ]
    decision = ProviderRouter(catalog).select(
        RouteRequest(provider="opencode", model="big-pickle", task_class="plan")
    )
    assert (decision["selected_provider"], decision["selected_model"]) == ("opencode", "big-pickle")

    catalog.entries = [entry("lmstudio", "ministral")]
    try:
        ProviderRouter(catalog).select(
            RouteRequest(provider="opencode", model="big-pickle", task_class="plan")
        )
    except NoEligibleProvider as exc:
        assert str(exc) == "MODEL_NOT_IN_CATALOG"
    else:
        raise AssertionError("exact request selected an alternate route")
