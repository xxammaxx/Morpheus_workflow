#!/usr/bin/env python3
"""HAMH Resolver HTTP Service — additive runtime-layer deployment (ADR H3).

Deployed to /opt/dev-fabric/hamh/ on the production host (Proxmox pve,
192.168.1.136). Serves the deterministic HAMH harness resolution as an HTTP
endpoint so the existing execution path (n8n -> adapter -> model adapter)
can resolve the effective harness WITHOUT any modification of the existing
production adapter/workflows (additive shadow deployment).

Endpoints:
    GET  /healthz            -> {"status": "ok", "version": ...}
    POST /v1/resolve         -> hamh.resolution.v1 payload
    GET  /v1/registry        -> harness_id list (no secrets)

Stdlib only. No external dependencies. Read-only against the registry file
(the registry is only mutated by the operator via init/rollback scripts).
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "runtime"))
sys.path.insert(0, os.path.join(HERE, "runtime", "hamh"))
sys.path.insert(0, os.path.join(HERE, "runtime", "contracts"))

from hamh.resolver import resolve, resolve_replay  # noqa: E402
from hamh.registry import HarnessRegistry  # noqa: E402

VERSION = "1.0.0"
DEFAULT_PORT = 8090
REGISTRY_PATH = os.environ.get(
    "HAMH_REGISTRY_PATH", os.path.join(HERE, "state", "registry.json")
)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence request logging (privacy)
        pass

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/healthz":
            self._json(
                200, {"status": "ok", "service": "hamh-resolver", "version": VERSION}
            )
            return
        if self.path == "/v1/registry":
            try:
                reg = HarnessRegistry(REGISTRY_PATH)
                ids = sorted(
                    "%s|%s" % (hid, e.get("status")) for hid, e in reg.entries().items()
                )
            except Exception as exc:  # never leak internals
                self._json(500, {"status": "error", "error": str(exc)})
                return
            self._json(200, {"status": "ok", "entries": ids})
            return
        self._json(404, {"status": "error", "error": "not found"})

    def do_POST(self):
        if self.path != "/v1/resolve":
            self._json(404, {"status": "error", "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode() or "{}")
        except (ValueError, UnicodeDecodeError):
            self._json(400, {"status": "error", "error": "invalid JSON body"})
            return
        try:
            reg = HarnessRegistry(REGISTRY_PATH)
            harness_id = payload.get("harness_id")
            if harness_id:
                # explicit replay resolution (audit/candidate path): returns
                # the entry regardless of status (CANDIDATE/SHADOW/CANARY)
                entry = resolve_replay(reg, harness_id)
                if entry is None:
                    self._json(
                        404, {"status": "error", "error": "harness_id not found"}
                    )
                    return
                resolution = _entry_to_resolution(entry)
            else:
                resolution = resolve(
                    provider=payload.get("provider"),
                    model=payload.get("model"),
                    task_class=payload.get("task_class", "baseline"),
                    runtime_mode=payload.get("runtime_mode", "auto"),
                    model_revision=payload.get("model_revision"),
                    requested_capabilities=payload.get("requested_capabilities"),
                    runtime_constraints=payload.get("runtime_constraints"),
                    registry=reg,
                    controller_allowlist=payload.get("controller_allowlist"),
                )
        except Exception as exc:  # resolution must never crash the caller
            self._json(500, {"status": "error", "error": "resolution failed: %s" % exc})
            return
        self._json(200, resolution)


def _entry_to_resolution(entry):
    """Build a hamh.resolution.v1 payload from a registry entry (replay)."""
    from hamh.resolver import _entry_resolution  # noqa: PLC0415

    return _entry_resolution(
        entry,
        requested_capabilities=[],
        runtime_constraints={},
        allowlist=_controller_allowlist_for(entry),
    )


def _controller_allowlist_for(entry):
    from hamh import profiles as _profiles  # noqa: PLC0415

    return _profiles.CONTROLLER_ALLOWED_TOOLS.get(
        entry.get("task_class"), _profiles.READONLY_TOOLS
    )


def main():
    port = int(os.environ.get("HAMH_PORT", DEFAULT_PORT))
    server = HTTPServer(("0.0.0.0", port), _Handler)
    print(
        "hamh-resolver listening on :%d (registry=%s)" % (port, REGISTRY_PATH),
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
