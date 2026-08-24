import json
import os
import sys
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


if __name__ == "__main__":
    unittest.main()
