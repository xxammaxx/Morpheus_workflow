#!/usr/bin/env python3
"""Cross-language validator equivalence: Python vs JS twin.

The JS validator is embedded in n8n Code nodes for deterministic gates.
Both must produce identical ok/errors on every fixture.

Run: python3 runtime/tests/test_validator_equivalence.py  (requires node)
"""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from contracts import registry  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
JS_VALIDATOR = os.path.join(ROOT, "contracts", "validator.js")
FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures_equivalence.json")


def build_fixtures():
    from test_contracts import sample_issue, sample_plan  # noqa

    fixtures = {}
    schemas = registry.load_all_schemas()

    # valid samples per contract
    valid = {
        "autodev.issue.v1": sample_issue(),
        "autodev.baseline.v1": {
            "contract": "autodev.baseline.v1",
            "version": "v1",
            "run_id": "run-test-0001",
            "repository": {
                "identity": "git@x/y",
                "head": "abcdef1",
                "branch": "main",
                "working_tree_clean": True,
                "build_system": "python",
                "test_system": "pytest",
                "relevant_files": ["src/a.py"],
                "constraints": [],
            },
            "read_only_proof": {"sentinel_absent": True, "git_status_unchanged": True},
        },
        "autodev.research.v1": {
            "contract": "autodev.research.v1",
            "version": "v1",
            "run_id": "run-test-0001",
            "areas": {"code": "n", "docs": "n", "tests": "n"},
            "parallelism": {
                "jobs": [
                    {
                        "job_id": "j1",
                        "job_type": "research.code",
                        "started_at": "t",
                        "ended_at": "t",
                        "duration_ms": 1,
                    }
                ],
                "overlap_proven": True,
            },
        },
        "autodev.plan.v1": sample_plan(),
        "autodev.build-input.v1": {
            "contract": "autodev.build-input.v1",
            "version": "v1",
            "run_id": "run-test-0001",
            "attempt_id": "a:build:1",
            "plan_fingerprint": "b" * 64,
            "repository_head": "abcdef1",
            "targets": {"files": ["src/greeter.py"]},
            "acceptance_criteria": ["ok"],
            "required_tests": ["t"],
            "build_scope": {"allowed_files": ["src/greeter.py"]},
        },
        "autodev.build-result.v1": {
            "contract": "autodev.build-result.v1",
            "version": "v1",
            "run_id": "run-test-0001",
            "status": "success",
            "changed_files": [{"path": "src/a.py", "change": "add", "size": 10}],
            "summary": "ok",
        },
        "autodev.verification.v1": {
            "contract": "autodev.verification.v1",
            "version": "v1",
            "run_id": "run-test-0001",
            "passed": True,
            "checks": [
                {"name": "unit", "type": "unit", "passed": True, "detail": "1 passed"}
            ],
            "failure_class": None,
            "failure_signature": None,
            "new_evidence": [],
        },
        "autodev.finding.v1": {
            "category": "security",
            "severity": "CRITICAL",
            "confidence": "HIGH",
            "blocking": True,
            "rule": "SEC-001",
            "evidence": {"file": "src/a.py", "symbol": "x", "line_range": "1-5"},
            "recommendation": "remove secret",
        },
        "autodev.review-batch.v1": {
            "contract": "autodev.review-batch.v1",
            "version": "v1",
            "run_id": "run-test-0001",
            "reviews": [
                {
                    "category": "security",
                    "verdict": "FAIL",
                    "findings": [
                        {
                            "category": "security",
                            "severity": "CRITICAL",
                            "confidence": "HIGH",
                            "blocking": True,
                            "rule": "SEC-001",
                            "evidence": {"file": "a.py"},
                            "recommendation": "x",
                        }
                    ],
                }
            ],
            "blocked": True,
            "blocking_findings": [],
            "parallelism": {"jobs": [], "overlap_proven": True},
        },
        "autodev.decision.v1": {
            "contract": "autodev.decision.v1",
            "version": "v1",
            "run_id": "run-test-0001",
            "decision": "DONE",
            "reason_code": "ALL_HARD_GATES_GREEN",
            "next": "terminal",
            "evidence": {"verification_ref": "v", "review_ref": "r"},
        },
        "autodev.split.v1": {
            "contract": "autodev.split.v1",
            "version": "v1",
            "parent_run_id": "run-test-0001",
            "reason": "retry exhausted",
            "reason_code": "RETRY_DENIED_ATTEMPT_LIMIT",
            "subtasks": [
                {
                    "id": "st-1",
                    "title": "Subtask A",
                    "description": "do thing A properly",
                },
                {
                    "id": "st-2",
                    "title": "Subtask B",
                    "description": "do thing B properly",
                },
            ],
            "dependencies": [["st-1", "st-2"]],
            "acceptance_criteria": ["A and B done"],
            "limits": {"max_split_depth": 2, "max_subtasks": 5, "current_depth": 1},
        },
        "autodev.run-event.v1": {
            "contract": "autodev.run-event.v1",
            "version": "v1",
            "run_id": "run-test-0001",
            "event": "STATE_CHANGE",
            "timestamp": "2026-08-17T00:00:00Z",
            "state": {"previous_state": "ACCEPTED", "new_state": "BASELINING"},
            "reason_code": "INTAKE_OK",
        },
        # --- HAMH contracts (ADR-2026-08-20): Py/JS twins must agree too
        "hamh.harness.v1": {
            "contract": "hamh.harness.v1",
            "version": "v1",
            "harness_id": "deepseek/v4-flash/0731/thinking/build/v1",
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "model_revision": "0731",
            "task_class": "build",
            "runtime_mode": "thinking",
            "harness_version": "v1",
            "status": "CANDIDATE",
            "fingerprint": "a" * 64,
            "prompt_profile": {"style": "baseline"},
            "context_profile": {"stable_prefix": ["system"]},
            "tool_profile": {"capabilities": {"read": True}, "presentation": "flat"},
        },
        "hamh.resolution.v1": {
            "contract": "hamh.resolution.v1",
            "version": "v1",
            "resolved_harness_id": "baseline/shared/default/auto/plan/v1",
            "harness_version": "v1",
            "fingerprint": "b" * 64,
            "provider": "unknown",
            "model": "unknown",
            "model_revision": None,
            "task_class": "plan",
            "runtime_mode": "auto",
            "is_fallback": True,
            "effective_tool_profile": {
                "capabilities": {"read": True},
                "presentation": "flat",
            },
            "effective_context_profile": {"stable_prefix": ["system"]},
            "effective_reasoning_profile": {"thinking": "auto"},
            "fallback_profile": {"name": "baseline"},
        },
    }

    for cid, sample in valid.items():
        fixtures["valid_" + cid] = {"schema": schemas[cid], "payload": sample}

    # invalid variants
    fixtures["invalid_missing_task"] = {
        "schema": schemas["autodev.issue.v1"],
        "payload": {
            k: v
            for k, v in valid["autodev.issue.v1"].items()
            if k != "task_description"
        },
    }
    fixtures["invalid_bad_runid"] = {
        "schema": schemas["autodev.issue.v1"],
        "payload": dict(valid["autodev.issue.v1"], run_id="bad id!"),
    }
    fixtures["invalid_extra_prop"] = {
        "schema": schemas["autodev.plan.v1"],
        "payload": dict(valid["autodev.plan.v1"], evil_extra=1),
    }
    fixtures["invalid_wrong_type"] = {
        "schema": schemas["autodev.plan.v1"],
        "payload": dict(valid["autodev.plan.v1"], acceptance_criteria="not-an-array"),
    }
    fixtures["invalid_short_string"] = {
        "schema": schemas["autodev.plan.v1"],
        "payload": dict(valid["autodev.plan.v1"], run_id="ab"),
    }
    fixtures["invalid_sentinel_false"] = {
        "schema": schemas["autodev.plan.v1"],
        "payload": dict(
            valid["autodev.plan.v1"],
            safety={
                "sentinel_absent": False,
                "repo_unchanged": True,
                "write_attempts": 0,
            },
        ),
    }
    fixtures["invalid_finding_severity"] = {
        "schema": schemas["autodev.finding.v1"],
        "payload": dict(valid["autodev.finding.v1"], severity="EXTREME"),
    }
    fixtures["invalid_garbage"] = {
        "schema": schemas["autodev.decision.v1"],
        "payload": {"foo": 1},
    }
    fixtures["invalid_null_payload"] = {
        "schema": schemas["autodev.decision.v1"],
        "payload": None,
    }
    fixtures["invalid_list_payload"] = {
        "schema": schemas["autodev.decision.v1"],
        "payload": [1, 2, 3],
    }
    fixtures["invalid_minitems"] = {
        "schema": schemas["autodev.plan.v1"],
        "payload": dict(valid["autodev.plan.v1"], targets={"files": [], "symbols": []}),
    }
    fixtures["invalid_enum_check"] = {
        "schema": schemas["autodev.verification.v1"],
        "payload": dict(
            valid["autodev.verification.v1"],
            checks=[{"name": "u", "type": "crystal-ball", "passed": True}],
        ),
    }
    fixtures["invalid_const"] = {
        "schema": schemas["autodev.issue.v1"],
        "payload": dict(valid["autodev.issue.v1"], contract="autodev.issue.v2"),
    }
    fixtures["invalid_required_nested"] = {
        "schema": schemas["autodev.build-result.v1"],
        "payload": dict(
            valid["autodev.build-result.v1"],
            changed_files=[{"path": "a.py", "change": "add"}],
        ),
    }
    fixtures["invalid_oneof_alt"] = {
        "schema": schemas["autodev.verification.v1"],
        "payload": dict(valid["autodev.verification.v1"], failure_class="NONSENSE"),
    }
    # HAMH invalid variants (Py/JS twins must agree on the new contracts)
    fixtures["invalid_hamh_bad_status"] = {
        "schema": schemas["hamh.harness.v1"],
        "payload": dict(valid["hamh.harness.v1"], status="SUPER_ACTIVE"),
    }
    fixtures["invalid_hamh_bad_fingerprint"] = {
        "schema": schemas["hamh.harness.v1"],
        "payload": dict(valid["hamh.harness.v1"], fingerprint="not-hex"),
    }
    fixtures["invalid_hamh_bad_task_class"] = {
        "schema": schemas["hamh.harness.v1"],
        "payload": dict(valid["hamh.harness.v1"], task_class="hacking"),
    }
    fixtures["invalid_hamh_resolution_missing"] = {
        "schema": schemas["hamh.resolution.v1"],
        "payload": {
            k: v
            for k, v in valid["hamh.resolution.v1"].items()
            if k != "effective_reasoning_profile"
        },
    }
    fixtures["invalid_hamh_resolution_bad_fp"] = {
        "schema": schemas["hamh.resolution.v1"],
        "payload": dict(valid["hamh.resolution.v1"], fingerprint="xyz"),
    }
    return fixtures


