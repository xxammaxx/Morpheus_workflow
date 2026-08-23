#!/usr/bin/env python3
"""Offline provider runtime acceptance and failover tests."""

import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from contracts import registry
from providers.adapters import ProviderAdapter
from providers.catalog import ProviderCatalog
from providers.protocol import (
    NoEligibleProvider,
    ProviderFailure,
    RouteRequest,
    free_eligibility,
    normalized_entry,
)
from providers.router import AUTOMATIC_PAID_AGENT_ESCALATION, ProviderRouter
from providers.runtime import ProviderRuntime


def make_server(fail_status=None):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length).decode())
            if fail_status:
                self.send_response(fail_status)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            result = {
                "id": "request-1",
                "model": body.get("model"),
                "choices": [{"message": {"content": "proof"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                "cost": 0,
            }
            encoded = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def entry(provider, endpoint, model):
    return normalized_entry(
        provider,
        model,
        endpoint,
        availability=True,
        health="HEALTHY",
        account_class="verified-free-account",
        cost_class="FREE_HARD_STOP",
        input_price=0,
        output_price=0,
        usage_terms_permit=True,
        automatic_paid_fallback=False,
        privacy_class="ALLOWED",
        capabilities={"RESEARCH_CAPABLE": True},
        free_evidence=[
            "CATALOG_FREE",
            "ACCOUNT_FREE_ELIGIBLE",
            "DIRECT_LIVE_PROVEN",
            "ADAPTER_LIVE_PROVEN",
            "SELECTION_TO_EXECUTION_PROVEN",
        ],
    )


def runtime_with(entries, adapters, state):
    catalog = ProviderCatalog(
        path=os.path.join(state, "catalog.json"), adapters=adapters
    )
    catalog.entries = entries
    return ProviderRuntime(catalog=catalog, enabled=True)


def main():
    assert AUTOMATIC_PAID_AGENT_ESCALATION is False
    print("PASS AUTOMATIC_PAID_ESCALATION_DISABLED")
    unknown = entry("groq", "http://unused", "model-unknown")
    unknown["account_class"] = "unknown"
    assert free_eligibility(unknown) is False
    print("PASS ZERO_COST_UNKNOWN_ACCOUNT_REJECTED")

    private = entry("groq", "http://unused", "private-model")
    private["privacy_class"] = "ALLOWED"
    private["privacy_policy"] = {}
    assert free_eligibility(private, "PRIVATE_CODE") is False
    print("PASS PRIVACY_EVIDENCE_FAIL_CLOSED")

    with tempfile.TemporaryDirectory() as state:
        failing = make_server(503)
        healthy = make_server()
        failing_url = "http://127.0.0.1:%d" % failing.server_address[1]
        healthy_url = "http://127.0.0.1:%d" % healthy.server_address[1]
        adapters = {
            "groq": ProviderAdapter("groq", failing_url, ""),
            "openrouter": ProviderAdapter("openrouter", healthy_url, ""),
        }
        runtime = runtime_with(
            [
                entry("groq", failing_url, "groq-model"),
                entry("openrouter", healthy_url, "openrouter-model"),
            ],
            adapters,
            state,
        )
        execution = runtime.invoke_with_failover(
            RouteRequest(task_class="research"),
            [{"role": "user", "content": "probe"}],
            "research",
            5,
            "attempt-groq-to-openrouter",
        )
        assert execution.decision["selected_provider"] == "openrouter"
        assert execution.execution_proof["actual_provider"] == "openrouter"
        assert execution.attempt_id == "attempt-groq-to-openrouter"
        print("PASS PROVIDER_FAILOVER_GROQ_TO_OPENROUTER")
        print("PASS SEMANTIC_ATTEMPT_UNCHANGED_FORWARD")
        failing.shutdown()
        healthy.shutdown()

        failing = make_server(503)
        healthy = make_server()
        failing_url = "http://127.0.0.1:%d" % failing.server_address[1]
        healthy_url = "http://127.0.0.1:%d" % healthy.server_address[1]
        adapters = {
            "groq": ProviderAdapter("groq", healthy_url, ""),
            "openrouter": ProviderAdapter("openrouter", failing_url, ""),
        }
        runtime = runtime_with(
            [
                entry("groq", healthy_url, "groq-model"),
                entry("openrouter", failing_url, "openrouter-model"),
            ],
            adapters,
            state,
        )
        execution = runtime.invoke_with_failover(
            RouteRequest(provider="openrouter", task_class="research"),
            [{"role": "user", "content": "probe"}],
            "research",
            5,
            "attempt-openrouter-to-groq",
        )
        assert execution.decision["selected_provider"] == "groq"
        assert execution.execution_proof["actual_provider"] == "groq"
        assert execution.attempt_id == "attempt-openrouter-to-groq"
        print("PASS PROVIDER_FAILOVER_OPENROUTER_TO_GROQ")
        print("PASS SEMANTIC_ATTEMPT_UNCHANGED_REVERSE")
        failing.shutdown()
        healthy.shutdown()

        class DiscoveryAdapter(ProviderAdapter):
            def discover_models(self):
                return [
                    normalized_entry(
                        "groq",
                        "discovered-model",
                        "http://discovered",
                        availability=True,
                    )
                ]

        discovered = ProviderCatalog(
            path=os.path.join(state, "discovered.json"),
            adapters={"groq": DiscoveryAdapter("groq", "http://unused", "")},
        )
        assert discovered.refresh()["entry_count"] == 1
        print("PASS DYNAMIC_PROVIDER_MODEL_DISCOVERY")

        paid = entry("deepseek", "http://unused", "deepseek-model")
        paid.update({"cost_class": "PAID", "input_price": 1, "output_price": 1})
        catalog = ProviderCatalog(path=os.path.join(state, "paid.json"), adapters={})
        catalog.entries = [paid]
        try:
            ProviderRouter(catalog).select(RouteRequest(task_class="research"))
        except NoEligibleProvider as exc:
            assert str(exc) == "NO_ELIGIBLE_FREE_PROVIDER"
            print("PASS DEEPSEEK_AND_PAID_ROUTE_EXCLUDED")
        else:
            raise AssertionError("paid route selected")

        alias = entry("openrouter", "http://unused", "deepseek/free-alias")
        alias_catalog = ProviderCatalog(
            path=os.path.join(state, "alias.json"), adapters={}
        )
        alias_catalog.entries = [alias]
        try:
            ProviderRouter(alias_catalog).select(RouteRequest(task_class="research"))
        except NoEligibleProvider:
            print("PASS DEEPSEEK_MODEL_ALIAS_EXCLUDED")
        else:
            raise AssertionError("DeepSeek model alias selected")

        mismatch_catalog = ProviderCatalog(
            path=os.path.join(state, "mismatch.json"),
            adapters={"groq": ProviderAdapter("groq", "http://actual", "")},
        )
        mismatch_catalog.entries = [entry("groq", "http://catalog", "mismatch-model")]
        mismatch_runtime = ProviderRuntime(catalog=mismatch_catalog, enabled=True)
        mismatch_decision = ProviderRouter(mismatch_catalog).select(
            RouteRequest(task_class="research")
        )
        try:
            mismatch_runtime.direct_invoke(
                mismatch_decision,
                [{"role": "user", "content": "probe"}],
                "research",
                1,
                "attempt-mismatch",
            )
        except ProviderFailure as exc:
            assert "endpoint mismatch" in str(exc)
            print("PASS CATALOG_ENDPOINT_OWNERSHIP")
        else:
            raise AssertionError("endpoint mismatch was not rejected")

    sample = {
        "contract": "provider.execution-proof.v1",
        "version": "v1",
        "routing_event_id": "route-1",
        "attempt_id": "attempt-1",
        "selected_provider": "groq",
        "selected_model": "model-1",
        "actual_provider": "groq",
        "actual_model": "model-1",
        "free_eligible": True,
        "execution_proof": "PASS",
        "usage": {"input_tokens": 1, "output_tokens": 1},
        "actual_cost": 0,
        "failover": [],
    }
    assert registry.validate(sample)["ok"]
    print("PASS PROVIDER_EXECUTION_PROOF_CONTRACT")


if __name__ == "__main__":
    main()
