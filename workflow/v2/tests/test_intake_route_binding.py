"""Provider-free regression tests for the canonical intake route contract."""

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
GENERATOR = ROOT / "workflow" / "v2" / "generate_workflows_v2.py"
CONFIG = ROOT / "workflow" / "v2" / "config.json"


def generated_intake(tmp_path):
    subprocess.run([sys.executable, str(GENERATOR), str(CONFIG), str(tmp_path)], check=True)
    workflow = json.loads((tmp_path / "00 AutoDev API Start.json").read_text())
    return next(node["parameters"]["jsCode"] for node in workflow["nodes"] if node["name"] == "Validate Intake"), workflow


def run_intake(source, body):
    runner = """
const fs = require('fs');
const value = JSON.parse(fs.readFileSync(0, 'utf8'));
const result = new Function('$json', value.source)(value.body);
process.stdout.write(JSON.stringify(result));
"""
    completed = subprocess.run(
        ["node", "-e", runner],
        input=json.dumps({"source": source, "body": body}),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)[0]["json"]


def request(metadata=None, **values):
    task = {
        "run_id": "run-route-contract",
        "task_ref": "route-contract",
        "repository_ref": "fixture-only",
        "workspace": "route-contract",
        "task_description": "Exercise canonical route binding without a provider call.",
        "max_attempts": 1,
        **values,
    }
    if metadata is not None:
        task["x-metadata"] = metadata
    return {"task": task}


def test_exact_route_and_binding_survive_generated_intake(tmp_path):
    source, workflow = generated_intake(tmp_path)
    metadata = {
        "adaptive_metadata": {
            "contract": "autodev.adaptive-metadata.v1",
            "version": "v1",
            "experiment_id": "route-contract-001",
            "benchmark_task_id": "d-001",
            "benchmark_split": "development",
            "candidate_id": None,
            "factor": "BASELINE",
            "context_policy": "disabled",
            "repo_explorer_policy": "disabled",
            "experience_policy": "disabled",
            "config_hash": "a" * 64,
            "task_set_hash": "b" * 64,
            "harness_version": "v1",
        },
        "route_policy": "FAIL_CLOSED",
        "expected_provider": "opencode",
        "expected_model": "big-pickle",
    }
    result = run_intake(source, request(metadata, provider="opencode", model="big-pickle"))
    assert result["intake_valid"] is True
    assert result["provider"] == "opencode"
    assert result["model"] == "big-pickle"
    issue_metadata = result["issue"]["x-metadata"]
    assert issue_metadata["route_policy"] == "FAIL_CLOSED"
    assert issue_metadata["expected_provider"] == "opencode"
    assert issue_metadata["expected_model"] == "big-pickle"

    respond = next(node for node in workflow["nodes"] if node["name"] == "Respond 202")
    execute = next(node for node in workflow["nodes"] if node["name"] == "Run Orchestrator")
    assert respond["parameters"]["options"]["responseCode"] == 202
    assert execute["parameters"]["options"]["waitForSubWorkflow"] is False


def test_explicit_invalid_and_mismatched_routes_fail_closed(tmp_path):
    source, _ = generated_intake(tmp_path)
    mismatch = run_intake(
        source,
        request({"route_policy": "FAIL_CLOSED", "expected_provider": "lmstudio", "expected_model": "big-pickle"}, provider="opencode", model="big-pickle"),
    )
    assert mismatch["intake_valid"] is False
    assert "ROUTE_BINDING_REBIND" in mismatch["errors"]

    invalid = run_intake(source, request(provider="unknown provider", model="big-pickle"))
    assert invalid["intake_valid"] is False
    assert "BAD_PROVIDER" in invalid["errors"]
    assert invalid["provider"] == "unknown provider"

    deepseek = run_intake(source, request(provider="openrouter", model="deepseek/deepseek-chat"))
    assert deepseek["intake_valid"] is False
    assert "DEEPSEEK_RETIRED" in deepseek["errors"]


def test_omitted_route_remains_explicitly_dynamic(tmp_path):
    source, _ = generated_intake(tmp_path)
    result = run_intake(source, request())
    assert result["intake_valid"] is True
    assert result["provider"] is None
    assert result["model"] is None
