#!/usr/bin/env python3
"""Generate the AutoDev Harness workflow JSON (n8n 2.26.8 node formats).

Usage: python3 generate_workflow.py <token-file> <output-json>
Token is read from file (never from argv/process listing).
"""

import json
import sys
import uuid


def uid():
    return str(uuid.uuid4())


TOKEN = open(sys.argv[1]).read().strip()
OUT = sys.argv[2]

ADAPTER_URL_EXPR = "={{ $json.config.adapter_base_url }}"
TOKEN_HEADER = {"name": "X-Harness-Token", "value": TOKEN}
CT_HEADER = {"name": "Content-Type", "value": "application/json"}


def http_node(name, path, body_expr, pos):
    return {
        "parameters": {
            "method": "POST",
            "url": "={{ $json.config.adapter_base_url }}" + path,
            "sendHeaders": True,
            "headerParameters": {"parameters": [TOKEN_HEADER, CT_HEADER]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": body_expr,
            "options": {"timeout": 120000},
        },
        "id": uid(),
        "name": name,
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4,
        "position": pos,
    }


def code_node(name, js_code, pos):
    return {
        "parameters": {"jsCode": js_code},
        "id": uid(),
        "name": name,
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": pos,
    }


def if_node(name, left_expr, pos, value2=None):
    if value2 is None:
        operator = {"type": "boolean", "operation": "true", "singleValue": True}
        cond = {"leftValue": left_expr, "operator": operator}
    else:
        operator = {"type": "string", "operation": "equals"}
        cond = {"leftValue": left_expr, "rightValue": value2, "operator": operator}
    return {
        "parameters": {
            "conditions": {
                "combinator": "and",
                "conditions": [cond],
                "options": {
                    "caseSensitive": True,
                    "leftValue": "",
                    "typeValidation": "loose",
                    "version": 2,
                },
            }
        },
        "id": uid(),
        "name": name,
        "type": "n8n-nodes-base.if",
        "typeVersion": 2,
        "position": pos,
    }


def merge_node(name, pos):
    return {
        "parameters": {"mode": "append", "numberInputs": 2},
        "id": uid(),
        "name": name,
        "type": "n8n-nodes-base.merge",
        "typeVersion": 3.2,
        "position": pos,
    }


CTX = json.dumps

nodes = []
conns = {}


def connect(src, out_idx, dst, in_idx=0):
    conns.setdefault(src, {"main": []})
    main = conns[src]["main"]
    while len(main) <= out_idx:
        main.append([])
    main[out_idx].append({"node": dst, "type": "main", "index": in_idx})


# ---- 1. Webhook Intake ------------------------------------------------------
nodes.append(
    {
        "parameters": {
            "httpMethod": "POST",
            "path": "autodev-harness",
            "responseMode": "lastNode",
            "options": {},
        },
        "id": uid(),
        "name": "Webhook Intake",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [0, 0],
        "webhookId": uid(),
    }
)

# ---- 2. Manual Trigger ------------------------------------------------------
nodes.append(
    {
        "parameters": {},
        "id": uid(),
        "name": "Manual Trigger",
        "type": "n8n-nodes-base.manualTrigger",
        "typeVersion": 1,
        "position": [0, 140],
    }
)

# ---- 3. Demo Task ------------------------------------------------------------
nodes.append(
    code_node(
        "Demo Task",
        r"""const demo = {
  task: "Canary: implement greet() function with unit tests (demo)",
  repository: "local-canary/greeter",
  execution_backend: "embedded",
  max_attempts: 2
};
return [{ json: demo }];""",
        [200, 140],
    )
)

# ---- 4. Normalize Intake ------------------------------------------------------
nodes.append(
    code_node(
        "Normalize Intake",
        r"""const input = $input.first()?.json ?? {};
const raw = (input.body && typeof input.body === 'object') ? input.body : input;
const task = raw.task ?? raw.issue ?? raw.description;
if (task === undefined || task === null || String(task).trim() === '') {
  return [{
    json: {
      contract: "harness.issue.v1",
      run_id: null,
      status: "INTAKE_INVALID",
      intake_valid: false,
      error: "INTAKE_INVALID",
      trace: { started_at: new Date().toISOString() }
    }
  }];
}
const runId = 'run-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
return [{
  json: {
    contract: "harness.issue.v1",
    run_id: runId,
    task: String(task),
    repository: raw.repository ?? "local-canary/greeter",
    attempt: 1,
    max_attempts: Number(raw.max_attempts ?? 2),
    fixture: raw.fixture ?? null,
    execution_backend: raw.execution_backend ?? "embedded",
    intake_valid: true,
    status: "OK",
    config: {
      adapter_base_url: raw.adapter_base_url ?? "http://192.168.1.136:8080"
    },
    trace: { started_at: new Date().toISOString() }
  }
}];""",
        [420, 0],
    )
)

# ---- 5. Intake Valid? --------------------------------------------------------
nodes.append(if_node("Intake Valid?", "={{ $json.intake_valid }}", [640, 0]))

# ---- 6. Baseline Adapter ------------------------------------------------------
BASELINE_BODY = r"={{ JSON.stringify({ run_id: $json.run_id, task: $json.task, repository: $json.repository, fixture: $json.fixture, execution_backend: $json.execution_backend, max_attempts: $json.max_attempts, config: { adapter_base_url: $json.config.adapter_base_url } }) }}"
nodes.append(http_node("Baseline Adapter", "/baseline", BASELINE_BODY, [860, 0]))

# ---- 7-9. Research Code/Docs/Tests --------------------------------------------
RESEARCH_BODY = r"={{ JSON.stringify({ run_id: $json.run_id, task: $json.task, repository: $json.repository, fixture: $json.fixture, execution_backend: $json.execution_backend, research_focus: '$(FOCUS)', config: { adapter_base_url: $json.config.adapter_base_url } }) }}"
nodes.append(
    http_node(
        "Research Code",
        "/research/code",
        RESEARCH_BODY.replace("$(FOCUS)", "code"),
        [1080, -140],
    )
)
nodes.append(
    http_node(
        "Research Docs",
        "/research/docs",
        RESEARCH_BODY.replace("$(FOCUS)", "docs"),
        [1080, 0],
    )
)
nodes.append(
    http_node(
        "Research Tests",
        "/research/tests",
        RESEARCH_BODY.replace("$(FOCUS)", "tests"),
        [1080, 140],
    )
)

# ---- 10-11. Merge Research ------------------------------------------------------
nodes.append(merge_node("Merge Research A+B", [1300, -70]))
nodes.append(merge_node("Merge Research +C", [1520, 0]))

# ---- 12. Research Contract -------------------------------------------------------
nodes.append(
    code_node(
        "Research Contract",
        r"""const items = $input.all().map(i => i.json);
const research = items.filter(i => i && i.contract === "harness.research.v1");
const first = items.find(i => i && i.run_id) || {};
const empty = research.length === 0 || research.every(r => r.empty);
return [{
  json: {
    contract: "harness.research.v1",
    run_id: first.run_id,
    task: first.task,
    repository: first.repository,
    fixture: first.fixture,
    execution_backend: first.execution_backend,
    attempt: first.attempt ?? 1,
    max_attempts: first.max_attempts ?? 2,
    config: first.config ?? {},
    research,
    research_empty: empty,
    trace: first.trace ?? {}
  }
}];""",
        [1740, 0],
    )
)

# ---- 13. Plan Adapter -----------------------------------------------------------
PLAN_BODY = r"={{ JSON.stringify({ run_id: $json.run_id, task: $json.task, repository: $json.repository, fixture: $json.fixture, execution_backend: $json.execution_backend, research: $json.research, config: { adapter_base_url: $json.config.adapter_base_url } }) }}"
nodes.append(http_node("Plan Adapter", "/plan", PLAN_BODY, [1960, 0]))

# ---- 14. Plan Gate ----------------------------------------------------------------
nodes.append(
    code_node(
        "Plan Gate",
        r"""const d = $input.first().json;
const plan = d.plan ?? null;
const errors = [];
if (!plan) errors.push("PLAN_MISSING");
if (!plan || !Array.isArray(plan.acceptance_criteria) || plan.acceptance_criteria.length === 0) errors.push("ACCEPTANCE_CRITERIA_MISSING");
if (!plan || !plan.build_scope) errors.push("BUILD_SCOPE_MISSING");
if (!plan || !Array.isArray(plan.required_tests)) errors.push("REQUIRED_TESTS_INVALID");
const approved = errors.length === 0;
return [{ json: { ...d, plan_gate: { approved, errors, checked_at: new Date().toISOString() } } }];""",
        [2180, 0],
    )
)

# ---- 15. Plan Approved? ------------------------------------------------------------
nodes.append(if_node("Plan Approved?", "={{ $json.plan_gate.approved }}", [2400, 0]))

# ---- 16. Final BLOCKED - Plan -------------------------------------------------------
nodes.append(
    code_node(
        "Final BLOCKED - Plan",
        r"""const d = $input.first().json;
const reason = d.intake_valid === false
  ? "INTAKE_INVALID"
  : ((d.plan_gate?.errors ?? []).join(",") || "PLAN_GATE_REJECTED");
return [{
  json: {
    contract: "harness.terminal.v1",
    run_id: d.run_id ?? null,
    decision: "BLOCKED",
    reason_code: reason,
    next_path: "HUMAN_OR_POLICY_INTERVENTION",
    plan_gate: d.plan_gate ?? null,
    status: "BLOCKED"
  }
}];""",
        [2400, 160],
    )
)

# ---- 17. Build Adapter ---------------------------------------------------------------
BUILD_BODY = r"={{ JSON.stringify({ run_id: $json.run_id, task: $json.task, repository: $json.repository, fixture: $json.fixture, execution_backend: $json.execution_backend, attempt: $json.attempt, plan: $json.plan, config: { adapter_base_url: $json.config.adapter_base_url } }) }}"
nodes.append(http_node("Build Adapter", "/build", BUILD_BODY, [2620, -60]))

# ---- 18. Verify Adapter ----------------------------------------------------------------
VERIFY_BODY = r"={{ JSON.stringify({ run_id: $json.run_id, task: $json.task, repository: $json.repository, fixture: $json.fixture, execution_backend: $json.execution_backend, attempt: $json.attempt, plan: $json.plan, build: $json.build, config: { adapter_base_url: $json.config.adapter_base_url } }) }}"
nodes.append(http_node("Verify Adapter", "/verify", VERIFY_BODY, [2840, -60]))

# ---- 19. Verification Passed? ------------------------------------------------------------
nodes.append(
    if_node("Verification Passed?", "={{ $json.verification.passed }}", [3060, -60])
)

# ---- 20. Retry Policy ----------------------------------------------------------------------
nodes.append(
    code_node(
        "Retry Policy",
        r"""const d = $input.first().json;
const v = d.verification ?? {};
const attempt = Number(d.attempt ?? 1);
const maxAttempts = Number(d.max_attempts ?? 2);
const hasSig = typeof v.failure_signature === "string" && v.failure_signature.length > 0;
const hasDelta = typeof v.strategy_delta === "string" && v.strategy_delta.length > 0;
let allowed = false;
let reason_code;
if (!hasSig) reason_code = "RETRY_DENIED_NO_FAILURE_SIGNATURE";
else if (!hasDelta) reason_code = "RETRY_DENIED_NO_STRATEGY_DELTA";
else if (attempt >= maxAttempts) reason_code = "RETRY_DENIED_ATTEMPT_LIMIT";
else { allowed = true; reason_code = "RETRY_ALLOWED_WITH_STRATEGY_DELTA"; }
return [{ json: { ...d, attempt, max_attempts: maxAttempts, retry_policy: { allowed, reason_code, attempt, max_attempts: maxAttempts, checked_at: new Date().toISOString() } } }];""",
        [3060, 160],
    )
)

# ---- 21. Retry Allowed? -----------------------------------------------------------------------
nodes.append(
    if_node("Retry Allowed?", "={{ $json.retry_policy.allowed }}", [3280, 160])
)

# ---- 22. Fix Adapter -----------------------------------------------------------------------------
FIX_BODY = r"={{ JSON.stringify({ run_id: $json.run_id, task: $json.task, repository: $json.repository, fixture: $json.fixture, execution_backend: $json.execution_backend, attempt: $json.attempt + 1, max_attempts: $json.max_attempts, strategy_delta: $json.verification.strategy_delta, config: { adapter_base_url: $json.config.adapter_base_url } }) }}"
nodes.append(http_node("Fix Adapter", "/fix", FIX_BODY, [3500, 20]))

# ---- 23. Verify Retry Adapter ---------------------------------------------------------------------
VERIFY_RETRY_BODY = r"={{ JSON.stringify({ run_id: $json.run_id, task: $json.task, repository: $json.repository, fixture: $json.fixture, execution_backend: $json.execution_backend, attempt: $json.fix.attempt, max_attempts: $json.max_attempts, plan: $json.plan, config: { adapter_base_url: $json.config.adapter_base_url } }) }}"
nodes.append(
    http_node("Verify Retry Adapter", "/verify", VERIFY_RETRY_BODY, [3720, 20])
)

# ---- 24. Retry Passed? -------------------------------------------------------------------------------
nodes.append(if_node("Retry Passed?", "={{ $json.verification.passed }}", [3940, 20]))

# ---- 25. Final SPLIT -------------------------------------------------------------------------------------
nodes.append(
    code_node(
        "Final SPLIT",
        r"""const d = $input.first().json;
let reason = d.retry_policy?.reason_code ?? null;
if (!reason) {
  const v = d.verification ?? {};
  const attempt = Number(d.attempt ?? 1);
  const maxAttempts = Number(d.max_attempts ?? 2);
  const hasSig = typeof v.failure_signature === "string" && v.failure_signature.length > 0;
  const hasDelta = typeof v.strategy_delta === "string" && v.strategy_delta.length > 0;
  if (!hasSig) reason = "RETRY_DENIED_NO_FAILURE_SIGNATURE";
  else if (!hasDelta) reason = "RETRY_DENIED_NO_STRATEGY_DELTA";
  else if (attempt >= maxAttempts) reason = "RETRY_DENIED_ATTEMPT_LIMIT";
  else reason = "RETRY_EXHAUSTED";
}
return [{
  json: {
    contract: "harness.terminal.v1",
    run_id: d.run_id ?? null,
    decision: "SPLIT",
    reason_code: reason,
    next_path: "DECOMPOSE_INTO_SUBTASKS",
    retry_policy: d.retry_policy ?? null,
    status: "SPLIT"
  }
}];""",
        [3500, 240],
    )
)

# ---- 26-28. Reviews -----------------------------------------------------------------------------------------
REVIEW_BODY = r"={{ JSON.stringify({ run_id: $json.run_id, task: $json.task, repository: $json.repository, fixture: $json.fixture, execution_backend: $json.execution_backend, attempt: $json.attempt, verification: $json.verification, config: { adapter_base_url: $json.config.adapter_base_url } }) }}"
nodes.append(merge_node("Merge Verify Paths", [3060, -140]))
nodes.append(
    http_node("Review Correctness", "/review/correctness", REVIEW_BODY, [3280, -200])
)
nodes.append(http_node("Review Security", "/review/security", REVIEW_BODY, [3280, -80]))
nodes.append(http_node("Review Quality", "/review/quality", REVIEW_BODY, [3280, 40]))

# ---- 29-30. Merge Reviews -----------------------------------------------------------------------------------------
nodes.append(merge_node("Merge Reviews A+B", [3500, -140]))
nodes.append(merge_node("Merge Reviews +C", [3720, -140]))

# ---- 31. Deterministic Controller -----------------------------------------------------------------------------------
nodes.append(
    code_node(
        "Deterministic Controller",
        r"""const items = $input.all().map(i => i.json);
const reviews = items.filter(i => i && i.review);
const first = items.find(i => i && i.run_id) || {};
const sevRank = { INFO: 0, LOW: 1, MEDIUM: 2, HIGH: 3, CRITICAL: 4 };
let decision = "DONE";
let reason_code = "ALL_HARD_GATES_GREEN";
const hardBlock = reviews.some(r => r.review.blocking === true && (sevRank[r.review.severity] ?? 0) >= sevRank.HIGH);
if (hardBlock) {
  decision = "BLOCKED";
  reason_code = "BLOCKING_HIGH_OR_CRITICAL_FINDING";
} else if (reviews.some(r => r.review.recommendation === "SPLIT")) {
  decision = "SPLIT";
  reason_code = "REVIEW_REQUESTED_SPLIT";
} else if (reviews.some(r => !["PASS", "OK", "APPROVED"].includes(r.review.status))) {
  decision = "FIX";
  reason_code = "NON_BLOCKING_REVIEW_FINDINGS";
}
let maxSeverity = "INFO";
for (const r of reviews) {
  if ((sevRank[r.review.severity] ?? 0) > (sevRank[maxSeverity] ?? 0)) maxSeverity = r.review.severity;
}
const nextPath = decision === "DONE" ? "FINALIZE_OR_PUBLISH"
  : decision === "FIX" ? "TARGETED_FIX_LOOP"
  : decision === "SPLIT" ? "DECOMPOSE_INTO_SUBTASKS"
  : "HUMAN_OR_POLICY_INTERVENTION";
return [{
  json: {
    contract: "harness.controller.v1",
    run_id: first.run_id,
    task: first.task,
    repository: first.repository,
    fixture: first.fixture,
    execution_backend: first.execution_backend,
    config: first.config ?? {},
    controller: {
      decision,
      reason_code,
      next_path: nextPath,
      max_severity: maxSeverity,
      review_count: reviews.length,
      reviews: reviews.map(r => r.review)
    },
    status: decision
  }
}];""",
        [3940, -140],
    )
)

# ---- 32-37. Decision chain ---------------------------------------------------------------------------------------------
nodes.append(
    if_node(
        "Decision DONE?",
        "={{ $json.controller.decision }}",
        [4160, -140],
        value2="DONE",
    )
)
nodes.append(
    if_node(
        "Decision FIX?", "={{ $json.controller.decision }}", [4160, -60], value2="FIX"
    )
)
nodes.append(
    if_node(
        "Decision SPLIT?",
        "={{ $json.controller.decision }}",
        [4160, 20],
        value2="SPLIT",
    )
)

# ---- 33-38. Terminal nodes ------------------------------------------------------------------------------------------------
nodes.append(
    code_node(
        "Final DONE",
        r"""const d = $input.first().json;
return [{
  json: {
    contract: "harness.terminal.v1",
    run_id: d.run_id ?? null,
    decision: "DONE",
    reason_code: d.controller?.reason_code ?? "ALL_HARD_GATES_GREEN",
    next_path: "FINALIZE_OR_PUBLISH",
    controller: d.controller ?? null,
    status: "DONE"
  }
}];""",
        [4380, -260],
    )
)

nodes.append(
    code_node(
        "Final FIX",
        r"""const d = $input.first().json;
return [{
  json: {
    contract: "harness.terminal.v1",
    run_id: d.run_id ?? null,
    decision: "FIX",
    reason_code: d.controller?.reason_code ?? "NON_BLOCKING_REVIEW_FINDINGS",
    next_path: "TARGETED_FIX_LOOP",
    controller: d.controller ?? null,
    status: "FIX"
  }
}];""",
        [4380, -180],
    )
)

nodes.append(
    code_node(
        "Final SPLIT - Review",
        r"""const d = $input.first().json;
return [{
  json: {
    contract: "harness.terminal.v1",
    run_id: d.run_id ?? null,
    decision: "SPLIT",
    reason_code: d.controller?.reason_code ?? "REVIEW_REQUESTED_SPLIT",
    next_path: "DECOMPOSE_INTO_SUBTASKS",
    controller: d.controller ?? null,
    status: "SPLIT"
  }
}];""",
        [4600, -100],
    )
)

nodes.append(
    code_node(
        "Final BLOCKED - Review",
        r"""const d = $input.first().json;
return [{
  json: {
    contract: "harness.terminal.v1",
    run_id: d.run_id ?? null,
    decision: "BLOCKED",
    reason_code: d.controller?.reason_code ?? "BLOCKING_HIGH_OR_CRITICAL_FINDING",
    next_path: "HUMAN_OR_POLICY_INTERVENTION",
    controller: d.controller ?? null,
    status: "BLOCKED"
  }
}];""",
        [4600, -20],
    )
)

# ---- connections -----------------------------------------------------------------------------------------------------------
connect("Webhook Intake", 0, "Normalize Intake")
connect("Manual Trigger", 0, "Demo Task")
connect("Demo Task", 0, "Normalize Intake")
connect("Normalize Intake", 0, "Intake Valid?")
connect("Intake Valid?", 0, "Baseline Adapter")
connect("Intake Valid?", 1, "Final BLOCKED - Plan")

connect("Baseline Adapter", 0, "Research Code")
connect("Baseline Adapter", 0, "Research Docs")
connect("Baseline Adapter", 0, "Research Tests")

connect("Research Code", 0, "Merge Research A+B", 0)
connect("Research Docs", 0, "Merge Research A+B", 1)
connect("Merge Research A+B", 0, "Merge Research +C", 0)
connect("Research Tests", 0, "Merge Research +C", 1)
connect("Merge Research +C", 0, "Research Contract")

connect("Research Contract", 0, "Plan Adapter")
connect("Plan Adapter", 0, "Plan Gate")
connect("Plan Gate", 0, "Plan Approved?")
connect("Plan Approved?", 0, "Build Adapter")
connect("Plan Approved?", 1, "Final BLOCKED - Plan")

connect("Build Adapter", 0, "Verify Adapter")
connect("Verify Adapter", 0, "Verification Passed?")
connect("Verification Passed?", 0, "Merge Verify Paths", 0)
connect("Verification Passed?", 1, "Retry Policy")

connect("Retry Policy", 0, "Retry Allowed?")
connect("Retry Allowed?", 0, "Fix Adapter")
connect("Retry Allowed?", 1, "Final SPLIT")

connect("Fix Adapter", 0, "Verify Retry Adapter")
connect("Verify Retry Adapter", 0, "Retry Passed?")
connect("Retry Passed?", 0, "Merge Verify Paths", 1)
connect("Retry Passed?", 1, "Final SPLIT")

connect("Merge Verify Paths", 0, "Review Correctness")
connect("Merge Verify Paths", 0, "Review Security")
connect("Merge Verify Paths", 0, "Review Quality")

connect("Review Correctness", 0, "Merge Reviews A+B", 0)
connect("Review Security", 0, "Merge Reviews A+B", 1)
connect("Merge Reviews A+B", 0, "Merge Reviews +C", 0)
connect("Review Quality", 0, "Merge Reviews +C", 1)
connect("Merge Reviews +C", 0, "Deterministic Controller")

connect("Deterministic Controller", 0, "Decision DONE?")
connect("Decision DONE?", 0, "Final DONE")
connect("Decision DONE?", 1, "Decision FIX?")
connect("Decision FIX?", 0, "Final FIX")
connect("Decision FIX?", 1, "Decision SPLIT?")
connect("Decision SPLIT?", 0, "Final SPLIT - Review")
connect("Decision SPLIT?", 1, "Final BLOCKED - Review")

workflow = {
    "name": "AutoDev Harness - Graph Orchestrator v1",
    "nodes": nodes,
    "connections": conns,
    "settings": {"executionOrder": "v1"},
}

with open(OUT, "w") as f:
    json.dump(workflow, f, indent=2)

print("NODES:", len(nodes))
print("OUT:", OUT)
