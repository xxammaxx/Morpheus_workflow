import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
import control_tower


class ProjectionTests(unittest.TestCase):
    def test_unknown_source_does_not_become_green(self):
        self.assertEqual(control_tower.safe_status(False)["status"], "UNAVAILABLE")

    def test_partial_degradation_preserves_projection(self):
        original = (control_tower.table_rows, control_tower.adapter_runtime, control_tower.n8n_health, control_tower.adapter_health)
        try:
            control_tower.table_rows = lambda name: ([{"run_id": "r", "state": "DONE"}], True) if name == "runs" else ([], True)
            control_tower.adapter_runtime = lambda: ({}, False)
            control_tower.n8n_health = lambda: control_tower.safe_status(False)
            control_tower.adapter_health = lambda: control_tower.safe_status(True)
            value = control_tower.projection()
            self.assertEqual(value["system_health"]["n8n"]["status"], "UNAVAILABLE")
            self.assertEqual(value["system_health"]["adapter"]["status"], "HEALTHY")
            self.assertEqual(value["recent_runs"][0]["run_id"], "r")
        finally:
            control_tower.table_rows, control_tower.adapter_runtime, control_tower.n8n_health, control_tower.adapter_health = original

    def test_failure_run_ids_are_stable(self):
        self.assertEqual(control_tower.GOLDEN_RUN, "run-mt6unuge-agsdu4")
        self.assertEqual(control_tower.FAILURE_RUN, "run-mt6uony8-jjp9hf")


if __name__ == "__main__":
    unittest.main()
