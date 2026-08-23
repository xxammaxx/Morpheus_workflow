#!/usr/bin/env python3
"""Offline X-Harness-Token validator regression test."""

import importlib.util
import os
import sys
import tempfile


def main():
    with tempfile.TemporaryDirectory() as state:
        token_path = os.path.join(state, "token")
        with open(token_path, "w") as stream:
            stream.write("temporary-token-value")
        os.environ["AUTODEV_V2_STATE"] = state
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        spec = importlib.util.spec_from_file_location(
            "adapter_auth_test",
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "adapter",
                "harness_adapter_v2.py",
            ),
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        class Headers:
            def __init__(self, values):
                self.values = values

            def get_all(self, name):
                return self.values

        handler = object.__new__(module.Handler)
        handler.headers = Headers(["temporary-token-value"])
        assert handler._auth() is True
        handler.headers = Headers(["wrong"])
        assert handler._auth() is False
        assert module.call_resume_url("http://127.0.0.1:9/internal", {}) is None
        print("PASS CALLBACK_ALLOWLIST_REJECTS_INTERNAL_HOST")
        print("PASS X_HARNESS_TOKEN_VALIDATION")
        print("PASS X_HARNESS_TOKEN_REJECTS_WRONG_VALUE")


if __name__ == "__main__":
    main()
