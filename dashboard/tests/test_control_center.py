import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from control_center import (
    ADMIN_COMMANDS, OPERATOR_COMMANDS, blueprint_projection, classify_issue,
    continuation_policy, project_projection, reassessment, redact, validate_command, validate_target,
)


class ControlCenterPolicyTests(unittest.TestCase):
    def test_roles_and_allowlist(self):
        validate_command("PAUSE_RUN", {"run_id": "r-1"}, "OPERATOR")
        with self.assertRaises(PermissionError):
            validate_command("REFRESH_CATALOG", {}, "OPERATOR")
        validate_command("REFRESH_CATALOG", {}, "ADMIN")
        with self.assertRaises(ValueError):
            validate_command("NOPE", {}, "ADMIN")

    def test_start_payload_and_ssrf_guard(self):
        validate_command("START_ISSUE", {"repository_url": "https://github.com/o/r", "issue": "#42"}, "OPERATOR")
        with self.assertRaises(ValueError):
            validate_command("START_ISSUE", {"repository_url": "http://127.0.0.1/x", "issue": "#42"}, "OPERATOR")
        with self.assertRaises(ValueError):
            validate_command("START_ISSUE", {"repository_url": "https://github.com/o/r", "issue": "#42", "api_key": "x"}, "OPERATOR")
        with self.assertRaises(ValueError):
            validate_command("START_PROJECT", {"blueprint_md": "# safe", "model": "deepseek/deepseek-chat"}, "OPERATOR")

    def test_target_allowlist_rejects_arbitrary_routing_metadata(self):
        self.assertEqual(validate_target({"run_id": "run-safe"}), {"run_id": "run-safe"})
        with self.assertRaises(ValueError):
            validate_target({"url": "http://127.0.0.1"})
        with self.assertRaises(ValueError):
            validate_target({"run_id": {"nested": "target"}})

    def test_blueprint_is_structured_and_persistent_intent(self):
        value = blueprint_projection("# Ziel\nEin Produkt\n## Acceptance Criteria\n- Tests grün")
        self.assertTrue(value["valid"])
        self.assertEqual(value["format"], ".md")

    def test_reassessment_continues_or_blocks_or_completes(self):
        issues = [{"number": 10, "status": "DONE"}, {"number": 11, "status": "READY"}]
        value = reassessment(issues, {"valid": True}, "AUTO")
        self.assertEqual(value["status"], "READY")
        self.assertEqual(value["next_issue"]["number"], 11)
        blocked = reassessment([{"number": 10, "blocked": True}], {"valid": True})
        self.assertEqual(blocked["status"], "BLOCKED")
        done = reassessment([{"number": 10, "status": "DONE"}], {"valid": True})
        self.assertEqual(done["status"], "PROJECT_DONE")
        not_covered = reassessment([], {"valid": False})
        self.assertNotEqual(not_covered["status"], "PROJECT_DONE")

    def test_issue_classification_and_project_grouping(self):
        self.assertEqual(classify_issue({"duplicate_of": 4}), "DUPLICATE")
        projects = project_projection([{"project_id": "p", "name": "P", "repository_url": "https://github.com/o/r"}], [{"project_id": "p", "number": 1, "status": "DONE"}], [{"project_id": "p", "run_id": "run-1", "state": "DONE"}])
        self.assertEqual(projects[0]["progress"], {"done": 1, "total": 1})

    def test_server_redaction_drops_reasoning_and_secrets(self):
        value = redact({"api_key": "secret", "reasoning_content": "private", "payload": {"ok": True}})
        self.assertEqual(value["api_key"], "[REDACTED]")
        self.assertNotIn("reasoning_content", value)
        self.assertTrue(value["payload"]["ok"])

    def test_resume_run_reuses_operator_contract_with_bounded_intent(self):
        command, payload = validate_command("RESUME_RUN", {
            "project_id": "project-canary",
            "source_run_id": "run-previous-1",
            "issue_number": "42",
            "continuation_reason": "continue unfinished work",
            "requested_action": "implement the next approved milestone",
        }, "OPERATOR")
        self.assertEqual(command, "RESUME_RUN")
        self.assertEqual(payload["source_run_id"], "run-previous-1")
        for bad in (
            {"project_id": "project-canary", "source_run_id": "run-previous-1", "continuation_reason": "x", "requested_action": "y", "url": "https://evil"},
            {"project_id": "project-canary", "source_run_id": "run-previous-1", "continuation_reason": "x", "requested_action": "y", "provider": "openrouter"},
            {"project_id": "project-canary", "source_run_id": "run-previous-1", "continuation_reason": "x", "requested_action": "y", "issue_number": {"nested": True}},
        ):
            with self.assertRaises(ValueError):
                validate_command("RESUME_RUN", bad, "OPERATOR")

    def test_continuation_policy_preserves_project_and_run_history(self):
        project = {"project_id": "project-canary", "name": "Canary"}
        runs = [
            {"project_id": "project-canary", "run_id": "run-1", "state": "DONE", "issue_number": "42"},
        ]
        result = continuation_policy(project, runs, [{"project_id": "project-canary", "issue_number": "42", "status": "READY"}], {
            "project_id": "project-canary", "source_run_id": "run-1", "issue_number": "42", "correlation_id": "ct-test-1",
        })
        self.assertTrue(result["allowed"])
        self.assertEqual(result["source_run"]["run_id"], "run-1")
        self.assertEqual(runs[0]["run_id"], "run-1")

    def test_continuation_policy_covers_terminal_abort_block_and_active_conflict(self):
        for terminal in ("ABORTED", "BLOCKED", "COMPLETED"):
            result = continuation_policy({"project_id": "p"}, [{"project_id": "p", "run_id": "run-1", "state": terminal}], [], {
                "project_id": "p", "source_run_id": "run-1", "continuation_reason": "resume", "requested_action": "next", "correlation_id": terminal,
            })
            self.assertTrue(result["allowed"], terminal)
        conflict = continuation_policy({"project_id": "p"}, [
            {"project_id": "p", "run_id": "run-1", "state": "DONE"},
            {"project_id": "p", "run_id": "run-2", "state": "BUILDING"},
        ], [], {"project_id": "p", "source_run_id": "run-1", "correlation_id": "ct-conflict"})
        self.assertEqual(conflict["code"], "PROJECT_ACTIVE_RUN_CONFLICT")

    def test_continuation_policy_fails_closed_for_project_issue_and_replay(self):
        request = {"project_id": "p", "source_run_id": "run-1", "issue_number": "99", "correlation_id": "ct-replay"}
        self.assertEqual(continuation_policy(None, [], [], request)["code"], "PROJECT_NOT_FOUND")
        runs = [{"project_id": "p", "run_id": "run-1", "state": "DONE"}]
        self.assertEqual(continuation_policy({"project_id": "p"}, runs, [{"project_id": "p", "issue_number": "42"}], request)["code"], "ISSUE_NOT_FOUND")
        replay = runs + [{"project_id": "p", "run_id": "run-cont-1", "state": "ACCEPTED", "correlation_id": "ct-replay", "created_via": "CONTROL_TOWER_CONTINUATION"}]
        self.assertEqual(continuation_policy({"project_id": "p"}, replay, [], {"project_id": "p", "source_run_id": "run-1", "correlation_id": "ct-replay"})["code"], "DUPLICATE_REQUEST")
        source_two = {"project_id": "p", "run_id": "run-2", "state": "DONE"}
        self.assertEqual(continuation_policy({"project_id": "p"}, replay + [source_two], [], {"project_id": "p", "source_run_id": "run-2", "correlation_id": "ct-replay"})["code"], "DUPLICATE_REQUEST")

    def test_project_projection_exposes_history_and_continuation_guard(self):
        value = project_projection(
            [{"project_id": "p", "name": "P"}],
            [{"project_id": "p", "issue_number": "42", "status": "READY"}],
            [
                {"project_id": "p", "run_id": "run-1", "state": "DONE", "updated_at": "2026-08-29T00:00:00Z"},
                {"project_id": "p", "run_id": "run-2", "state": "ABORTED", "source_run_id": "run-1", "created_via": "CONTROL_TOWER_CONTINUATION", "updated_at": "2026-08-30T00:00:00Z"},
            ],
        )[0]
        self.assertTrue(value["continuation_allowed"])
        self.assertEqual(value["latest_run_id"], "run-2")
        self.assertEqual([row["run_id"] for row in value["run_history"]], ["run-2", "run-1"])
        self.assertEqual(value["run_history"][0]["source_run_id"], "run-1")


if __name__ == "__main__":
    unittest.main()
