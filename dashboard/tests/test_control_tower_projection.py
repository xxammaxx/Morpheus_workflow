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

    def test_all_pipeline_states_are_active(self):
        for state in control_tower.ACTIVE_RUN_STATES:
            self.assertTrue(control_tower.is_active_run({"state": state}), state)
        self.assertFalse(control_tower.is_active_run({"state": "DONE"}))

    def test_counts_use_real_24_hour_terminal_window(self):
        reference = control_tower.dt.datetime(2026, 8, 25, tzinfo=control_tower.dt.timezone.utc)
        runs = [
            {"state": "DONE", "ended_at": "2026-08-24T23:00:00Z"},
            {"state": "DONE", "ended_at": "2026-08-23T23:00:00Z"},
            {"state": "FAILED", "updated_at": "2026-08-24T21:00:00Z"},
            {"state": "BLOCKED", "updated_at": "2026-08-24T22:00:00Z"},
            {"state": "FAILED", "updated_at": "not-a-date"},
            {"state": "BUILDING", "updated_at": "2026-08-24T23:30:00Z"},
        ]
        self.assertEqual(control_tower.build_run_counts(runs, reference), {"running": 1, "waiting": 0, "done_24h": 1, "failed_24h": 2})

    def test_recent_runs_are_updated_descending_and_missing_last(self):
        runs = [{"run_id": "old", "updated_at": "2026-01-01T00:00:00Z"}, {"run_id": "new", "updated_at": "2026-02-01T00:00:00Z"}, {"run_id": "unknown"}]
        self.assertEqual([run["run_id"] for run in control_tower.sort_recent_runs(runs)], ["new", "old", "unknown"])

    def test_pool_health_requires_two_free_providers(self):
        self.assertEqual(control_tower.provider_pool_status(2), "HEALTHY")
        self.assertEqual(control_tower.provider_pool_status(1), "DEGRADED")
        self.assertEqual(control_tower.provider_pool_status(0), "UNAVAILABLE")

    def test_stale_only_applies_to_active_runs(self):
        reference = control_tower.dt.datetime(2026, 8, 25, tzinfo=control_tower.dt.timezone.utc)
        self.assertFalse(control_tower.is_stale_run({"state": "BUILDING", "updated_at": "2026-08-24T23:55:00Z"}, 1800, reference))
        self.assertTrue(control_tower.is_stale_run({"state": "BUILDING", "updated_at": "2026-08-24T23:00:00Z"}, 1800, reference))
        self.assertFalse(control_tower.is_stale_run({"state": "DONE", "updated_at": "2026-08-24T23:00:00Z"}, 1800, reference))


if __name__ == "__main__":
    unittest.main()
