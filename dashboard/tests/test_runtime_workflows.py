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

    @staticmethod
    def _assert_generated_code_node_syntax(workflows):
        code_nodes = [
            (workflow_name, node["name"], node["parameters"]["jsCode"])
            for workflow_name, workflow in workflows.items()
            for node in workflow.get("nodes", [])
            if node.get("type") == "n8n-nodes-base.code"
            and isinstance(node.get("parameters", {}).get("jsCode"), str)
        ]
        with tempfile.TemporaryDirectory() as directory:
            for index, (workflow_name, node_name, source) in enumerate(code_nodes):
                path = Path(directory) / f"code-node-{index}.js"
                path.write_text(source, encoding="utf-8")
                result = subprocess.run(
                    ["node", "--check", str(path)], capture_output=True, text=True
                )
                if result.returncode:
                    raise AssertionError(
                        "generated Code node failed syntax check: "
                        f"workflow={workflow_name!r} node={node_name!r}\n"
                        f"{result.stderr}"
                    )
        return len(code_nodes)

    def test_all_generated_code_nodes_pass_node_check(self):
        count = self._assert_generated_code_node_syntax(self._generate())
        self.assertGreater(count, 0)

    def test_workflow_08_decision_code_is_valid_and_builds_continuation_request(self):
        workflow = self._generate()["08 AutoDev Project Reassessment"]
        decision = next(node for node in workflow["nodes"] if node["name"] == "Decide Canonical Continuation")
        source = decision["parameters"]["jsCode"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workflow-08-decision.js"
            path.write_text(source, encoding="utf-8")
            subprocess.run(["node", "--check", str(path)], check=True)

        fixture = {
            "request": {
                "project_id": "morpheus-canary-20260831",
                "source_run_id": "run-canary-source-20260831",
                "issue_number": "42",
                "continuation_reason": "resume",
                "requested_action": "continue",
                "requested_by": "test",
                "correlation_id": "ct-syntax-gate",
                "mode": "MANUAL",
                "correlation_valid": True,
            },
            "project": {"project_id": "morpheus-canary-20260831", "repository_url": "xxammaxx/morpheus"},
            "source": {"run_id": "run-canary-source-20260831", "project_id": "morpheus-canary-20260831", "state": "PLAN_BLOCKED", "issue_number": "42"},
            "issues": [{"issue_number": "42", "title": "Continue canonical work", "body": "Continue the project."}],
        }
        node_script = (
            "const vm=require('vm');\n"
            f"const fixture={json.dumps(fixture)};\n"
            "const values={'Normalize Continuation Request':{json:fixture.request},"
            "'Fetch Canonical Project':{json:{data:[fixture.project]}},"
            "'Fetch Project Runs':{json:{data:[fixture.source]}}};\n"
            "const $=name=>({first:()=>values[name]});\n"
            "const $json={data:fixture.issues};\n"
            "const result=vm.runInNewContext('(function(){\\n' + "
            + json.dumps(source)
            + " + '\\n})()', {$,$json,TextEncoder});\n"
            "console.log(JSON.stringify(result));"
        )
        result = subprocess.run(["node", "-e", node_script], check=True, capture_output=True, text=True)
        payload = json.loads(result.stdout)[0]["json"]
        self.assertTrue(payload["valid"])
        self.assertRegex(payload["continuation_run_id"], r"^run-cont-")
        task = payload["start_request"]["task"]
        self.assertEqual(task["project_id"], fixture["request"]["project_id"])
        self.assertEqual(task["source_run_id"], fixture["request"]["source_run_id"])
        self.assertEqual(task["created_via"], "CONTROL_TOWER_CONTINUATION")
        self.assertEqual(payload["start_request"]["backend"], "opencode-builder-8001")

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

    def test_start_response_projects_persisted_canonical_run_id_after_upsert(self):
        workflow = self._generate()["00 AutoDev API Start"]
        response = next(node for node in workflow["nodes"] if node["name"] == "Respond 202")
        response_body = response["parameters"]["responseBody"]
        self.assertIn("$('Prepare Run Row').first().json.data[0].run_id", response_body)
        self.assertNotIn("$json.run_id", response_body)
        insert_routes = workflow["connections"]["Insert Run Row"]["main"][0]
        self.assertEqual(
            {route["node"] for route in insert_routes},
            {"Respond 202", "Restore Intake Carrier"},
        )
        self.assertNotIn("Respond 202", json.dumps(workflow["connections"]["Pass Intake"]))

    def test_continuation_has_no_provider_or_model_selection(self):
        reassessment = json.dumps(self._generate()["08 AutoDev Project Reassessment"])
        self.assertIn("backend:'opencode-builder-8001'", reassessment)
        self.assertNotIn("provider:", reassessment)
        self.assertNotIn("model:", reassessment)


if __name__ == "__main__":
    unittest.main()
