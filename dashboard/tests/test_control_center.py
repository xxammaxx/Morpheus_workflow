import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from control_center import (
    ADMIN_COMMANDS, OPERATOR_COMMANDS, blueprint_projection, classify_issue,
    project_projection, reassessment, redact, validate_command,
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


if __name__ == "__main__":
    unittest.main()
