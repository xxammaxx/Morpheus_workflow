import json
import importlib.util
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
GENERATOR = ROOT / "workflow" / "v2" / "generate_workflows_v2.py"


class RuntimeWorkflowTests(unittest.TestCase):
    @staticmethod
    def _generator_module():
        spec = importlib.util.spec_from_file_location("morpheus_workflow_generator", GENERATOR)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _continuation_js(self, statement):
        generator = self._generator_module()
        completed = subprocess.run(
            ["node", "-e", generator.CONTINUATION_RUN_ID_JS + "\n" + generator.RUN_OWNERSHIP_GUARD_JS + "\n" + statement],
            check=True, capture_output=True, text=True,
        )
        return json.loads(completed.stdout)

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
        self.assertIn("TARGET_KEY_NOT_ALLOWED", json.dumps(gateway))
        self.assertIn("TARGET_VALUE_INVALID", json.dumps(gateway))
        self.assertIn("autodev/project/reassess", json.dumps(gateway))
        self.assertNotIn("COMMAND_NOT_IMPLEMENTED", json.dumps(gateway))
        self.assertIn("overall", json.dumps(gateway))
        self.assertIn("modules", json.dumps(gateway))
        self.assertIn("Prepare Canonical Run Action", {node["name"] for node in gateway["nodes"]})
        router_test = next(node for node in gateway["nodes"] if node["name"] == "Router Test Result")
        self.assertIn("first().json.payload", router_test["parameters"]["jsCode"])
        router_js = router_test["parameters"]["jsCode"]
        self.assertIn("'Free Pool':", router_js)
        self.assertIn("!checks.provider_contact", router_test["parameters"]["jsCode"])
        for diagnostic in (
            "Dynamischer Router", "Modellkatalog", "Free Pool", "Credential-Erkennung",
            "Capability Filter", "Tool Routing", "Vision Routing", "Structured Output",
            "Transport Failover", "Semantic Failover", "Run Blacklist",
            "Paid Fallback Sperre", "DeepSeek Sperre",
        ):
            self.assertIn("'%s':" % diagnostic, router_js)

    def test_abort_looks_up_then_updates_existing_run_and_keeps_response_carrier(self):
        gateway = self._generate()["05 AutoDev Control Gateway"]
        names = {node["name"] for node in gateway["nodes"]}
        self.assertTrue({
            "Prepare Canonical Run Action", "Fetch Canonical Run",
            "Check Canonical Run", "Canonical Run Found?",
            "Prepare Canonical Run Update", "Persist Canonical Run Action",
            "Canonical Run Action Result", "Respond Run Not Found",
        }.issubset(names))
        persist = next(node for node in gateway["nodes"] if node["name"] == "Persist Canonical Run Action")
        self.assertEqual(persist["parameters"]["method"], "PATCH")
        self.assertTrue(persist["alwaysOutputData"])
        fetch = next(node for node in gateway["nodes"] if node["name"] == "Fetch Canonical Run")
        self.assertTrue(fetch["alwaysOutputData"])
        self.assertNotIn("/upsert", persist["parameters"]["url"])
        self.assertIn("RUN_NOT_FOUND", json.dumps(gateway))
        self.assertIn("correlation_id", next(node for node in gateway["nodes"] if node["name"] == "Canonical Run Action Result")["parameters"]["jsCode"])

    def test_orchestrator_state_updates_cannot_resurrect_aborted_run(self):
        orchestrator = self._generate()["01 AutoDev Orchestrator"]
        updates = [node for node in orchestrator["nodes"] if node["name"].endswith(" State Update")]
        self.assertGreaterEqual(len(updates), 3)
        for node in updates:
            self.assertEqual(node["parameters"]["method"], "PATCH")
            self.assertTrue(node["alwaysOutputData"])
            prep = next(n for n in orchestrator["nodes"] if n["name"] == node["name"].replace(" Update", " Prep"))
            restore = next(n for n in orchestrator["nodes"] if n["name"] == node["name"].replace(" Update", " Restore"))
            self.assertIn("value: 'ABORTED'", prep["parameters"]["jsCode"])
            self.assertIn("return []", restore["parameters"]["jsCode"])

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
        self.assertIn("/usr/local/bin/opencode mcp list", gateway)
        self.assertIn("No MCP servers configured", gateway)

    def test_blueprint_dry_run_never_writes_github(self):
        workflows = self._generate()
        blueprint = json.dumps(workflows["07 AutoDev Blueprint Bootstrap"])
        self.assertIn("p.dry_run!==true", blueprint)
        self.assertIn("blueprint_write", blueprint)

    def test_resume_run_is_canonical_project_continuation(self):
        workflows = self._generate()
        gateway = workflows["05 AutoDev Control Gateway"]
        reassessment = workflows["08 AutoDev Project Reassessment"]
        gateway_text = json.dumps(gateway)
        reassessment_text = json.dumps(reassessment)
        self.assertIn("RESUME_RUN", gateway_text)
        self.assertIn("requested_by", gateway_text)
        self.assertIn("autodev/project/reassess", gateway_text)
        self.assertIn("Fetch Canonical Project", reassessment_text)
        self.assertIn("Fetch Project Runs", reassessment_text)
        self.assertIn("Fetch Project Issues", reassessment_text)
        for code in ("PROJECT_NOT_FOUND", "PROJECT_ACTIVE_RUN_CONFLICT", "CONTINUATION_NOT_ALLOWED", "ISSUE_NOT_FOUND", "DUPLICATE_REQUEST", "CORRELATION_ID_INVALID"):
            self.assertIn(code, reassessment_text)
        self.assertIn("CONTROL_TOWER_CONTINUATION", reassessment_text)
        self.assertIn("source_run_id", reassessment_text)
        self.assertIn("new_run_id", reassessment_text)
        self.assertIn("run-cont-", reassessment_text)

    def test_continuation_identity_is_project_source_and_correlation_namespaced(self):
        result = self._continuation_js("""
const correlation = 'ct-same-correlation';
const runA = canonicalContinuationRunId('project-a', 'run-source-a', correlation);
const runB = canonicalContinuationRunId('project-b', 'run-source-a', correlation);
const replay = canonicalContinuationRunId('project-a', 'run-source-a', correlation);
const differentSource = canonicalContinuationRunId('project-a', 'run-source-b', correlation);
const maximum = canonicalContinuationRunId('p'.repeat(96), 'run-' + 's'.repeat(60), 'c'.repeat(96));
console.log(JSON.stringify({runA,runB,replay,differentSource,maximum}));
""")
        self.assertNotEqual(result["runA"], result["runB"])
        self.assertEqual(result["runA"], result["replay"])
        self.assertNotEqual(result["runA"], result["differentSource"])
        expected = "run-cont-" + hashlib.sha256(
            json.dumps(["project-a", "run-source-a", "ct-same-correlation"], separators=(",", ":")).encode()
        ).hexdigest()[:48]
        self.assertEqual(result["runA"], expected)
        for run_id in result.values():
            self.assertRegex(run_id, r"^run-[A-Za-z0-9_-]{1,60}$")
            self.assertLessEqual(len(run_id), 64)

    def test_start_refuses_cross_project_run_id_reassignment_and_replays_exact_identity(self):
        result = self._continuation_js("""
const existing = {run_id:'run-cont-fixed',project_id:'project-a',source_run_id:'run-source-a',correlation_id:'ct-a',created_via:'CONTROL_TOWER_CONTINUATION'};
const same = requestedRunOwnership(existing, existing);
const crossProject = requestedRunOwnership({...existing, project_id:'project-b'}, existing);
const differentSource = requestedRunOwnership({...existing, source_run_id:'run-source-b'}, existing);
console.log(JSON.stringify({same,crossProject,differentSource}));
""")
        self.assertTrue(result["same"]["ownership_ok"])
        self.assertTrue(result["same"]["continuation_replay"])
        self.assertFalse(result["crossProject"]["ownership_ok"])
        self.assertEqual(result["crossProject"]["ownership_code"], "RUN_ID_OWNERSHIP_CONFLICT")
        self.assertFalse(result["differentSource"]["ownership_ok"])

    def test_start_contract_carries_continuation_provenance_into_new_run(self):
        workflow = self._generate()["00 AutoDev API Start"]
        start = json.dumps(workflow)
        for field in ("source_run_id", "continuation_reason", "requested_action", "created_via", "requested_by", "correlation_id"):
            self.assertIn(field, start)
        self.assertIn("requestedRunId", start)
        self.assertIn("Fetch Requested Run", {node["name"] for node in workflow["nodes"]})
        self.assertIn("Guard Requested Run Ownership", {node["name"] for node in workflow["nodes"]})
        self.assertIn("RUN_ID_OWNERSHIP_CONFLICT", start)
        replay_routes = workflow["connections"]["Continuation Intake Replay?"]["main"]
        self.assertEqual(replay_routes[0][0]["node"], "Respond Existing Continuation")
        self.assertEqual(replay_routes[1][0]["node"], "Insert Run Row")
        insert = next(node for node in workflow["nodes"] if node["name"] == "Insert Run Row")
        self.assertTrue(insert["parameters"]["url"].endswith("/upsert"))
        self.assertIn("run_id", insert["parameters"]["jsonBody"])
        self.assertIn("Restore Intake Carrier", {node["name"] for node in workflow["nodes"]})

    def test_continuation_has_no_provider_or_model_selection(self):
        reassessment = json.dumps(self._generate()["08 AutoDev Project Reassessment"])
        self.assertIn("backend:'opencode-builder-8001'", reassessment)
        self.assertNotIn("provider:", reassessment)
        self.assertNotIn("model:", reassessment)


if __name__ == "__main__":
    unittest.main()
