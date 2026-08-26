"""Regression coverage for the canonical Research failover boundary."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers.catalog import ProviderCatalog
from providers.protocol import NoEligibleProvider, RouteRequest, normalized_entry
from providers.router import ProviderRouter
from providers.session import RunRoutingState


ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "workflow" / "v2" / "generate_workflows_v2.py"
CONFIG = ROOT / "workflow" / "v2" / "config.json"


def research_model(tmp_path, name, provider="provider"):
    return normalized_entry(
        provider,
        name,
        "http://%s.invalid" % provider,
        availability=True,
        health="HEALTHY",
        authenticated=True,
        account_class="verified-free-account",
        cost_class="FREE_HARD_STOP",
        input_price=0,
        output_price=0,
        usage_terms_permit=True,
        automatic_paid_fallback=False,
        privacy_class="ALLOWED",
        capabilities={"RESEARCH_CAPABLE": True},
        free_evidence=["CATALOG_FREE", "ACCOUNT_FREE_ELIGIBLE"],
    )


def research_catalog(tmp_path, entries):
    catalog = ProviderCatalog(path=str(tmp_path / "catalog.json"), adapters={})
    catalog.entries = entries
    return catalog


def test_research_continues_after_three_models_are_exhausted(tmp_path):
    """A, B, and C fail twice; D remains eligible and must be selected."""
    entries = [research_model(tmp_path, name) for name in "abcde"]
    router = ProviderRouter(
        research_catalog(tmp_path, entries),
        state=RunRoutingState(str(tmp_path / "runs.jsonl")),
    )
    for name in "abc":
        router.record_transport_failure("research-run", "provider", name)
        router.record_transport_failure("research-run", "provider", name)

    request = RouteRequest(
        task_class="research", run_id="research-run", task_id="research.code"
    )
    assert router.select(request)["selected_model"] == "d"
    assert router.select(request)["selected_model"] == "d"


def test_research_reports_true_free_pool_exhaustion(tmp_path):
    entries = [research_model(tmp_path, name) for name in "abcde"]
    router = ProviderRouter(
        research_catalog(tmp_path, entries),
        state=RunRoutingState(str(tmp_path / "runs.jsonl")),
    )
    for name in "abcde":
        router.record_transport_failure("research-run", "provider", name)
        router.record_transport_failure("research-run", "provider", name)

    try:
        router.select(RouteRequest(task_class="research", run_id="research-run"))
    except NoEligibleProvider as exc:
        assert str(exc) == "NO_ELIGIBLE_FREE_PROVIDER"
    else:
        raise AssertionError("Research did not fail closed after true exhaustion")


def test_research_recovery_is_bounded_and_preserves_poll_budget(tmp_path):
    out = tmp_path / "workflows"
    subprocess.run([sys.executable, str(GENERATOR), str(CONFIG), str(out)], check=True)
    workflow = json.loads((out / "20 AutoDev Research Batch.json").read_text())
    names = {node["name"] for node in workflow["nodes"]}
    assert {"Retry Interrupted?", "Prepare Research Recovery"} <= names

    poll = next(node for node in workflow["nodes"] if node["name"] == "Poll Batch")
    assert "?polls={{ $json.polls || 0 }}" in poll["parameters"]["url"]
    assert any(
        node["name"] == "Limit?"
        and node["parameters"]["conditions"]["conditions"][0]["rightValue"] == 240
        for node in workflow["nodes"]
    )

    prep = next(
        node for node in workflow["nodes"] if node["name"] == "Prep Research Batch"
    )
    assert "timeout_s: 180" in prep["parameters"]["jsCode"]

    recovery = next(
        node for node in workflow["nodes"] if node["name"] == "Prepare Research Recovery"
    )
    recovery_js = recovery["parameters"]["jsCode"]
    assert "$items('Prep Research Batch')" in recovery_js
    assert ":research-batch:recovery-" in recovery_js
    assert "recovery_of" in recovery_js

    def has_edge(source, target, output):
        groups = workflow["connections"][source]["main"]
        return any(edge["node"] == target for edge in groups[output])

    assert has_edge("Batch Failed?", "Retry Interrupted?", 0)
    assert has_edge("Retry Interrupted?", "Prepare Research Recovery", 0)
    assert has_edge("Retry Interrupted?", "Batch Failed", 1)
    assert has_edge("Prepare Research Recovery", "Dispatch Research Batch", 0)


def test_research_transport_exclusions_survive_router_restart(tmp_path):
    ledger = str(tmp_path / "runs.jsonl")
    entries = [research_model(tmp_path, name) for name in "abcd"]
    catalog = research_catalog(tmp_path, entries)
    router = ProviderRouter(catalog, state=RunRoutingState(ledger))
    router.record_transport_failure("research-run", "provider", "a")
    router.record_transport_failure("research-run", "provider", "a")

    restarted = ProviderRouter(catalog, state=RunRoutingState(ledger))
    selected = restarted.select(
        RouteRequest(task_class="research", run_id="research-run", task_id="research.docs")
    )
    assert selected["selected_model"] != "a"


def test_research_timeout_kills_remote_opencode_attempt():
    source = (ROOT / "adapter" / "harness_adapter_v2.py").read_text()
    assert "timeout --kill-after=5s %ss %s run" in source
    assert "opencode research model attempt timed out" in source
    assert "        attempt_timeout_s,\n        OPENCODE_BIN," in source


def test_parallel_research_workers_use_distinct_artifacts():
    source = (ROOT / "adapter" / "harness_adapter_v2.py").read_text()
    assert 'output_name = ".opencode/research-%s.jsonl" % artifact_key' in source
    assert 'stderr_name = ".opencode/research-%s.stderr" % artifact_key' in source
    assert "agent_name = \"research-worker-%s\" % artifact_key" in source
