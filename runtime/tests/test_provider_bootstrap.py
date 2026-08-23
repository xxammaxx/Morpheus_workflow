#!/usr/bin/env python3
"""Regression tests for first-probe versus promoted-route eligibility."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from providers.catalog import ProviderCatalog, apply_policy
from providers.protocol import (
    normalized_entry,
    probe_eligibility,
    promotion_eligibility,
)
from providers.router import NoEligibleProvider, ProviderRouter, RouteRequest


def route(provider="openrouter", model="openrouter/free", **extra):
    values = dict(
        availability=True,
        health="HEALTHY",
        credential_valid=True,
        route_exists=True,
        cost_class="FREE_HARD_STOP",
        input_price=0,
        output_price=0,
        billing_risk=False,
        usage_terms_permit=True,
        automatic_paid_fallback=False,
        privacy_class="ALLOWED",
        route_cost_proven=True,
        capabilities={"RESEARCH_CAPABLE": True},
    )
    values.update(extra)
    return normalized_entry(provider, model, "http://provider.invalid", **values)


def check(name, value):
    if not value:
        raise AssertionError(name)
    print("PASS " + name)


def main():
    unsafe = route(cost_class="UNKNOWN", input_price=None, output_price=None)
    check("T1_UNSAFE_COST_PROBE_DENIED", not probe_eligibility(unsafe))
    safe = route()
    check("T2_SAFE_ZERO_COST_PROBE_ALLOWED", probe_eligibility(safe))
    with tempfile.TemporaryDirectory() as state:
        catalog = ProviderCatalog(path=os.path.join(state, "catalog.json"), adapters={})
        catalog.entries = [safe]
        router = ProviderRouter(catalog)
        decision = router.select(RouteRequest(task_class="research"))
        check("T3_SELECTION_DOES_NOT_REQUIRE_EXECUTION_PROOF", decision["selected_model"] == "openrouter/free")
        check("T4_PROMOTION_DENIED_BEFORE_PROBE", not promotion_eligibility(safe, decision))
        decision.update(
            {
                "probe_attempted": True,
                "execution_proof": "PASS",
                "selection_to_execution_proven": True,
                "actual_cost_proof": "CATALOG_HARD_ZERO",
                "actual_cost": None,
            }
        )
        check("T5_PROMOTION_REQUIRES_ALL_GATES", promotion_eligibility(safe, decision))
        failed = dict(decision, execution_proof="NOT_PROVEN")
        check("T6_FAILED_PROBE_NOT_PROMOTED", not promotion_eligibility(safe, failed))

    groq = route(provider="groq", model="openai/gpt-oss-20b", cost_class="UNKNOWN", input_price=None, output_price=None)
    apply_policy(groq, "groq")
    check("T7_GROQ_UNKNOWN_ACCOUNT_FAILS_CLOSED", groq["cost_class"] == "UNKNOWN" and not groq["free_eligible"])
    deepseek = route(provider="deepseek", model="deepseek-chat", cost_class="PAID", input_price=0.14, output_price=0.28)
    check("T8_DEEPSEEK_PROBE_DENIED", not probe_eligibility(deepseek))
    paid = route(provider="paid-provider", model="paid-model", cost_class="PAID", input_price=1, output_price=1)
    check("T9_PAID_ROUTE_PROBE_DENIED", not probe_eligibility(paid))
    try:
        ProviderRouter(ProviderCatalog(path=os.path.join(tempfile.gettempdir(), "empty-bootstrap.json"), adapters={})).select(RouteRequest(provider="deepseek"))
    except NoEligibleProvider:
        check("T10_NO_ELIGIBLE_PAID_PROVIDER", True)
    print("PROVIDER_BOOTSTRAP acceptance tests passed")


if __name__ == "__main__":
    main()
