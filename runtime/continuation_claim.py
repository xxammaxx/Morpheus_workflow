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
import hmac
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
    generation INTEGER NOT NULL DEFAULT 1,
    delivery_state TEXT NOT NULL DEFAULT 'PENDING' CHECK (delivery_state IN ('PENDING', 'ACCEPTED')),
    orchestrator_accepted_at REAL,
    orchestrator_completed_at REAL,
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
        # WAL permits concurrent readers while FULL synchronous commits the
        # short BEGIN IMMEDIATE transactions before the HTTP response exists.
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _ensure_schema(self) -> None:
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, mode=0o750, exist_ok=True)
        with self._schema_lock, self._connect() as connection:
            connection.executescript(SCHEMA)
            existing = {row[1] for row in connection.execute("PRAGMA table_info(continuation_claims)")}
            migrations = {
                "generation": "ALTER TABLE continuation_claims ADD COLUMN generation INTEGER NOT NULL DEFAULT 1",
                "delivery_state": "ALTER TABLE continuation_claims ADD COLUMN delivery_state TEXT NOT NULL DEFAULT 'PENDING'",
                "orchestrator_accepted_at": "ALTER TABLE continuation_claims ADD COLUMN orchestrator_accepted_at REAL",
                "orchestrator_completed_at": "ALTER TABLE continuation_claims ADD COLUMN orchestrator_completed_at REAL",
            }
            for column, statement in migrations.items():
                if column not in existing:
                    connection.execute(statement)

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
                     state, lease_until, generation, delivery_state, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 'CLAIMED', ?, 1, 'PENDING', ?, ?)""",
                    tuple(identity[field] for field in required) + (lease_until, now, now),
                )
                return {"claim_acquired": True, "run_id": identity["run_id"], "state": "CLAIMED", "generation": 1}
            if row["state"] == "CLAIMED" and row["lease_until"] <= now:
                connection.execute(
                    "UPDATE continuation_claims SET lease_until = ?, generation = generation + 1, updated_at = ? WHERE identity_key = ? AND state = 'CLAIMED' AND lease_until <= ?",
                    (lease_until, now, identity["identity_key"], now),
                )
                refreshed = connection.execute("SELECT generation FROM continuation_claims WHERE identity_key = ?", (identity["identity_key"],)).fetchone()
                return {"claim_acquired": True, "run_id": row["run_id"], "state": "CLAIMED", "generation": refreshed["generation"], "recovered": True}
            return {"claim_acquired": False, "run_id": row["run_id"], "state": row["state"], "generation": row["generation"], "delivery_state": row["delivery_state"]}

    def accept_orchestration(self, identity_key: str, run_id: str, generation: int) -> dict[str, Any]:
        """Atomically accept the logical downstream effect, once per run."""
        now = time.time()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM continuation_claims WHERE identity_key = ?", (identity_key,)).fetchone()
            if row is None or row["run_id"] != run_id:
                raise ValueError("claim identity does not own run_id")
            if row["delivery_state"] == "ACCEPTED":
                return {"accepted": False, "run_id": row["run_id"], "generation": row["generation"], "delivery_state": "ACCEPTED"}
            if row["generation"] != generation or row["state"] != "CLAIMED":
                return {"accepted": False, "stale": True, "run_id": row["run_id"], "generation": row["generation"], "delivery_state": row["delivery_state"]}
            connection.execute(
                "UPDATE continuation_claims SET state = 'STARTED', lease_until = 0, delivery_state = 'ACCEPTED', orchestrator_accepted_at = ?, updated_at = ? WHERE identity_key = ? AND generation = ? AND delivery_state = 'PENDING'",
                (now, now, identity_key, generation),
            )
            return {"accepted": True, "run_id": row["run_id"], "generation": generation, "delivery_state": "ACCEPTED"}

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
            if not hmac.compare_digest(self.headers.get("X-Morpheus-Claim-Token", ""), token):
                _json_response(self, 401, {"error": "UNAUTHORIZED"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length))
                if self.path == "/claim":
                    _json_response(self, 200, store.claim(payload))
                elif self.path == "/orchestration/accept":
                    _json_response(self, 200, store.accept_orchestration(payload["identity_key"], payload["run_id"], int(payload["generation"])))
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