def main():
    fixtures = build_fixtures()
    with open(FIXTURES, "w") as f:
        json.dump(fixtures, f, ensure_ascii=False)

    script = r"""
const fs = require('fs');
const { validateAutodevContract } = require(process.argv[2]);
const fixtures = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
let bad = 0;
for (const [name, fx] of Object.entries(fixtures)) {
  const r = validateAutodevContract(fx.payload, fx.schema);
  const out = { ok: r.ok, errors: r.errors };
  console.log(JSON.stringify({ name, out }));
  if (!r.ok && r.errors.length === 0) bad++;
}
process.exit(bad ? 1 : 0);
"""
    js = os.path.join(os.path.dirname(__file__), "_eq_check.js")
    with open(js, "w") as f:
        f.write(script)

    proc = subprocess.run(
        ["node", js, JS_VALIDATOR, FIXTURES], capture_output=True, text=True
    )
    if proc.returncode != 0:
        print("NODE ERROR:", proc.stderr[:2000])
        return 1

    js_results = {}
    for line in proc.stdout.strip().splitlines():
        row = json.loads(line)
        js_results[row["name"]] = row["out"]

    passed = failed = 0
    for name, fx in fixtures.items():
        py = registry.validate(fx["payload"], fx["schema"].get("$id"))
        py_out = {"ok": py["ok"], "errors": py["errors"]}
        js_out = js_results.get(name, {})
        if py_out == js_out:
            passed += 1
            print("PASS EQ %s" % name)
        else:
            failed += 1
            print(
                "FAIL EQ %s\n  py: %s\n  js: %s"
                % (name, json.dumps(py_out), json.dumps(js_out))
            )

    print("\nRESULT %d passed, %d failed" % (passed, failed))
    os.unlink(js)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
