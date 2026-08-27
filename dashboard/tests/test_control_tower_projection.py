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

    def test_pool_health_requires_one_free_provider(self):
        self.assertEqual(control_tower.provider_pool_status(2), "HEALTHY")
        self.assertEqual(control_tower.provider_pool_status(1), "HEALTHY")
        self.assertEqual(control_tower.provider_pool_status(0), "UNAVAILABLE")

    def test_n8n_health_counts_all_sixteen_canonical_workflows(self):
        original_get = control_tower.Upstream.get
        try:
            control_tower.Upstream.get = lambda self, path, params=None: (200, {
                "data": [{"name": f"{prefix} Canonical"} for prefix in (
                    "00", "01", "02", "05", "06", "07", "08", "10",
                    "20", "30", "40", "50", "60", "70", "80", "90"
                )]
            })
            self.assertEqual(control_tower.n8n_health()["workflow_count"], 16)
        finally:
            control_tower.Upstream.get = original_get

    def test_optional_mcp_does_not_fail_mandatory_system(self):
        original = (control_tower.table_rows, control_tower.adapter_runtime, control_tower.n8n_health, control_tower.adapter_health, control_tower.adapter_events)
        try:
            control_tower.table_rows = lambda name: ([], True)
            control_tower.adapter_runtime = lambda: ({
                "free_first_enabled": True,
                "automatic_paid_agent_escalation": False,
                "providers": [{"provider": "openrouter", "model": "x:free", "free_eligible": True}],
                "mcp": {"status": "NICHT_KONFIGURIERT", "servers": []},
                "opencode": {"ct8001_reachable": True, "binary_present": True, "version": "1.18.22"},
                "deepseek_policy": {key: False for key in ("catalog_eligible", "router_eligible", "explicit_request_allowed", "fallback_allowed", "opencode_default")},
            }, True)
            control_tower.n8n_health = lambda: control_tower.safe_status(True)
            control_tower.adapter_health = lambda: control_tower.safe_status(True)
            control_tower.adapter_events = lambda: ([], True)
            value = control_tower.projection()
            self.assertEqual(value["system_health_summary"]["status"], "OK")
            self.assertEqual(value["system_health"]["mcp"]["status"], "NICHT_KONFIGURIERT")
            self.assertEqual(value["optional_components_not_configured"], ["MCP", "LM Studio"])
        finally:
            (control_tower.table_rows, control_tower.adapter_runtime, control_tower.n8n_health, control_tower.adapter_health, control_tower.adapter_events) = original

    def test_empty_event_sources_are_idle_not_live(self):
        original = (control_tower.table_rows, control_tower.adapter_events)
        try:
            control_tower.table_rows = lambda name: ([], True)
            control_tower.adapter_events = lambda: ([], True)
            events, live = control_tower.debugging_events("run-without-events")
            self.assertEqual(events, [])
            self.assertFalse(live)
        finally:
            control_tower.table_rows, control_tower.adapter_events = original

    def test_adapter_event_container_is_projected(self):
        events = [{"run_id": "run-1", "event": "DISPATCH_ACCEPTED"}]
        self.assertEqual(control_tower.list_items({"data": {"events": events}}), events)

    def test_stale_only_applies_to_active_runs(self):
        reference = control_tower.dt.datetime(2026, 8, 25, tzinfo=control_tower.dt.timezone.utc)
        self.assertFalse(control_tower.is_stale_run({"state": "BUILDING", "updated_at": "2026-08-24T23:55:00Z"}, 1800, reference))
        self.assertTrue(control_tower.is_stale_run({"state": "BUILDING", "updated_at": "2026-08-24T23:00:00Z"}, 1800, reference))
        self.assertFalse(control_tower.is_stale_run({"state": "DONE", "updated_at": "2026-08-24T23:00:00Z"}, 1800, reference))


if __name__ == "__main__":
    unittest.main()
