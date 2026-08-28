import json
import os
import sys
import threading
import urllib.error
import urllib.request
import unittest
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


if __name__ == "__main__":
    unittest.main()
