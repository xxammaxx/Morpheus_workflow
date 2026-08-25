#!/usr/bin/env python3
"""Prove canonical _dispatch identity comes from dynamic free routing."""

import importlib.util
import json
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from providers.adapters import ProviderAdapter
from providers.catalog import ProviderCatalog
from providers.protocol import normalized_entry
from providers.runtime import ProviderRuntime


class Handler(BaseHTTPRequestHandler):
    requests = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length).decode())
        Handler.requests.append(body)
        encoded = json.dumps(
            {
                "id": "integration-1",
                "model": body["model"],
                "choices": [{"message": {"content": "integration proof"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                "cost": 0,
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args):
        pass


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    endpoint = "http://127.0.0.1:%d" % server.server_address[1]
    with tempfile.TemporaryDirectory() as state:
        os.environ["AUTODEV_V2_STATE"] = state
        os.environ["AUTODEV_PROVIDER_CATALOG"] = os.path.join(state, "catalog.json")
        spec = importlib.util.spec_from_file_location(
            "provider_adapter_integration",
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "adapter",
                "harness_adapter_v2.py",
            ),
        )
        adapter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(adapter)
        catalog = ProviderCatalog(
            path=os.path.join(state, "catalog.json"),
            adapters={"groq": ProviderAdapter("groq", endpoint, "")},
        )
        catalog.entries = [
            normalized_entry(
                "groq",
                "integration-model",
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
        ]
        adapter._provider_runtime = ProviderRuntime(catalog=catalog, enabled=True)
        adapter._provider_runtime.begin_run = lambda run_id: None
        catalog.refresh_live = lambda: {"refresh": "PASS"}
        adapter.run_job_thread = lambda *args, **kwargs: None
        issue = {
            "contract": "autodev.issue.v1",
            "version": "v1",
            "run_id": "integration-run",
            "repository_ref": "proof/project",
            "workspace": "proof",
            "task_description": "Return a research proof.",
            "trace_id": "trace-proof",
        }
        record, error = adapter._dispatch(
            "integration-run",
            "integration-job",
            "research.code",
            "integration-attempt",
            "autodev.issue.v1",
            issue,
            "opencode-builder-8001",
        )
        assert error is None
        result = adapter.JOBS[record["job_id"]]
        assert result["provider"] == "groq"
        assert result["model"] == "integration-model"
        assert result["model_alias"] == "morpheus-dynamic-free"
        assert result["route_decision"]["selected_provider"] == "groq"
        print("PASS ADAPTER_DYNAMIC_FREE_DISPATCH")
        print("PASS ADAPTER_NO_FIXED_PROVIDER_ROUTE")
    server.shutdown()


if __name__ == "__main__":
    main()
