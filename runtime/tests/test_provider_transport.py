#!/usr/bin/env python3
"""Offline transport tests for header precedence and secret exclusion."""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from providers.adapters import ProviderAdapter


class Handler(BaseHTTPRequestHandler):
    seen = {}

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        Handler.seen = {key.lower(): value for key, value in self.headers.items()}
        self.rfile.read(length)
        body = json.dumps(
            {
                "id": "request-1",
                "model": "model-1",
                "choices": [{"message": {"content": "ok"}}],
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    endpoint = "http://127.0.0.1:%d" % server.server_address[1]
    os.environ["PROVIDER_TEST_CREDENTIAL"] = "test-credential-not-output"
    expected_auth = "Bearer " + os.environ["PROVIDER_TEST_CREDENTIAL"]
    adapter = ProviderAdapter("groq", endpoint, "PROVIDER_TEST_CREDENTIAL")
    request = type(
        "Request",
        (),
        {
            "model": "model-1",
            "messages": [{"role": "user", "content": "hello"}],
            "requested_capabilities": [],
            "outbound_request_id": "transport-test-1",
        },
    )()
    response = adapter.invoke(request, timeout=5)
    assert Handler.seen["user-agent"] == "Morpheus-AutoDev/1.0"
    assert Handler.seen["authorization"] == expected_auth
    assert "cookie" not in response.response_headers
    assert "authorization" not in response.response_headers
    adapter._request(
        "POST",
        "/chat/completions",
        {"model": "model-1", "messages": []},
        headers={"User-Agent": "Explicit-Provider/2", "Authorization": "caller-value"},
    )
    assert Handler.seen["user-agent"] == "Explicit-Provider/2"
    assert Handler.seen["authorization"] == expected_auth
    print("PASS GROQ_DEFAULT_AND_EXPLICIT_USER_AGENT")
    print("PASS PROVIDER_AUTH_OWNERSHIP_AND_HEADER_REDACTION")
    server.shutdown()


if __name__ == "__main__":
    main()
