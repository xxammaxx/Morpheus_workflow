"""Regression coverage for model identity admission and catalog authority."""

import importlib.util
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from providers.adapters import ProviderAdapter
from providers.catalog import ProviderCatalog
from providers.protocol import (
    DeepSeekPolicyViolation,
    NoEligibleProvider,
    RouteRequest,
    is_valid_model_identifier,
    normalized_entry,
)
from providers.router import ProviderRouter
from providers.runtime import ProviderRuntime


MODEL = "llama-3.2-1b-instruct@q4_k_m"


def local_entry(model=MODEL, endpoint="http://127.0.0.1:1234/v1"):
    return normalized_entry(
        "lmstudio",
        model,
        endpoint,
        availability=True,
        health="HEALTHY",
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
        capabilities={"RESEARCH_CAPABLE": True},
        free_evidence=["CATALOG_FREE", "ACCOUNT_FREE_ELIGIBLE"],
    )


def load_adapter(state):
    os.environ["AUTODEV_V2_STATE"] = state
    os.environ["AUTODEV_PROVIDER_CATALOG"] = os.path.join(state, "catalog.json")
    spec = importlib.util.spec_from_file_location(
        "model_identifier_adapter",
        os.path.join(os.path.dirname(__file__), "..", "..", "adapter", "harness_adapter_v2.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def issue(run_id):
    return {
        "contract": "autodev.issue.v1",
        "version": "v1",
        "run_id": run_id,
        "repository_ref": "xxammaxx/morpheus-builder-acceptance-20260825",
        "workspace": "model-identifier",
        "task_description": "deterministic model identity proof",
        "trace_id": "model-identifier-trace",
    }


def main():
    assert is_valid_model_identifier(MODEL)
    for value in ("bad\nmodel", "bad\rmodel", "bad\x00model", "bad\x01model", "bad;model", "bad`model", "bad$(id)"):
        assert not is_valid_model_identifier(value), repr(value)
    assert not is_valid_model_identifier("model with spaces")
    assert not is_valid_model_identifier("model\twith-tabs")
    assert not is_valid_model_identifier("model+with-plus")
    print("PASS MODEL_IDENTIFIER_LEXICAL_SECURITY")

    with tempfile.TemporaryDirectory() as state:
        endpoint = "http://127.0.0.1:1234/v1"
        catalog = ProviderCatalog(
            path=os.path.join(state, "router-catalog.json"),
            adapters={"lmstudio": ProviderAdapter("lmstudio", endpoint, "")},
        )
        catalog.entries = [local_entry(endpoint=endpoint)]
        router = ProviderRouter(catalog)
        decision = router.select(
            RouteRequest(provider="lmstudio", model=MODEL, task_class="research")
        )
        assert decision["selected_provider"] == "lmstudio"
        assert decision["selected_model"] == MODEL
        print("PASS CATALOG_VALID_LOCAL_MODEL_REACHES_ROUTE_SELECTION")

        try:
            router.select(RouteRequest(provider="lmstudio", model="safe-but-unknown"))
        except NoEligibleProvider as exc:
            assert str(exc) == "MODEL_NOT_IN_CATALOG"
        else:
            raise AssertionError("unknown model was not rejected")
        print("PASS UNKNOWN_SAFE_MODEL_FAILS_CLOSED")

        adapter = load_adapter(state)
        adapter._provider_runtime = ProviderRuntime(catalog=catalog, enabled=True)
        adapter._provider_runtime.begin_run = lambda run_id: None
        catalog.refresh_live = lambda: {"refresh": "PASS", "catalog_entries": 1}
        adapter.run_job_thread = lambda *args, **kwargs: None
        record, error = adapter._dispatch(
            "model-run", "model-job", "research.code", "model-attempt",
            "autodev.issue.v1", issue("model-run"),
            "opencode-builder-8001", provider="lmstudio", model=MODEL,
        )
        assert error is None
        assert record["route_decision"]["selected_model"] == MODEL
        print("PASS DISPATCH_ACCEPTS_CATALOG_VALID_AT_MODEL")

        _, error = adapter._dispatch(
            "unknown-run", "unknown-job", "research.code", "unknown-attempt",
            "autodev.issue.v1", issue("unknown-run"),
            "opencode-builder-8001", provider="lmstudio", model="safe-but-unknown",
        )
        assert error["error"]["code"] == "MODEL_NOT_IN_CATALOG"
        print("PASS UNKNOWN_MODEL_NOT_BAD_MODEL")

    try:
        ProviderRouter(catalog).select(
            RouteRequest(provider="openrouter", model="deepseek/deepseek-chat")
        )
    except DeepSeekPolicyViolation:
        print("PASS DEEPSEEK_RETIRED_UNCHANGED")
    else:
        raise AssertionError("DeepSeek bypassed policy")


if __name__ == "__main__":
    main()
