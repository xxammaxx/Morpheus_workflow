import json
import os
import sys
import threading
import urllib.error
import urllib.request
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
os.environ.setdefault("CONTROL_TOWER_VIEW_TOKEN", "test-viewer-token")
import control_tower


class ContractAndProjectionTests(unittest.TestCase):
    def test_sanitizer_excludes_content(self):
        value = control_tower.sanitize_run({"run_id": "r", "prompt": "secret", "response": "secret", "state": "DONE"})
        self.assertEqual(value, {"run_id": "r", "state": "DONE"})

    def test_timeline_uses_observed_timestamps_only(self):
        events = control_tower.timeline([{"run_id": "r", "started_at": "2026-01-01T00:00:00Z", "status": "running"}])
        self.assertEqual([x["event"] for x in events], ["ATTEMPT_STARTED"])

    def test_contract_files_are_json(self):
        for path in (Path(__file__).parents[1] / "contracts").glob("*.json"):
            self.assertIsInstance(json.loads(path.read_text()), dict)

    def test_runtime_telemetry_is_get_only(self):
        server = control_tower.ThreadingHTTPServer(("127.0.0.1", 0), control_tower.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = "http://127.0.0.1:%s/api/v1/telemetry/runtime" % server.server_port
            request = urllib.request.Request(url, headers={"X-Control-Tower-Token": "test-viewer-token"})
            with urllib.request.urlopen(request, timeout=3) as response:
                value = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertEqual(value["contract"], "autodev.runtime-telemetry.v1")
            post = urllib.request.Request(url, data=b"{}", method="POST", headers={"X-Control-Tower-Token": "test-viewer-token", "X-Control-Tower-Request": "1"})
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(post, timeout=3)
            self.assertEqual(raised.exception.code, 405)
        finally:
            server.shutdown()
            server.server_close()

    def test_continuation_provenance_is_projected_without_content(self):
        value = control_tower.sanitize_run({
            "run_id": "run-2", "project_id": "p", "source_run_id": "run-1",
            "created_via": "CONTROL_TOWER_CONTINUATION", "continuation_reason": "resume",
            "requested_action": "next milestone", "prompt": "private",
        })
        self.assertEqual(value["source_run_id"], "run-1")
        self.assertEqual(value["created_via"], "CONTROL_TOWER_CONTINUATION")
        self.assertNotIn("prompt", value)

    def test_bounded_canonical_errors_map_to_safe_http_status(self):
        self.assertEqual(control_tower.command_result_status(200, {"status": "error", "code": "PROJECT_ACTIVE_RUN_CONFLICT"}), 409)
        self.assertEqual(control_tower.command_result_status(200, {"status": "error", "code": "RUN_ID_OWNERSHIP_CONFLICT"}), 409)
        self.assertEqual(control_tower.command_result_status(200, {"status": "error", "code": "PROJECT_NOT_FOUND"}), 404)

    def test_continuation_mutation_requires_auth_role_and_csrf(self):
        server = control_tower.ThreadingHTTPServer(("127.0.0.1", 0), control_tower.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = "http://127.0.0.1:%s/api/v1/commands" % server.server_port
        body = json.dumps({"command": "RESUME_RUN", "payload": {"project_id": "p", "source_run_id": "run-1", "continuation_reason": "resume", "requested_action": "next"}, "target": {"project_id": "p"}}).encode()
        try:
            with self.assertRaises(urllib.error.HTTPError) as missing:
                urllib.request.urlopen(urllib.request.Request(url, data=body, method="POST"), timeout=3)
            self.assertEqual(missing.exception.code, 401)
            with self.assertRaises(urllib.error.HTTPError) as csrf:
                urllib.request.urlopen(urllib.request.Request(url, data=body, method="POST", headers={"X-Control-Tower-Token": "test-viewer-token"}), timeout=3)
            self.assertEqual(csrf.exception.code, 403)
            headers = {"X-Control-Tower-Token": "test-viewer-token", "X-Control-Tower-Request": "1", "Content-Type": "application/json"}
            with self.assertRaises(urllib.error.HTTPError) as viewer:
                urllib.request.urlopen(urllib.request.Request(url, data=body, method="POST", headers=headers), timeout=3)
            self.assertEqual(viewer.exception.code, 403)
            invalid = json.dumps({"command": "RESUME_RUN", "payload": {"project_id": "p", "source_run_id": "run-1", "continuation_reason": "resume", "requested_action": "next"}, "target": {"url": "https://evil"}}).encode()
            with self.assertRaises(urllib.error.HTTPError) as target:
                urllib.request.urlopen(urllib.request.Request(url, data=invalid, method="POST", headers={**headers}), timeout=3)
            self.assertEqual(target.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()

    def test_invalid_client_correlation_is_replaced_with_a_safe_server_correlation(self):
        captured = []
        original_operator = control_tower.OPERATOR_TOKEN
        control_tower.OPERATOR_TOKEN = "test-operator-token"
        server = control_tower.ThreadingHTTPServer(("127.0.0.1", 0), control_tower.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        body = json.dumps({
            "command": "RESUME_RUN",
            "payload": {"project_id": "p", "source_run_id": "run-1", "continuation_reason": "resume", "requested_action": "next"},
            "target": {"project_id": "p", "run_id": "run-1"},
            "correlation_id": "invalid correlation with spaces",
        }).encode()
        try:
            def fake_command_post(path, envelope):
                captured.append((path, envelope))
                return 200, {"status": "ACCEPTED"}
            headers = {"X-Control-Tower-Token": "test-operator-token", "X-Control-Tower-Request": "1", "Content-Type": "application/json"}
            with patch.object(control_tower, "command_post", side_effect=fake_command_post):
                with urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:%s/api/v1/commands" % server.server_port, data=body, method="POST", headers=headers), timeout=3) as response:
                    self.assertEqual(response.status, 202)
            self.assertEqual(captured[0][0], control_tower.COMMAND_PATHS["RESUME_RUN"])
            self.assertTrue(control_tower.re_correlation_id(captured[0][1]["correlation_id"]))
            self.assertNotEqual(captured[0][1]["correlation_id"], "invalid correlation with spaces")
        finally:
            control_tower.OPERATOR_TOKEN = original_operator
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
