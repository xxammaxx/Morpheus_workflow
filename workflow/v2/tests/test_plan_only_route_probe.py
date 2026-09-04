"""Provider-free tests for the bounded canonical plan-only branch."""

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
GENERATOR = ROOT / "workflow" / "v2" / "generate_workflows_v2.py"
CONFIG = ROOT / "workflow" / "v2" / "config.json"


def generated(tmp_path):
    subprocess.run([sys.executable, str(GENERATOR), str(CONFIG), str(tmp_path)], check=True)
    start = json.loads((tmp_path / "00 AutoDev API Start.json").read_text())
    orchestrator = json.loads((tmp_path / "01 AutoDev Orchestrator.json").read_text())
    plan = json.loads((tmp_path / "30 AutoDev Plan.json").read_text())
    validate = next(n["parameters"]["jsCode"] for n in start["nodes"] if n["name"] == "Validate Intake")
    return validate, start, orchestrator, plan


def run_js(source, body):
    runner = """
const fs = require('fs');
const value = JSON.parse(fs.readFileSync(0, 'utf8'));
const result = new Function('$json', value.source)(value.body);
process.stdout.write(JSON.stringify(result));
"""
    completed = subprocess.run(
        ["node", "-e", runner], input=json.dumps({"source": source, "body": body}),
        text=True, capture_output=True, check=True,
    )
    return json.loads(completed.stdout)[0]["json"]


def task(metadata=None, **values):
    item = {
        "run_id": "run-plan-only-contract", "task_ref": "qualification:exact-route:001",
        "repository_ref": "fixture-only", "workspace": "route-contract",
        "task_description": "Provider-free bounded route qualification plan probe.",
        "max_attempts": 1, "provider": "opencode", "model": "big-pickle",
        "backend": "opencode-builder-8001", **values,
    }
    if metadata is not None:
        item["x-metadata"] = metadata
    return {"task": item}


def valid_metadata():
    return {
        "contract": "autodev.route-probe.v1", "version": "v1",
        "execution_scope": "PLAN_ONLY_ROUTE_PROBE", "backend": "opencode-builder-8001",
        "provider": "opencode", "model": "big-pickle", "route_policy": "FAIL_CLOSED",
        "expected_provider": "opencode", "expected_model": "big-pickle", "max_attempts": 1,
        "changes_expected": False, "no_change_required": True,
        "requested_action": "QUALIFICATION_PLAN_ONLY_ROUTE_PROBE",
    }


def test_valid_probe_is_accepted_and_bound(tmp_path):
    source, _, _, _ = generated(tmp_path)
    result = run_js(source, task(valid_metadata()))
    assert result["intake_valid"] is True
    assert result["issue"]["x-metadata"]["execution_scope"] == "PLAN_ONLY_ROUTE_PROBE"
    assert result["provider"] == "opencode" and result["model"] == "big-pickle"


def test_probe_invariant_failures_are_rejected_without_normal_fallback(tmp_path):
    source, _, _, _ = generated(tmp_path)
    for key, value in (("provider", "lmstudio"), ("model", "deepseek/chat"),
                       ("route_policy", "ALLOW_FALLBACK"), ("max_attempts", 2),
                       ("changes_expected", True), ("execution_scope", "UNKNOWN")):
        metadata = valid_metadata()
        metadata[key] = value
        result = run_js(source, task(metadata))
        assert result["intake_valid"] is False
        assert result["issue"]["x-metadata"].get("execution_scope") == value if key == "execution_scope" else True


def test_scope_requires_probe_identity_and_cannot_be_ordinary_plan(tmp_path):
    source, _, orchestrator, plan = generated(tmp_path)
    bad_identity = run_js(source, task(valid_metadata(), task_ref="ordinary-plan"))
    assert bad_identity["intake_valid"] is False
    ordinary = run_js(source, task(None, task_ref="ordinary-plan", provider=None, model=None, max_attempts=2))
    assert ordinary["intake_valid"] is True
    init = next(n for n in orchestrator["nodes"] if n["name"] == "Init Run State")
    assert "execution_scope" in init["parameters"]["jsCode"]
    assert "Plan-Only Probe Scope?" in orchestrator["connections"]["Init Run State"]["main"][0][0]["node"]
    assert orchestrator["connections"]["Plan-Only Probe Scope?"]["main"][1][0]["node"] == "Baseline State Prep"
    assert orchestrator["connections"]["Run Plan (Probe)"]["main"][0][0]["node"] == "Post-Plan (Probe)"
    assert not any(edge["node"] == "Run Build" for output in orchestrator["connections"].get("Post-Plan (Probe)", {}).get("main", []) for edge in output)
    plan_input = next(n for n in plan["nodes"] if n["name"] == "Prep plan")["parameters"]["jsCode"]
    assert "s.research || null" in plan_input


def test_probe_dispatch_and_terminal_structure(tmp_path):
    _, _, orchestrator, _ = generated(tmp_path)
    names = {n["name"] for n in orchestrator["nodes"]}
    assert {"Run Plan (Probe)", "Plan-Only Probe Complete Prep", "Plan-Only Probe Failed Prep"} <= names
    assert "Run Baseline" not in [e["node"] for e in orchestrator["connections"]["Plan-Only Probe Scope?"]["main"][0]]
    assert "Run Research" not in [e["node"] for e in orchestrator["connections"]["Plan-Only Probe Scope?"]["main"][0]]
    assert orchestrator["connections"]["Run Plan (Probe)"]["main"][0][0]["node"] == "Post-Plan (Probe)"
    assert "Run Build" not in json.dumps(orchestrator["connections"]["Probe Plan OK?"]["main"])
