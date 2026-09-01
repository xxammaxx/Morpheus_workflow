"""Deterministic capability evidence, refresh, TTL, and policy regressions."""

import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from providers.capabilities import (  # noqa: E402
    TOOL_CONTRACT_VERSION,
    CapabilityRegistry,
    merge_empirical_capabilities,
)
from providers.catalog import ProviderCatalog  # noqa: E402
from providers.protocol import RouteRequest, normalized_entry  # noqa: E402
from providers.router import ProviderRouter  # noqa: E402


NOW = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
PROBE_VERSION = "morpheus-build-capability-v1"


def evidence(provider="opencode", model="big-pickle", verified="2026-09-01T09:00:00+00:00",
             probe_version=PROBE_VERSION, tool_contract=TOOL_CONTRACT_VERSION):
    return {
        "provider": provider,
        "model": model,
        "capabilities": {
            "BUILD_CAPABLE": True,
            "TOOL_CAPABLE": True,
            "STRUCTURED_OUTPUT_CAPABLE": True,
        },
        "probe_status": "PASS",
        "probe_version": probe_version,
        "tool_contract_version": tool_contract,
        "verified_at": verified,
        "evidence_hash": "fixture-evidence-hash",
        "identity": {
            "provider": provider,
            "model": model,
            "tool_contract_version": tool_contract,
        },
    }


def live_entry(model="big-pickle", **values):
    defaults = {
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
        "privacy_policy": {"version": "v1", "approved": True, "provider_policy_ref": "fixture", "request_data_class": "PRIVATE_CODE", "retention_class": "provider-default"},
        "route_exists": True,
        "route_cost_proven": True,
        "free_evidence": ["CATALOG_FREE", "ACCOUNT_FREE_ELIGIBLE", "DIRECT_LIVE_PROVEN", "ADAPTER_LIVE_PROVEN", "SELECTION_TO_EXECUTION_PROVEN"],
        "capabilities": {"BUILD_CAPABLE": False, "TOOL_CAPABLE": True, "STRUCTURED_OUTPUT_CAPABLE": False},
        "tool_probe": "PASS",
        "structured_output_score": 1.0,
    }
    defaults.update(values)
    return normalized_entry("opencode", model, "ct8001://opencode", **defaults)


def test_empirical_build_capability_survives_live_refresh(tmp_path, monkeypatch):
    cap_path = tmp_path / "provider-capabilities.json"
    registry = CapabilityRegistry(str(cap_path))
    registry.record_probe("opencode", "big-pickle", evidence("opencode", "big-pickle")["capabilities"], PROBE_VERSION, verified_at="2026-09-01T09:00:00+00:00", evidence_hash="fixture-evidence-hash")
    monkeypatch.setattr("providers.catalog.refresh_catalog", lambda *a, **k: {"entries": [{"provider": "opencode", "model": "big-pickle", "id": "big-pickle", "pricing": {"prompt": 0, "completion": 0}, "capabilities": {"toolcall": True}}]})
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"opencode": {"type": "api", "key": "fixture"}}))
    catalog = ProviderCatalog(path=str(tmp_path / "catalog.json"), adapters={"opencode": type("A", (), {"base_url": "ct8001://opencode", "credential_env": ""})()})
    catalog.capability_registry = registry
    catalog.entries = [live_entry()]
    catalog.refresh_live(auth_file=str(auth), opencode_bin="unused")
    item = catalog.entries[0]
    assert item["capabilities"]["BUILD_CAPABLE"] is True
    assert item["capability_status"] == "PROVEN"
    assert ProviderRouter(catalog).select(RouteRequest(provider="opencode", model="big-pickle", task_class="build", task_profile={"requires_code": True, "requires_repository_tools": True}))


def test_fresh_empirical_capability_survives_refresh(tmp_path):
    entry = live_entry()
    result = merge_empirical_capabilities(entry, evidence(), now=NOW, ttl_seconds=7200)
    assert result["valid"] is True and entry["capabilities"]["BUILD_CAPABLE"] is True


def test_expired_empirical_capability_requires_reprobe():
    entry = live_entry()
    result = merge_empirical_capabilities(entry, evidence(verified="2026-08-31T08:00:00+00:00"), now=NOW, ttl_seconds=3600)
    assert result["valid"] is False
    assert entry["capability_needs_reprobe"] is True
    assert entry["capabilities"]["BUILD_CAPABLE"] is False


def test_model_identity_change_invalidates_probe():
    entry = live_entry("other-model")
    assert merge_empirical_capabilities(entry, evidence(), now=NOW)["valid"] is False


def test_provider_identity_change_invalidates_probe():
    entry = live_entry()
    entry["provider"] = "other-provider"
    assert merge_empirical_capabilities(entry, evidence(), now=NOW)["valid"] is False


def test_probe_version_change_invalidates_probe():
    entry = live_entry()
    assert merge_empirical_capabilities(entry, evidence(probe_version="old"), now=NOW, expected_probe_version=PROBE_VERSION)["valid"] is False


def test_tool_contract_change_invalidates_probe():
    entry = live_entry()
    assert merge_empirical_capabilities(entry, evidence(tool_contract="old-contract"), now=NOW)["valid"] is False


def test_store_corruption_fails_closed(tmp_path):
    path = tmp_path / "provider-capabilities.json"
    path.write_text("{not-json")
    assert CapabilityRegistry(str(path)).get("opencode", "big-pickle") is None
    path.write_text(json.dumps({"entries": {"opencode/big-pickle": {"capabilities": {"BUILD_CAPABLE": True}}}}))
    assert CapabilityRegistry(str(path)).get("opencode", "big-pickle")["capabilities"]["BUILD_CAPABLE"] is True


def test_missing_model_not_build_eligible_despite_old_probe(tmp_path):
    entry = live_entry()
    entry["availability"] = False
    router = ProviderRouter(ProviderCatalog(path=str(tmp_path / "catalog.json"), adapters={}))
    router.catalog.entries = [entry]
    try:
        router.select(RouteRequest(provider="opencode", model="big-pickle", task_class="build", task_profile={"requires_code": True, "requires_repository_tools": True}))
    except Exception as exc:
        assert "NO_ELIGIBLE" in str(exc)
    else:
        raise AssertionError("missing model was eligible")
