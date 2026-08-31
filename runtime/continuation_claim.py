#!/usr/bin/env python3
"""Durable, claim-only guard for canonical project continuations.

This service owns no run state.  It is deliberately a tiny n8n-side control
plane extension: the only durable invariant is UNIQUE(identity_key).  SQLite
serializes the short BEGIN IMMEDIATE transaction, so competing processes use
the same database constraint rather than a process-local lock.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS continuation_claims (
    identity_key TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    source_run_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('CLAIMED', 'STARTED')),
    lease_until REAL NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
)
"""


class ClaimStore:
    """SQLite-backed claim store; each operation is safe across processes."""

    def __init__(self, path: str, lease_seconds: float = 30.0):
        self.path = path
        self.lease_seconds = lease_seconds
        self._schema_lock = threading.Lock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _ensure_schema(self) -> None:
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, mode=0o750, exist_ok=True)
        with self._schema_lock, self._connect() as connection:
            connection.executescript(SCHEMA)

    def claim(self, identity: dict[str, str]) -> dict[str, Any]:
        required = ("identity_key", "run_id", "project_id", "source_run_id", "correlation_id")
        if any(not str(identity.get(field, "")) for field in required):
            raise ValueError("complete continuation identity is required")
        now = time.time()
        lease_until = now + self.lease_seconds
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM continuation_claims WHERE identity_key = ?",
                (identity["identity_key"],),
            ).fetchone()
            if row is None:
                connection.execute(
                    """INSERT INTO continuation_claims
                    (identity_key, run_id, project_id, source_run_id, correlation_id,
                     state, lease_until, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 'CLAIMED', ?, ?, ?)""",
                    tuple(identity[field] for field in required) + (lease_until, now, now),
                )
                return {"claim_acquired": True, "run_id": identity["run_id"], "state": "CLAIMED"}
            if row["state"] == "CLAIMED" and row["lease_until"] <= now:
                connection.execute(
                    "UPDATE continuation_claims SET lease_until = ?, updated_at = ? WHERE identity_key = ?",
                    (lease_until, now, identity["identity_key"]),
                )
                return {"claim_acquired": True, "run_id": row["run_id"], "state": "CLAIMED", "recovered": True}
            return {"claim_acquired": False, "run_id": row["run_id"], "state": row["state"]}

    def mark_started(self, identity_key: str, run_id: str) -> bool:
        with self._connect() as connection:
            result = connection.execute(
                "UPDATE continuation_claims SET state = 'STARTED', updated_at = ? "
                "WHERE identity_key = ? AND run_id = ? AND state = 'CLAIMED'",
                (time.time(), identity_key, run_id),
            )
            return result.rowcount == 1


def _json_response(handler: BaseHTTPRequestHandler, status: int, body: dict[str, Any]) -> None:
    encoded = json.dumps(body, separators=(",", ":")).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


def serve(host: str, port: int, path: str, token: str) -> None:
    store = ClaimStore(path)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: object) -> None:
            return

        def do_POST(self) -> None:  # noqa: N802
            if self.headers.get("X-Morpheus-Claim-Token", "") != token:
                _json_response(self, 401, {"error": "UNAUTHORIZED"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length))
                if self.path == "/claim":
                    _json_response(self, 200, store.claim(payload))
                elif self.path == "/started":
                    _json_response(self, 200, {"started": store.mark_started(payload["identity_key"], payload["run_id"])})
                else:
                    _json_response(self, 404, {"error": "NOT_FOUND"})
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                _json_response(self, 400, {"error": str(exc)})

    ThreadingHTTPServer((host, port), Handler).serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8091)
    parser.add_argument("--db", default=os.environ.get("MORPHEUS_CLAIM_DB", "/var/lib/n8n/morpheus-continuation-claims.sqlite"))
    parser.add_argument("--token", default=os.environ.get("MORPHEUS_CLAIM_TOKEN", ""))
    args = parser.parse_args()
    if not args.token:
        parser.error("--token or MORPHEUS_CLAIM_TOKEN is required")
    serve(args.host, args.port, args.db, args.token)


if __name__ == "__main__":
    main()
