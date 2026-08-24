"""Deterministic regression tests for the adapter -> Plan Gate seam.

These tests deliberately model the JSON boundary rather than calling a
provider. The generated workflow assertions ensure the model remains tied to
the canonical generator and that worker failures cannot become PLAN_MISSING.
"""

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "workflow" / "v2" / "generate_workflows_v2.py"
CONFIG = ROOT / "workflow" / "v2" / "config.json"


def gate_for_job(job, artifact=None):
    """Expected boundary semantics for a plan job returned by the adapter."""
    if job.get("status") != "completed":
        return {
            "status": "BLOCKED",
            "reason_code": job.get("failure_class") or "INFRA_FAILURE",
            "failure_signature": job.get("failure_signature"),
        }
    result = job.get("result")
    if result is None and job.get("result_ref") and artifact is not None:
        result = artifact
    if result is None:
        return {"status": "BLOCKED", "reason_code": "PLAN_MISSING"}
    if result.get("contract") != "autodev.plan.v1":
        return {"status": "BLOCKED", "reason_code": "CONTRACT_FAILURE"}
    required = ("version", "run_id", "repository_head", "targets",
                "acceptance_criteria", "required_tests", "build_scope",
                "context", "safety")
    if any(key not in result for key in required):
        return {"status": "BLOCKED", "reason_code": "CONTRACT_FAILURE"}
    return {"status": "APPROVED", "reason_code": "PLAN_GATE_APPROVED"}


def valid_plan():
    return {
        "contract": "autodev.plan.v1", "version": "v1", "run_id": "run-test",
        "repository_head": "a" * 40, "targets": {"files": ["lib/a.dart"]},
        "acceptance_criteria": ["criterion"], "required_tests": ["flutter test"],
        "build_scope": {"allowed_files": ["lib/a.dart"]},
        "context": {"fingerprint": "b" * 64},
        "safety": {"sentinel_absent": True, "repo_unchanged": True,
                   "write_attempts": 0},
    }


def test_plan_job_boundary_cases():
    plan = valid_plan()
    assert gate_for_job({"status": "completed", "result": plan})["status"] == "APPROVED"  # P1
    assert gate_for_job({"status": "completed", "result": None,
                         "result_ref": "artifact://plan"}, plan)["status"] == "APPROVED"  # P2
    assert gate_for_job({"status": "completed", "result": None})["reason_code"] == "PLAN_MISSING"  # P3
    failed = {"status": "failed", "failure_class": "CONTRACT_FAILURE",
              "failure_signature": "PLAN_PARSE_FAILED"}
    assert gate_for_job(failed)["reason_code"] == "CONTRACT_FAILURE"  # P4
    invalid = dict(plan, contract="wrong.contract")
    assert gate_for_job({"status": "completed", "result": invalid})["reason_code"] == "CONTRACT_FAILURE"  # P5


def test_generated_plan_and_webhook_contracts(tmp_path):
    out = tmp_path / "workflows"
    subprocess.run([sys.executable, str(GENERATOR), str(CONFIG), str(out)], check=True)
    plan = json.loads((out / "30 AutoDev Plan.json").read_text())
    orch = json.loads((out / "01 AutoDev Orchestrator.json").read_text())
    assert "research: s.research || null" in next(
        n["parameters"]["jsCode"] for n in plan["nodes"] if n["name"] == "Prep plan"
    )
    post_plan = next(n["parameters"]["jsCode"] for n in orch["nodes"] if n["name"] == "Post-Plan")
    assert "failure.failure_class" in post_plan
    assert "PLAN_MISSING" in post_plan
    assert "Plan Failure Gate" in {e["node"] for outs in plan["connections"].values() for group in outs.get("main", []) for e in group}

    for path in out.glob("*.json"):
        workflow = json.loads(path.read_text())
        for node in workflow["nodes"]:
            if node.get("type") != "n8n-nodes-base.webhook":
                continue
            creds = node.get("credentials", {})
            if creds.get("httpHeaderAuth"):
                assert node["parameters"].get("authentication") == "headerAuth", path.name


def test_external_default_branch_is_not_hardcoded_main():
    source = (ROOT / "workflow" / "v2" / "generate_workflows_v2.py").read_text()
    assert "repository_ref" in source
    assert "repository_ref: 'main'" not in source


def test_generated_orchestrator_proves_all_terminal_handoffs(tmp_path):
    out = tmp_path / "workflows"
    subprocess.run([sys.executable, str(GENERATOR), str(CONFIG), str(out)], check=True)
    orch = json.loads((out / "01 AutoDev Orchestrator.json").read_text())
    names = {node["name"] for node in orch["nodes"]}
    assert {"Verify State Prep", "Verify State Update", "Verify State Restore"} <= names
    assert {"Decision State Prep", "Decision State Update", "Decision State Restore"} <= names
    assert "Decision Retry Guard" in names

    def has_edge(source, target, index=0):
        groups = orch["connections"][source]["main"]
        return any(
            edge["node"] == target
            for edge in groups[index]
        )

    assert has_edge("Build Attempt Attempt Restore", "Verify State Prep")
    assert has_edge("Fix Attempt Attempt Restore", "Verify State Prep")
    assert has_edge("Decision Fix Attempt Attempt Restore", "Verify State Prep")
    assert has_edge("Verify State Restore", "Run Verify")
    assert has_edge("Security Blocked?", "Decision State Prep", 1)
    assert has_edge("Decision State Restore", "Run Decision")
    assert has_edge("Post-Decision", "Decision Retry Guard")
    assert has_edge("Decision Retry Guard", "Decision DONE?")
    retry_guard = next(
        n["parameters"]["jsCode"]
        for n in orch["nodes"] if n["name"] == "Decision Retry Guard"
    )
    assert "RETRY_DENIED_ATTEMPT_LIMIT" in retry_guard
