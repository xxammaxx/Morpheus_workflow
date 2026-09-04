import json
from pathlib import Path


ROOT = Path(__file__).parents[3]
WORKFLOW = ROOT / "n8n" / "workflows" / "autodev" / "01 AutoDev Orchestrator.json"


def test_build_dispatch_error_uses_existing_terminal_failure_transition():
    workflow = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    run_build = next(node for node in workflow["nodes"] if node["name"] == "Run Build")

    assert run_build["onError"] == "continueRegularOutput"
    assert workflow["connections"]["Run Build"]["main"][0][0]["node"] == "Post-Build"
    assert workflow["connections"]["Build OK?"]["main"][1][0]["node"] == "Build Failed Prep"
