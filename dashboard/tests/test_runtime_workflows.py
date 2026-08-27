import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
GENERATOR = ROOT / "workflow" / "v2" / "generate_workflows_v2.py"


class RuntimeWorkflowTests(unittest.TestCase):
    def _generate(self):
        config = {
            "n8n_base": "http://n8n",
            "adapter_base": "http://adapter",
            "webhook_base": "http://n8n",
            "tables": {"runs": "runs", "attempts": "attempts", "projects": "projects", "issues": "issues", "audit": "audit"},
            "creds": {
                "n8n_api": {"id": "n8n", "name": "n8n"},
                "harness_token": {"id": "harness", "name": "harness"},
                "api_auth": {"id": "api", "name": "api"},
                "github_api": {"id": "github", "name": "github"},
                "runner_ssh": {"id": "ssh", "name": "ssh"},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            output = Path(directory) / "workflows"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            subprocess.run([sys.executable, str(GENERATOR), str(config_path), str(output)], check=True)
            return {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in output.glob("*.json")}

    def test_runtime_workflows_are_canonical_and_authenticated(self):
        workflows = self._generate()
        self.assertIn("05 AutoDev Control Gateway", workflows)
        self.assertIn("06 AutoDev Project Analysis", workflows)
        self.assertIn("07 AutoDev Blueprint Bootstrap", workflows)
        self.assertIn("08 AutoDev Project Reassessment", workflows)
        gateway = workflows["05 AutoDev Control Gateway"]
        webhook = next(node for node in gateway["nodes"] if node["name"] == "Control Webhook")
        self.assertEqual(webhook["parameters"]["path"], "autodev/control")
        self.assertEqual(webhook["parameters"]["authentication"], "headerAuth")
        self.assertIn("COMMAND_NOT_ALLOWED", next(node for node in gateway["nodes"] if node["name"] == "Validate Control Command")["parameters"]["jsCode"])

    def test_done_path_calls_n8n_reassessment(self):
        workflows = self._generate()
        orchestrator = workflows["01 AutoDev Orchestrator"]
        self.assertIn("Project Reassessment", {node["name"] for node in orchestrator["nodes"]})
        self.assertIn("autodev/project/reassess", json.dumps(orchestrator))

    def test_runtime_workflows_do_not_allow_arbitrary_shell(self):
        workflows = self._generate()
        gateway = json.dumps(workflows["05 AutoDev Control Gateway"])
        self.assertNotIn("execute shell", gateway.lower())
        self.assertNotIn("exec arbitrary", gateway.lower())
        self.assertIn("/root/.opencode/bin/opencode mcp list --json", gateway)


if __name__ == "__main__":
    unittest.main()
