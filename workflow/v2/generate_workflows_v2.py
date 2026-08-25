#!/usr/bin/env python3
"""AutoDev Harness v2 — n8n workflow generator.

Builds the 12 modular control-plane workflows from the canonical spec:
  00 API Start, 01 Orchestrator, 02 API Status,
  10 Baseline, 20 Research Batch, 30 Plan, 40 Build, 50 Verify,
  60 Review Batch, 70 Decision, 80 Fix, 90 Split

Run: python3 generate_workflows_v2.py <config.json> <outdir>
Config: {"n8n_base", "adapter_base", "webhook_base", "tables": {"runs": id,
        "attempts": id}, "creds": {"n8n_api": {"id","name"},
        "harness_token": {"id","name"}, "api_auth": {"id","name"}}}

The output JSON files are the production exports (output artefacts).
"""

import json
import os
import sys
import urllib.parse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.join(BASE_DIR, "..", "..")
SCHEMA_DIR = os.path.join(REPO_ROOT, "runtime", "contracts", "schemas")


def embed_schema(name):
    with open(os.path.join(SCHEMA_DIR, name + ".schema.json")) as f:
        return json.dumps(json.load(f), sort_keys=True)


# ------------------------------------------------------------ node helpers --
def node(name, ntype, parameters, position, type_version=2, credentials=None):
    n = {
        "parameters": parameters,
        "id": name.replace(" ", "-").lower()[:32],
        "name": name,
        "type": ntype,
        "typeVersion": type_version,
        "position": position,
    }
    if credentials:
        n["credentials"] = credentials
    return n


def code_node(name, js, pos, creds=None):
    return node(name, "n8n-nodes-base.code", {"jsCode": js}, pos, 2, creds)


def http_node(
    name,
    method,
    url,
    body_expr,
    pos,
    cred,
    options=None,
    params_extra=None,
    send_body=True,
):
    p = {
        "method": method,
        "url": "=" + url,
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendBody": send_body,
        "specifyBody": "json",
        "jsonBody": "={{ " + body_expr + " }}",
        "options": options or {},
    }
    if params_extra:
        p.update(params_extra)
    # the url must always be an expression (n8n evaluates {{ }} inside "=" strings)
    if "url" in p and not p["url"].startswith("="):
        p["url"] = "=" + p["url"]
    return node(name, "n8n-nodes-base.httpRequest", p, pos, 4, {"httpHeaderAuth": cred})


def wait_node(name, seconds, pos):
    return node(
        name, "n8n-nodes-base.wait", {"amount": seconds, "unit": "seconds"}, pos, 1
    )


IF_OPTIONS = {
    "caseSensitive": True,
    "leftValue": "",
    "typeValidation": "loose",
    "version": 2,
}


def if_node(name, conditions, pos):
    return node(
        name,
        "n8n-nodes-base.if",
        {
            "conditions": {
                "combinator": "and",
                "conditions": conditions,
                "options": IF_OPTIONS,
            }
        },
        pos,
        2,
    )


def bool_if(name, expr_true, pos):
    return if_node(
        name,
        [
            {
                "leftValue": "={{%s}}" % expr_true,
                "operator": {
                    "type": "boolean",
                    "operation": "true",
                    "singleValue": True,
                },
            }
        ],
        pos,
    )


def str_if(name, expr, equals, pos):
    return if_node(
        name,
        [
            {
                "leftValue": "={{%s}}" % expr,
                "rightValue": "=" + equals,
                "operator": {"type": "string", "operation": "equals"},
            }
        ],
        pos,
    )


def num_if(name, expr, op, value, pos):
    return if_node(
        name,
        [
            {
                "leftValue": "={{%s}}" % expr,
                "rightValue": value,
                "operator": {"type": "number", "operation": op},
            }
        ],
        pos,
    )


def webhook_node(name, path, method, auth_cred, pos, response_mode="responseNode"):
    parameters = {
        "httpMethod": method,
        "path": path,
        "responseMode": response_mode,
        "options": {},
    }
    credentials = None
    if auth_cred:
        # n8n 2.x requires the Webhook node's authentication mode itself to
        # be enabled. A credential reference alone is not enforcement.
        parameters["authentication"] = "headerAuth"
        credentials = {"httpHeaderAuth": auth_cred}
    return node(
        name,
        "n8n-nodes-base.webhook",
        parameters,
        pos,
        2,
        credentials,
    )


def respond_node(name, pos, response_body="={{ JSON.stringify($json) }}", tv=2):
    return node(
        name,
        "n8n-nodes-base.respondToWebhook",
        {"respondWith": "json", "responseBody": response_body},
        pos,
        tv,
    )


def execute_wf_node(cfg, name, wf_name, pos, options=None):
    wfid = cfg.wfid(wf_name)
    return node(
        name,
        "n8n-nodes-base.executeWorkflow",
        {
            "source": "database",
            "workflowId": {
                "__rl": True,
                "mode": "list",
                "value": wfid,
                "cachedResultName": wf_name,
            },
            "mode": "once",
            "options": options or {},
        },
        pos,
        4,
    )


def set_node(name, values, pos):
    return node(
        name, "n8n-nodes-base.set", {"values": values, "keepOnlySet": True}, pos, 2
    )


# --------------------------------------------------------------- workflow --
class WF:
    def __init__(self, name):
        self.name = name
        self.nodes = []
        self.connections = {}
        self._map = {}
        self._pending = []

    def add_node(self, n):
        self._map[n["name"]] = n
        self.nodes.append(n)
        return n

    def add(self, src, dst, out_index=0):
        s = src["name"] if isinstance(src, dict) else src
        d = dst["name"] if isinstance(dst, dict) else dst
        assert s in self._map, s
        if d not in self._map:
            self._pending.append((s, d, out_index))
            return
        self._wire(s, d, out_index)

    def _wire(self, s, d, out_index):
        mains = self.connections.setdefault(s, {}).setdefault("main", [])
        while len(mains) <= out_index:
            mains.append([])
        if any(e.get("node") == d for e in mains[out_index]):
            return
        mains[out_index].append({"node": d, "type": "main", "index": 0})

    def to_json(self):
        for s, d, out_index in self._pending:
            assert d in self._map, (s, d)
            self._wire(s, d, out_index)
        self._pending = []
        return {
            "name": self.name,
            "nodes": self.nodes,
            "connections": self.connections,
            "settings": {"executionOrder": "v1"},
        }

    def out(self, outdir):
        fn = os.path.join(outdir, self.name + ".json")
        with open(fn, "w") as f:
            json.dump(self.to_json(), f, indent=2, ensure_ascii=False)
        return fn


class Cfg:
    def __init__(self, cfg):
        self.wf_ids = cfg.get("workflow_ids", {})
        self.n8n = cfg["n8n_base"]
        self.adapter = cfg["adapter_base"]
        self.webhook = cfg["webhook_base"]
        self.runs = cfg["tables"]["runs"]
        self.attempts = cfg["tables"]["attempts"]
        self.cr_n8n = cfg["creds"]["n8n_api"]
        self.cr_harness = cfg["creds"]["harness_token"]
        self.cr_api = cfg["creds"]["api_auth"]

    def rows(self, table):
        return "%s/api/v1/data-tables/%s/rows" % (self.n8n, table)

    def jobs(self):
        return self.adapter + "/v1/jobs"

    def wfid(self, name):
        return self.wf_ids.get(name, "PENDING_" + name)

    def batches(self):
        return self.adapter + "/v1/batches"


def dt_filter(filters):
    return urllib.parse.quote(json.dumps(filters, separators=(",", ":")))


RUN_UPDATE_TMPL = """const s = $json;
const row = s.run_row || {};
row.run_id = s.issue.run_id;
row.state = '%s';
row.current_job = '%s';
%s
row.updated_at = new Date().toISOString();
return [{json: {
  filter: {filters: [{columnName: 'run_id', condition: 'eq', value: s.issue.run_id}]},
  data: row, returnData: true}}];"""


def state_update_nodes(wf, cfg, name_prefix, state, current_job, extra_fields, pos):
    js = (
        "const s = $json;\nconst row = Object.assign({}, s.run_row || {});\n"
        "row.run_id = s.issue.run_id;\nrow.state = '%s';\nrow.current_job = '%s';\n%s\n"
        "row.updated_at = new Date().toISOString();\n"
        "return [{json: {filter: {filters: [{columnName: 'run_id', condition: 'eq', "
        "value: s.issue.run_id}]}, data: row, returnData: true, state: s}}];"
        % (state, current_job, extra_fields)
    )
    c = code_node(name_prefix + " Prep", js, pos)
    h = http_node(
        name_prefix + " Update",
        "POST",
        cfg.rows(cfg.runs) + "/upsert",
        "JSON.stringify($json)",
        (pos[0] + 1, pos[1]),
        cfg.cr_n8n,
    )
    r = code_node(
        name_prefix + " Restore",
        "const s = $('%s Prep').first().json.state || {};\nreturn [{json: s}];"
        % name_prefix,
        (pos[0] + 2, pos[1]),
    )
    wf.add_node(c)
    wf.add_node(h)
    wf.add_node(r)
    wf.add(c, h)
    wf.add(h, r)
    return c, h, r


def attempts_insert_nodes(wf, cfg, name_prefix, pos):
    js = """const s = $json;
const rec = s.job_record || s.build_job || {};
return [{json: {state: s, data: [{
  run_id: s.issue.run_id,
  job_id: rec.job_id || '',
  attempt_id: rec.attempt_id || '',
  status: rec.status || '',
  input_contract: rec.input_contract || '',
  input_fingerprint: rec.input_fingerprint || '',
  output_contract: rec.output_contract || '',
  output_fingerprint: rec.output_fingerprint || '',
  provider: rec.provider || '',
  model: rec.model || '',
  started_at: rec.started_at || '',
  ended_at: rec.ended_at || '',
  failure_signature: rec.failure_signature || '',
  strategy_delta: rec.strategy_delta || '',
  result_ref: rec.result_ref || ''
}], returnType: 'all'}}];"""
    c = code_node(name_prefix + " Prep Attempt", js, pos)
    h = http_node(
        name_prefix + " Insert Attempt",
        "POST",
        cfg.rows(cfg.attempts),
        "JSON.stringify($json)",
        (pos[0] + 1, pos[1]),
        cfg.cr_n8n,
    )
    r = code_node(
        name_prefix + " Attempt Restore",
        "const s = $('%s Prep Attempt').first().json.state || {};\nreturn [{json: s}];"
        % name_prefix,
        (pos[0] + 2, pos[1]),
    )
    wf.add_node(c)
    wf.add_node(h)
    wf.add_node(r)
    wf.add(c, h)
    wf.add(h, r)
    return c, h, r


def artifact_store_nodes(wf, cfg, name_prefix, artifact_expr, pos):
    js = (
        """const s = $json;
return [{json: {artifact: %s}}];"""
        % artifact_expr
    )
    c = code_node(name_prefix + " Prep", js, pos)
    h = http_node(
        name_prefix + " Store",
        "POST",
        cfg.adapter + "/v1/artifacts/PLACEHOLDER_RUN/PLACEHOLDER_NAME",
        "JSON.stringify($json)",
        (pos[0] + 1, pos[1]),
        cfg.cr_harness,
        params_extra={
            "url": "={{ cfg.adapter }}/v1/artifacts/{{ $json.issue.run_id }}/{{ name }}".replace(
                "cfg.adapter", cfg.adapter
            ).replace("{{ name }}", name_prefix.lower().split(" ")[-1])
        },
    )
    wf.add_node(c)
    wf.add_node(h)
    return c, h


def dispatch_job_nodes(
    wf,
    cfg,
    name_prefix,
    job_type,
    input_expr,
    attempt_expr,
    job_id_expr,
    fixture_expr,
    backend_expr,
    pos,
):
    js = """const s = $json;
const input = %s;
return [{json: {
  run_id: s.issue.run_id,
  job_id: %s,
  job_type: '%s',
  attempt_id: %s,
  input_contract: 'autodev.issue.v1',
  input: input,
  backend: %s,
  fixture: %s
}}];""" % (input_expr, job_id_expr, job_type, attempt_expr, backend_expr, fixture_expr)
    c = code_node(name_prefix + " Prep", js, pos)
    h = http_node(
        name_prefix + " Dispatch",
        "POST",
        cfg.jobs(),
        "JSON.stringify($json)",
        (pos[0] + 1, pos[1]),
        cfg.cr_harness,
    )
    wf.add_node(c)
    wf.add_node(h)
    return c, h
    c = code_node(name_prefix + " Prep", js, pos)
    h = http_node(
        name_prefix + " Dispatch",
        "POST",
        cfg.jobs(),
        "JSON.stringify($json)",
        (pos[0] + 1, pos[1]),
        cfg.cr_harness,
    )
    wf.add_node(c)
    wf.add_node(h)
    return c, h


def hamh_passthrough_js(task_class):
    """HAMH identity passthrough (ADR H15/AC-17): provider/model/
    model_revision/task_class travel with the job dispatch. Backend routing
    is untouched."""
    return (
        "  provider: (s.provider || null),\n"
        "  model: (s.model || null),\n"
        "  model_revision: (s.model_revision || null),\n"
        "  task_class: '%s'" % task_class
    )


def poll_cycle(wf, cfg, name_prefix, get_url_expr, status_field, completed_value, pos):
    """Wait -> poll -> parse -> IF completed / IF failed / loop with limit.
    Returns the parse-code node name (data: job/batch view)."""
    w = wait_node(name_prefix + " Wait", 5, pos)
    poll = http_node(
        name_prefix + " Poll",
        "GET",
        get_url_expr,
        "{}",
        (pos[0] + 1, pos[1]),
        cfg.cr_harness,
        send_body=False,
        params_extra={"url": get_url_expr},
    )
    parse = code_node(
        name_prefix + " Parse",
        """const raw = $json;
const d = (raw && raw.data) ? raw.data : raw;
return [{json: d}];""",
        (pos[0] + 2, pos[1]),
    )
    ifc = str_if(
        name_prefix + " Done?",
        "$json." + status_field,
        completed_value,
        (pos[0] + 3, pos[1]),
    )
    iff = str_if(
        name_prefix + " Failed?",
        "$json." + status_field,
        "failed",
        (pos[0] + 4, pos[1]),
    )
    inc = code_node(
        name_prefix + " Incr",
        """const s = $json;
return [{json: Object.assign({}, s, {polls: (s.polls || 0) + 1})}];""",
        (pos[0] + 5, pos[1]),
    )
    lim = num_if(
        name_prefix + " Limit?", "$json.polls", "gte", 40, (pos[0] + 6, pos[1])
    )
    to = code_node(
        name_prefix + " Timeout",
        """const s = $json;
return [{json: Object.assign({}, s, {ok: false, failure_class: 'TIMEOUT',
  failure_signature: 'POLL_TIMEOUT', error: 'poll limit reached'})}];""",
        (pos[0] + 7, pos[1]),
    )
    for n in (w, poll, parse, ifc, iff, inc, lim, to):
        wf.add_node(n)
    wf.add(w, poll)
    wf.add(poll, parse)
    wf.add(parse, ifc)
    wf.add(ifc, "RESUME_" + name_prefix, 0)  # completed -> downstream hook
    wf.add(ifc, iff, 1)  # not completed -> failed?
    wf.add(iff, "FAIL_" + name_prefix, 0)  # failed -> downstream hook
    wf.add(iff, inc, 1)  # still running -> incr
    wf.add(inc, lim)
    wf.add(lim, w, 1)  # under limit -> loop
    wf.add(lim, to, 0)  # limit reached -> timeout
    return parse["name"], ifc["name"], iff["name"]


# ============================================================ 00 API Start ==
def build_00(cfg):
    wf = WF("00 AutoDev API Start")
    P = lambda x, y: [x * 240, y * 160]  # noqa: E731
    wf.add_node(
        webhook_node("Start Webhook", "autodev/start", "POST", cfg.cr_api, P(0, 0))
    )
    validate_js = (
        """const raw = $json.body || $json;
const task = raw.task && typeof raw.task === 'object' ? raw.task : raw;
const now = new Date();
const runId = 'run-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
const issue = {
  contract: 'autodev.issue.v1', version: 'v1', run_id: runId,
  task_ref: task.task_ref || '', repository_ref: task.repository_ref || '',
  workspace: task.workspace || 'autodev-v2',
  task_description: task.task_description || '',
  acceptance_hint: task.acceptance_hint || '',
  max_attempts: task.max_attempts || 2,
  created_at: now.toISOString(),
  trace_id: 'trace-' + runId, source: 'autodev-start-api',
};
"""
        + JS_VALIDATOR
        + """
const schema = %s;
const v = validateAutodevContract(issue, schema);
const fixture = (raw.fixture && ['invalid_plan','verify_fail_delta','verify_fail_no_delta','no_signature','attempt_limit','security_critical_blocking','review_fix','review_split'].includes(raw.fixture)) ? raw.fixture : null;
const backend = (raw.backend === 'embedded' || raw.backend === 'opencode-builder-8001') ? raw.backend : 'opencode-builder-8001';
const provider = (typeof raw.provider === 'string' && ['embedded','lmstudio','groq','openrouter','ollama'].includes(raw.provider)) ? raw.provider : null;
const model = (typeof raw.model === 'string' && raw.model.length <= 64) ? raw.model : null;
const modelRevision = (typeof raw.model_revision === 'string' && raw.model_revision.length <= 64) ? raw.model_revision : null;
const deepseekRequested = /deepseek/i.test(String(raw.provider || '')) || /deepseek/i.test(String(raw.model || ''));
const intakeErrors = deepseekRequested ? v.errors.concat(['DEEPSEEK_RETIRED']) : v.errors;
return [{ json: { intake_valid: v.ok && !deepseekRequested, errors: intakeErrors, issue: issue,
  fixture: fixture, backend: backend, provider: provider, model: model,
  model_revision: modelRevision, run_id: runId } }];
"""
        % embed_schema("autodev.issue.v1")
    )
    wf.add_node(code_node("Validate Intake", validate_js, P(1, 0)))
    wf.add_node(bool_if("Intake Valid?", "$json.intake_valid", P(2, 0)))
    wf.add_node(
        respond_node(
            "Respond 400",
            P(3, -1),
            "={{ JSON.stringify({ status: 'error', code: 'INTAKE_INVALID', run_id: $json.run_id, errors: $json.errors }) }}",
        )
    )
    wf.add_node(
        code_node(
            "Prepare Run Row",
            """const s = $json;
return [{json: {intake: {issue: s.issue, fixture: s.fixture, backend: s.backend,
  provider: s.provider || null, model: s.model || null,
  model_revision: s.model_revision || null},
  data: [{run_id: s.issue.run_id, state: 'ACCEPTED', task_ref: s.issue.task_ref || '',
  repository_ref: s.issue.repository_ref || '', current_job: 'intake', decision: '',
  reason_code: 'INTAKE_OK', created_at: s.issue.created_at, updated_at: s.issue.created_at,
  result_ref: '', trace_id: s.issue.trace_id || '', backend: s.backend}], returnType: 'all'}}];""",
            P(2, 1),
        )
    )
    wf.add_node(
        http_node(
            "Insert Run Row",
            "POST",
            cfg.rows(cfg.runs),
            "JSON.stringify($json)",
            P(3, 1),
            cfg.cr_n8n,
        )
    )
    wf.add_node(
        respond_node(
            "Respond 202",
            P(4, 0),
            "={{ JSON.stringify({ run_id: $json.run_id, status: 'ACCEPTED', status_url: '"
            + cfg.webhook
            + "/webhook/autodev/status?run_id=' + $json.run_id }) }}",
        )
    )
    wf.add_node(
        execute_wf_node(
            cfg,
            "Run Orchestrator",
            "01 AutoDev Orchestrator",
            P(5, 0),
            {"executeOnce": True},
        )
    )
    wf.add("Start Webhook", "Validate Intake")
    wf.add("Validate Intake", "Intake Valid?")
    wf.add("Intake Valid?", "Respond 400", 1)
    wf.add("Intake Valid?", "Prepare Run Row", 0)
    wf.add_node(
        code_node(
            "Pass Intake",
            """const s = $json;
const intake = $('Prepare Run Row').first().json.intake || {};
const row = (s.data && s.data[0]) || {};
return [{json: Object.assign({}, intake, {run_row: row,
  run_id: intake.issue ? intake.issue.run_id : row.run_id})}];""",
            P(4, 0),
        )
    )
    wf.add("Prepare Run Row", "Insert Run Row")
    wf.add("Insert Run Row", "Pass Intake")
    wf.add("Pass Intake", "Respond 202")
    wf.add("Pass Intake", "Run Orchestrator")
    return wf


# ============================================================ 02 API Status ==
def build_02(cfg):
    wf = WF("02 AutoDev API Status")
    P = lambda x, y: [x * 240, y * 160]  # noqa: E731
    wf.add_node(
        webhook_node("Status Webhook", "autodev/status", "GET", cfg.cr_api, P(0, 0))
    )
    wf.add_node(
        code_node(
            "Parse Query",
            """const runId = String(($json.query && $json.query.run_id) || '').trim();
if (!runId) return [{json: {run_id: '', found: false, error: 'MISSING_RUN_ID'}}];
const filter = JSON.stringify({filters: [{columnName: 'run_id', condition: 'eq', value: runId}]});
return [{json: {run_id: runId, filter_raw: filter}}];""",
            P(1, 0),
        )
    )
    wf.add_node(
        http_node(
            "Fetch Run Row",
            "GET",
            cfg.rows(cfg.runs),
            "{}",
            P(2, 0),
            cfg.cr_n8n,
            send_body=False,
            params_extra={
                "url": cfg.rows(cfg.runs),
                "sendQuery": True,
                "queryParameters": {
                    "parameters": [
                        {"name": "filter", "value": "={{ $json.filter_raw }}"}
                    ]
                },
            },
        )
    )
    wf.add_node(
        code_node(
            "Check Run Found",
            """const rows = ($json.data || []);
const runId = $('Parse Query').first().json.run_id || '';
if (!rows.length) return [{json: {run_id: runId, found: false, row: null}}];
return [{json: {run_id: runId, found: true, row: rows[0]}}];""",
            P(3, 0),
        )
    )
    wf.add_node(bool_if("Run Found?", "$json.found", P(4, 0)))
    wf.add_node(
        respond_node(
            "Respond 404",
            P(5, -1),
            "={{ JSON.stringify({ status: 'error', code: 'RUN_NOT_FOUND', run_id: $json.run_id }) }}",
        )
    )
    wf.add_node(
        code_node(
            "Prep Attempt Query",
            """const s = $json;
const filter = JSON.stringify({filters: [{columnName: 'run_id', condition: 'eq', value: s.run_id}]});
return [{json: {run_id: s.run_id, row: s.row, filter_raw: filter}}];""",
            P(4, 1),
        )
    )
    wf.add_node(
        http_node(
            "Fetch Attempt Count",
            "GET",
            cfg.rows(cfg.attempts),
            "{}",
            P(5, 1),
            cfg.cr_n8n,
            send_body=False,
            params_extra={
                "url": cfg.rows(cfg.attempts),
                "sendQuery": True,
                "queryParameters": {
                    "parameters": [
                        {"name": "filter", "value": "={{ $json.filter_raw }}"}
                    ]
                },
            },
        )
    )
    wf.add_node(
        code_node(
            "Build Status",
            """const row = $('Prep Attempt Query').first().json.row || {};
const attempts = ($json.data || []).length;
return [{json: {
  run_id: row.run_id, state: row.state, current_job: row.current_job || '',
  attempt: attempts, decision: row.decision || null, reason_code: row.reason_code || null,
  result_ref: row.result_ref || null, updated_at: row.updated_at || null
}}];""",
            P(6, 1),
        )
    )
    wf.add_node(respond_node("Respond 200", P(7, 1)))
    wf.add("Status Webhook", "Parse Query")
    wf.add("Parse Query", "Fetch Run Row")
    wf.add("Fetch Run Row", "Check Run Found")
    wf.add("Check Run Found", "Run Found?")
    wf.add("Run Found?", "Respond 404", 1)
    wf.add("Run Found?", "Prep Attempt Query", 0)
    wf.add("Prep Attempt Query", "Fetch Attempt Count")
    wf.add("Fetch Attempt Count", "Build Status")
    wf.add("Build Status", "Respond 200")
    return wf


# ============================================================ 01 Orchestrator
def build_01(cfg):
    wf = WF("01 AutoDev Orchestrator")
    P = lambda x, y: [x * 240, y * 160]  # noqa: E731

    wf.add_node(
        node(
            "Sub-Workflow Trigger",
            "n8n-nodes-base.executeWorkflowTrigger",
            {},
            P(-1, 0),
            1,
        )
    )
    wf.add_node(
        code_node(
            "Init Run State",
            """const s = $json;
const issue = s.issue || s;
return [{json: {
  issue: issue, fixture: s.fixture || null,
  backend: s.backend || 'opencode-builder-8001',
  provider: s.provider || null,
  model: s.model || null,
  model_revision: s.model_revision || null,
  run_row: {state: 'ACCEPTED', current_job: 'baseline', reason_code: 'INTAKE_OK'},
  baseline: null, research: null, plan: null, gate: null,
  build: null, verification: null, review: null, decision: null,
  attempt_build: 0, attempt_fix: 0,
  max_attempts: issue.max_attempts || 2
}}];""",
            P(0, 0),
        )
    )
    wf.add("Sub-Workflow Trigger", "Init Run State")

    # BASELINE phase
    c, h, r = state_update_nodes(
        wf,
        cfg,
        "Baseline State",
        "BASELINING",
        "baseline",
        "row.reason_code = 'START_BASELINE';",
        P(1, 0),
    )
    wf.add("Init Run State", c)
    wf.add_node(
        execute_wf_node(
            cfg, "Run Baseline", "10 AutoDev Baseline", P(3, 0), {"executeOnce": True}
        )
    )
    wf.add(r, "Run Baseline")
    wf.add("Run Baseline", "Post-Baseline")
    wf.add_node(
        code_node(
            "Post-Baseline",
            """const out = $json;
const b = out.baseline || {};
const s = Object.assign({}, $('Baseline State Prep').first().json.state || {}, {baseline: b});
return [{json: Object.assign({}, s, {baseline_ok: !!b.contract && b.ok !== false})}];""",
            P(4, 0),
        )
    )
    wf.add_node(bool_if("Baseline OK?", "$json.baseline_ok", P(5, 0)))
    # terminal FAILED helper
    term_failed = []
    c, h, r = state_update_nodes(
        wf,
        cfg,
        "Baseline Failed",
        "FAILED",
        "baseline",
        "row.decision = 'BLOCKED'; row.reason_code = 'BASELINE_FAILED';",
        P(6, 0),
    )
    term_failed.append((c, h))
    wf.add("Baseline OK?", c, 1)

    # RESEARCH phase
    c, h, r = state_update_nodes(
        wf,
        cfg,
        "Research State",
        "RESEARCHING",
        "research",
        "row.reason_code = 'BASELINE_OK';",
        P(6, 0),
    )
    wf.add("Baseline OK?", c, 0)
    wf.add_node(
        execute_wf_node(
            cfg,
            "Run Research",
            "20 AutoDev Research Batch",
            P(8, 0),
            {"executeOnce": True},
        )
    )
    wf.add(r, "Run Research")
    wf.add("Run Research", "Post-Research")
    wf.add_node(
        code_node(
            "Post-Research",
            """const out = $json;
const r = out.research || {};
const s = Object.assign({}, $('Research State Prep').first().json.state || {}, {research: r});
return [{json: Object.assign({}, s, {research_ok: !!r.contract && r.ok !== false})}];""",
            P(9, 0),
        )
    )
    wf.add_node(bool_if("Research OK?", "$json.research_ok", P(10, 0)))
    c, h, r = state_update_nodes(
        wf,
        cfg,
        "Research Failed",
        "FAILED",
        "research",
        "row.decision = 'BLOCKED'; row.reason_code = 'RESEARCH_FAILED';",
        P(11, 0),
    )
    wf.add("Research OK?", c, 1)

    # PLAN phase
    c, h, r = state_update_nodes(
        wf,
        cfg,
        "Plan State",
        "PLANNING",
        "plan",
        "row.reason_code = 'RESEARCH_OK';",
        P(11, 0),
    )
    wf.add("Research OK?", c, 0)
    wf.add_node(
        execute_wf_node(
            cfg, "Run Plan", "30 AutoDev Plan", P(13, 0), {"executeOnce": True}
        )
    )
    wf.add(r, "Run Plan")
    wf.add("Run Plan", "Post-Plan")
    wf.add_node(
        code_node(
            "Post-Plan",
            """const out = $json;
const s = Object.assign({}, $('Plan State Prep').first().json.state || {});
const baseline = s.baseline || {};
const failure = out.failure_class ? {
  failure_class: out.failure_class,
  failure_signature: out.failure_signature || null,
  error: out.error || null,
  job_record: out.job_record || {}
} : null;
return [{json: Object.assign({}, s, {
  plan: out.plan || null,
  plan_fingerprint: out.plan_fingerprint || '',
  plan_job: out.job_record || {},
  plan_failure: failure,
  baseline_head: (baseline.repository && baseline.repository.head) || '',
  gate: out.gate || (failure
    ? {status: 'BLOCKED', reason_code: failure.failure_class,
       failure_signature: failure.failure_signature, error: failure.error}
    : {status: 'BLOCKED', reason_code: 'PLAN_MISSING'})})}];""",
            P(14, 0),
        )
    )
    wf.add_node(str_if("Plan Gate?", "$json.gate.status", "APPROVED", P(15, 0)))
    c, h, r = state_update_nodes(
        wf,
        cfg,
        "Plan Blocked",
        "PLAN_BLOCKED",
        "plan",
        "row.decision = 'BLOCKED'; row.reason_code = $json.gate.reason_code || 'PLAN_REJECTED';",
        P(16, 0),
    )
    wf.add("Plan Gate?", c, 1)
    wf.add_node(
        code_node(
            "Plan Blocked Artifact",
            """const s = $json;
return [{json: {artifact: {contract: 'autodev.decision.v1', version: 'v1',
  run_id: s.issue.run_id, decision: 'BLOCKED',
  reason_code: s.gate.reason_code || 'PLAN_REJECTED', next: 'terminal',
  evidence: {verification_ref: '', review_ref: ''}}}}];""",
            P(17, 0),
        )
    )
    wf.add(r, "Plan Blocked Artifact")
    wf.add_node(
        http_node(
            "Store Plan Blocked",
            "POST",
            cfg.adapter + "/v1/artifacts/{{ $json.artifact.run_id }}/decision",
            "JSON.stringify($json)",
            P(18, 0),
            cfg.cr_harness,
        )
    )
    wf.add("Plan Blocked Artifact", "Store Plan Blocked")

    # BUILD phase
    c, h, r = state_update_nodes(
        wf,
        cfg,
        "Build State",
        "BUILDING",
        "build",
        "row.reason_code = 'PLAN_GATE_APPROVED';",
        P(16, 0),
    )
    wf.add("Plan Gate?", c, 0)
    wf.add_node(
        execute_wf_node(
            cfg, "Run Build", "40 AutoDev Build", P(18, 0), {"executeOnce": True}
        )
    )
    wf.add(r, "Run Build")
    wf.add("Run Build", "Post-Build")
    wf.add_node(
        code_node(
            "Post-Build",
            """const out = $json;
const b = out.build_result || {};
const s = Object.assign({}, $('Build State Prep').first().json.state || {});
return [{json: Object.assign({}, s, {
  build: b, build_job: b.job_record || {},
  build_ok: !!b && !!b.contract && b.status === 'success',
  attempt_build: (s.attempt_build || 0) + 1})}];""",
            P(19, 0),
        )
    )
    wf.add_node(bool_if("Build OK?", "$json.build_ok", P(20, 0)))
    c, h, r = state_update_nodes(
        wf,
        cfg,
        "Build Failed",
        "FAILED",
        "build",
        "row.decision = 'BLOCKED'; row.reason_code = 'BUILD_FAILED';",
        P(21, 0),
    )
    wf.add("Build OK?", c, 1)
    # attempt record for the build
    c, h, r = attempts_insert_nodes(wf, cfg, "Build Attempt", P(21, 0))
    wf.add("Build OK?", c, 0)

    # VERIFY phase
    verify_state_c, verify_state_h, verify_state_r = state_update_nodes(
        wf,
        cfg,
        "Verify State",
        "VERIFYING",
        "verify",
        "row.reason_code = 'BUILD_PASSED';",
        P(22, 0),
    )
    wf.add(r, verify_state_c)
    wf.add_node(
        execute_wf_node(
            cfg, "Run Verify", "50 AutoDev Verify", P(23, 0), {"executeOnce": True}
        )
    )
    wf.add(verify_state_r, "Run Verify")

    wf.add("Run Verify", "Post-Verify")
    wf.add_node(
        code_node(
            "Post-Verify",
            """const out = $json;
const v = out.verification || {};
// the state flows through the restore that ran directly before Run Verify
// (candidates: decision-fix loop, retry-fix loop, happy path)
let srcState = {};
try {
  const d = $('Decision Fix Attempt Attempt Restore');
  if (d && d.first) srcState = d.first().json;
} catch (e) { /* node not executed in this run */ }
if (!srcState || !srcState.issue) {
  try {
    const f = $('Fix Attempt Attempt Restore');
    if (f && f.first) srcState = f.first().json;
  } catch (e) { /* node not executed in this run */ }
}
if (!srcState || !srcState.issue) {
  try {
    const b = $('Build Attempt Attempt Restore');
    if (b && b.first) srcState = b.first().json;
  } catch (e) { /* node not executed in this run */ }
}
const s = Object.assign({}, srcState);
return [{json: Object.assign({}, s, {
  verification: v, verify_job: out.job_record || {},
  verify_ok: !!v && !!v.contract && v.passed === true})}];""",
            P(24, 0),
        )
    )
    wf.add_node(
        bool_if(
            "Verify Passed?",
            "$json.verification && $json.verification.passed === true",
            P(25, 0),
        )
    )

    # ---- verify FAILED -> retry policy
    retry_js = """const s = $json;
const v = s.verification || {};
const attempts = (s.attempt_build || 0) + (s.attempt_fix || 0);
const maxAttempts = s.max_attempts || 2;
let retry = null;
if (!v.failure_signature) {
  retry = {decision: 'SPLIT', reason_code: 'RETRY_DENIED_NO_FAILURE_SIGNATURE'};
} else if (attempts >= maxAttempts) {
  retry = {decision: 'SPLIT', reason_code: 'RETRY_DENIED_ATTEMPT_LIMIT'};
} else if (!v.new_evidence || !v.new_evidence.length) {
  retry = {decision: 'SPLIT', reason_code: 'RETRY_DENIED_NO_STRATEGY_DELTA'};
} else {
  retry = {decision: 'FIX', reason_code: 'VERIFY_FAILED_WITH_DELTA'};
}
return [{json: Object.assign({}, s, {retry: retry})}];"""
    wf.add_node(code_node("Retry Policy", retry_js, P(26, 0)))
    wf.add("Verify Passed?", "Retry Policy", 1)
    wf.add_node(str_if("Retry FIX?", "$json.retry.decision", "FIX", P(27, 0)))
    wf.add_node(str_if("Retry SPLIT?", "$json.retry.decision", "SPLIT", P(28, 0)))

    # FIX path
    c, h, r = state_update_nodes(
        wf,
        cfg,
        "Fix State",
        "FIX_REQUIRED",
        "fix",
        "row.decision = 'FIX'; row.reason_code = $json.retry.reason_code || 'VERIFY_FAILED_WITH_DELTA';",
        P(29, 0),
    )
    wf.add("Retry FIX?", c, 0)
    wf.add("Retry FIX?", "Retry SPLIT?", 1)
    wf.add_node(
        execute_wf_node(
            cfg, "Run Fix", "80 AutoDev Fix", P(31, 0), {"executeOnce": True}
        )
    )
    wf.add(r, "Run Fix")
    wf.add("Run Fix", "Post-Fix")
    wf.add_node(
        code_node(
            "Post-Fix",
            """const out = $json;
const b = out.build_result || {};
const s = Object.assign({}, $('Fix State Prep').first().json.state || {});
return [{json: Object.assign({}, s, {
  build: b, build_job: b.job_record || {},
  build_ok: !!b && !!b.contract && b.status === 'success',
  attempt_fix: (s.attempt_fix || 0) + 1})}];""",
            P(32, 0),
        )
    )
    wf.add_node(bool_if("Fix OK?", "$json.build_ok", P(33, 0)))
    c, h, r = state_update_nodes(
        wf,
        cfg,
        "Fix Failed",
        "FAILED",
        "fix",
        "row.decision = 'BLOCKED'; row.reason_code = 'FIX_FAILED';",
        P(34, 0),
    )
    wf.add("Fix OK?", c, 1)
    c, h, r = attempts_insert_nodes(wf, cfg, "Fix Attempt", P(34, 0))
    wf.add("Fix OK?", c, 0)
    # loop: fix attempt -> verify again
    wf.add(r, verify_state_c)

    # SPLIT path (retry policy)
    wf.add_node(
        execute_wf_node(
            cfg,
            "Run Split (Retry)",
            "90 AutoDev Split",
            P(29, 1),
            {"executeOnce": True},
        )
    )
    wf.add("Retry SPLIT?", "Run Split (Retry)", 0)
    wf.add_node(
        code_node(
            "Post-Split (Retry)",
            """const out = $json;
const sp = out.split || {};
const s = Object.assign({}, $('Retry Policy').first().json || {});
return [{json: Object.assign({}, s, {split: sp, split_ok: !!sp && !!sp.contract})}];""",
            P(30, 1),
        )
    )
    wf.add("Run Split (Retry)", "Post-Split (Retry)")
    c, h, r = state_update_nodes(
        wf,
        cfg,
        "Split Retry State",
        "SPLIT_REQUIRED",
        "split",
        "row.decision = 'SPLIT'; row.reason_code = $json.split.reason_code || 'SPLIT_REQUIRED';",
        P(31, 1),
    )
    wf.add("Post-Split (Retry)", c)
    wf.add(c, h)

    # BLOCKED path (retry policy; neither FIX nor SPLIT)
    c, h, r = state_update_nodes(
        wf,
        cfg,
        "Retry Blocked",
        "BLOCKED",
        "decision",
        "row.decision = 'BLOCKED'; row.reason_code = $json.retry.reason_code || 'RETRY_DENIED';",
        P(30, 1),
    )
    wf.add("Retry SPLIT?", c, 1)

    # ---- verify PASSED -> REVIEW phase
    c, h, r = state_update_nodes(
        wf,
        cfg,
        "Review State",
        "REVIEWING",
        "review",
        "row.reason_code = 'VERIFY_PASSED';",
        P(25, 1),
    )
    wf.add("Verify Passed?", c, 0)
    wf.add_node(
        execute_wf_node(
            cfg,
            "Run Review",
            "60 AutoDev Review Batch",
            P(27, 1),
            {"executeOnce": True},
        )
    )
    wf.add(r, "Run Review")
    wf.add("Run Review", "Post-Review")
    wf.add_node(
        code_node(
            "Post-Review",
            """const out = $json;
const r = out.review || {};
const s = Object.assign({}, $('Review State Prep').first().json.state || {});
return [{json: Object.assign({}, s, {
  review: r, review_ok: !!r && !!r.contract})}];""",
            P(28, 1),
        )
    )
    wf.add_node(
        bool_if(
            "Security Blocked?",
            "$json.review && $json.review.blocked === true",
            P(29, 1),
        )
    )
    c, h, r = state_update_nodes(
        wf,
        cfg,
        "Security Blocked",
        "BLOCKED",
        "review",
        "row.decision = 'BLOCKED'; row.reason_code = 'BLOCKING_HIGH_OR_CRITICAL_FINDING';",
        P(30, 1),
    )
    wf.add("Security Blocked?", c, 0)

    # DECISION phase
    decision_state_c, decision_state_h, decision_state_r = state_update_nodes(
        wf,
        cfg,
        "Decision State",
        "DECIDING",
        "decision",
        "row.reason_code = 'REVIEW_PASSED';",
        P(30, 2),
    )
    wf.add("Security Blocked?", decision_state_c, 1)
    wf.add_node(
        execute_wf_node(
            cfg, "Run Decision", "70 AutoDev Decision", P(30, 2), {"executeOnce": True}
        )
    )
    wf.add(decision_state_r, "Run Decision")
    wf.add("Run Decision", "Post-Decision")
    wf.add_node(
        code_node(
            "Post-Decision",
            """const out = $json;
const d = out.decision_contract || {};
const s = Object.assign({}, $('Review State Prep').first().json.state || {});
return [{json: Object.assign({}, s, {decision: d || null})}];""",
            P(31, 2),
        )
    )
    wf.add_node(
        code_node(
            "Decision Retry Guard",
            """const s = $json;
const d = Object.assign({}, s.decision || {});
const attempts = (s.attempt_build || 0) + (s.attempt_fix || 0);
const maxAttempts = s.max_attempts || 2;
if (d.decision === 'FIX' && attempts >= maxAttempts) {
  d.decision = 'BLOCKED';
  d.reason_code = 'RETRY_DENIED_ATTEMPT_LIMIT';
}
return [{json: Object.assign({}, s, {decision: d})}];""",
            P(31, 3),
        )
    )
    wf.add_node(
        str_if(
            "Decision DONE?",
            "$json.decision && $json.decision.decision",
            "DONE",
            P(32, 2),
        )
    )
    wf.add_node(
        str_if(
            "Decision FIX?",
            "$json.decision && $json.decision.decision",
            "FIX",
            P(33, 2),
        )
    )
    wf.add_node(
        str_if(
            "Decision SPLIT?",
            "$json.decision && $json.decision.decision",
            "SPLIT",
            P(34, 2),
        )
    )

    # DONE terminal
    c, h, r = state_update_nodes(
        wf,
        cfg,
        "Done State",
        "DONE",
        "terminal",
        "row.decision = 'DONE'; row.reason_code = 'ALL_HARD_GATES_GREEN'; row.result_ref = $json.decision ? ($json.decision.evidence ? $json.decision.evidence.review_ref : '') : '';",
        P(35, 2),
    )
    wf.add("Decision DONE?", c, 0)
    wf.add("Decision DONE?", "Decision FIX?", 1)

    # FIX from decision -> loop to fix path
    c2, h2, r = state_update_nodes(
        wf,
        cfg,
        "Decision Fix State",
        "FIX_REQUIRED",
        "fix",
        "row.decision = 'FIX'; row.reason_code = $json.decision.reason_code || 'NON_BLOCKING_REVIEW_FINDINGS';",
        P(33, 3),
    )
    wf.add("Decision FIX?", c2, 0)
    wf.add("Decision FIX?", "Decision SPLIT?", 1)
    wf.add_node(
        execute_wf_node(
            cfg, "Run Fix (Decision)", "80 AutoDev Fix", P(35, 3), {"executeOnce": True}
        )
    )
    wf.add(r, "Run Fix (Decision)")
    wf.add("Run Fix (Decision)", "Post-Fix (Decision)")
    wf.add_node(
        code_node(
            "Post-Fix (Decision)",
            """const out = $json;
const b = out.build_result || {};
const s = Object.assign({}, $('Decision Fix State Prep').first().json.state || {});
return [{json: Object.assign({}, s, {
  build: b, build_job: b.job_record || {},
  build_ok: !!b && !!b.contract && b.status === 'success',
  attempt_fix: (s.attempt_fix || 0) + 1})}];""",
            P(36, 3),
        )
    )
    wf.add_node(bool_if("Fix OK? (Decision)", "$json.build_ok", P(37, 3)))
    c3, h3, r = state_update_nodes(
        wf,
        cfg,
        "Decision Fix Failed",
        "FAILED",
        "fix",
        "row.decision = 'BLOCKED'; row.reason_code = 'FIX_FAILED';",
        P(38, 3),
    )
    wf.add("Fix OK? (Decision)", c3, 1)
    c4, h4, r = attempts_insert_nodes(wf, cfg, "Decision Fix Attempt", P(38, 3))
    wf.add("Fix OK? (Decision)", c4, 0)
    wf.add(r, verify_state_c)  # re-verify after decision fix

    # SPLIT from decision
    wf.add_node(
        execute_wf_node(
            cfg,
            "Run Split (Decision)",
            "90 AutoDev Split",
            P(35, 4),
            {"executeOnce": True},
        )
    )
    wf.add("Decision SPLIT?", "Run Split (Decision)", 0)
    wf.add_node(
        code_node(
            "Post-Split (Decision)",
            """const out = $json;
const sp = out.split || {};
const s = Object.assign({}, $('Post-Decision').first().json || {});
return [{json: Object.assign({}, s, {split: sp, split_ok: !!sp && !!sp.contract})}];""",
            P(36, 4),
        )
    )
    wf.add("Run Split (Decision)", "Post-Split (Decision)")
    c, h, r = state_update_nodes(
        wf,
        cfg,
        "Split Decision State",
        "SPLIT_REQUIRED",
        "split",
        "row.decision = 'SPLIT'; row.reason_code = $json.split.reason_code || 'SPLIT_REQUIRED';",
        P(37, 4),
    )
    wf.add("Post-Split (Decision)", c)
    wf.add(c, h)
    # BLOCKED from decision
    c5, h5, r = state_update_nodes(
        wf,
        cfg,
        "Decision Blocked",
        "BLOCKED",
        "terminal",
        "row.decision = 'BLOCKED'; row.reason_code = $json.decision.reason_code || 'DECISION_BLOCKED';",
        P(36, 4),
    )
    wf.add("Decision SPLIT?", c5, 1)

    # ---- ensure-wiring pass: add missing edges (idempotent)
    def ensure(src, dst, out_index=0):
        mains = wf.connections.get(src, {}).get("main", [])
        if any(dst in [e.get("node") for e in out] for out in mains):
            return
        wf.add(src, dst, out_index)

    ensure("Post-Baseline", "Baseline OK?")
    ensure("Post-Research", "Research OK?")
    ensure("Post-Plan", "Plan Gate?")
    ensure("Post-Build", "Build OK?")
    ensure("Post-Verify", "Verify Passed?")
    ensure("Post-Fix", "Fix OK?")
    ensure("Post-Fix (Decision)", "Fix OK? (Decision)")
    ensure("Post-Review", "Security Blocked?")
    ensure("Post-Decision", "Decision Retry Guard")
    ensure("Decision Retry Guard", "Decision DONE?")
    ensure("Retry Policy", "Retry FIX?")
    ensure("Run Baseline", "Post-Baseline")
    ensure("Run Research", "Post-Research")
    ensure("Run Plan", "Post-Plan")
    ensure("Run Build", "Post-Build")
    ensure("Run Verify", "Post-Verify")
    ensure("Run Review", "Post-Review")
    ensure("Run Decision", "Post-Decision")
    ensure("Run Fix", "Post-Fix")
    ensure("Run Fix (Decision)", "Post-Fix (Decision)")
    return wf


# ====================================================== single-job phases ==
def build_single_job_workflow(
    name,
    job_type,
    input_contract,
    input_expr,
    job_id_expr,
    attempt_expr,
    fixture_expr,
    backend_expr,
    validate_schema,
    out_key,
):
    def builder(cfg):
        wf = WF(name)
        P = lambda x, y: [x * 240, y * 160]  # noqa: E731
        wf.add_node(
            node(
                "Sub-Workflow Trigger",
                "n8n-nodes-base.executeWorkflowTrigger",
                {},
                P(-1, 0),
                1,
            )
        )
        wf.add("Sub-Workflow Trigger", "Prep %s" % job_type)
        _task_class = "plan" if job_type == "plan" else "baseline"
        prep_js = """const s = $json;
const input = %s;
return [{json: {
  run_id: s.issue.run_id, job_id: %s, job_type: '%s',
  attempt_id: %s, input_contract: '%s', input: input,
  backend: %s, fixture: %s,
  provider: (s.provider || null),
  model: (s.model || null),
  model_revision: (s.model_revision || null),
  task_class: '%s'
}}];""" % (
            input_expr,
            job_id_expr,
            job_type,
            attempt_expr,
            input_contract,
            backend_expr,
            fixture_expr,
            _task_class,
        )
        prep = code_node("Prep %s" % job_type, prep_js, P(0, 0))
        dispatch = http_node(
            "Dispatch %s" % job_type,
            "POST",
            cfg.jobs(),
            "JSON.stringify($json)",
            P(1, 0),
            cfg.cr_harness,
        )
        wf.add_node(prep)
        wf.add_node(dispatch)
        wf.add(prep, dispatch)

        w = wait_node("Wait", 5, P(2, 0))
        poll = http_node(
            "Poll",
            "GET",
            cfg.adapter
            + "/v1/jobs/{{ $json.data ? $json.data.job_id : $json.job_id }}",
            "{}",
            P(3, 0),
            cfg.cr_harness,
            send_body=False,
            params_extra={
                "url": cfg.adapter
                + "/v1/jobs/{{ $json.data ? $json.data.job_id : $json.job_id }}"
            },
        )
        parse = code_node(
            "Parse",
            """const raw = $json;
const d = (raw && raw.data) ? raw.data : raw;
return [{json: d}];""",
            P(4, 0),
        )
        done = str_if("Done?", "$json.status", "completed", P(5, 0))
        failed = str_if("Failed?", "$json.status", "failed", P(6, 0))
        inc = code_node(
            "Incr",
            """const s = $json;
return [{json: Object.assign({}, s, {polls: (s.polls || 0) + 1})}];""",
            P(7, 0),
        )
        lim = num_if("Limit?", "$json.polls", "gte", 40, P(8, 0))
        timeout = code_node(
            "Timeout",
            """const s = $json;
return [{json: {ok: false, failure_class: 'TIMEOUT',
  failure_signature: 'POLL_TIMEOUT', error: 'poll limit reached'}}];""",
            P(9, 0),
        )
        for n in (w, poll, parse, done, failed, inc, lim, timeout):
            wf.add_node(n)
        wf.add(dispatch, w)
        wf.add(w, poll)
        wf.add(poll, parse)
        wf.add(parse, done)
        wf.add(done, failed, 1)
        wf.add(failed, inc, 1)
        wf.add(inc, lim)
        wf.add(lim, w, 1)
        wf.add(lim, timeout, 0)

        # completed path: extract record + result -> validate -> output
        extract = code_node(
            "Extract %s" % job_type,
            """const s = $json;
const rec = s;
return [{json: {
  job_record: {
    job_id: rec.job_id, status: rec.status, job_type: rec.job_type,
    attempt_id: rec.attempt_id, backend: rec.backend, provider: rec.provider,
    model: rec.model, input_contract: rec.input_contract,
    input_fingerprint: rec.input_fingerprint,
    output_contract: rec.output_contract,
    output_fingerprint: rec.output_fingerprint,
    started_at: rec.started_at, ended_at: rec.ended_at,
    duration_ms: rec.duration_ms, failure_class: rec.failure_class,
    failure_signature: rec.failure_signature, strategy_delta: rec.strategy_delta,
    result_ref: rec.result_ref, error: rec.error
  },
  result: rec.result || null
}}];""",
            P(5, 1),
        )
        wf.add_node(extract)
        wf.add(done, extract, 0)

        # failed path
        fail = code_node(
            "Failed %s" % job_type,
            """const s = $json;
return [{json: {ok: false, failure_class: s.failure_class || 'UNKNOWN',
  failure_signature: s.failure_signature || null, error: s.error || null,
  job_record: {job_id: s.job_id, attempt_id: s.attempt_id, status: s.status,
    backend: s.backend, provider: s.provider, model: s.model,
    input_contract: s.input_contract, input_fingerprint: s.input_fingerprint,
    output_contract: s.output_contract, output_fingerprint: null,
    started_at: s.started_at, ended_at: s.ended_at, duration_ms: s.duration_ms,
    failure_class: s.failure_class, failure_signature: s.failure_signature,
    strategy_delta: s.strategy_delta, result_ref: s.result_ref, error: s.error}}}];""",
            P(6, 1),
        )
        wf.add_node(fail)
        wf.add(failed, fail, 0)

        # validate + output
        val_js = """const s = $json;
const result = s.result;
const schema = %s;
const v = validateAutodevContract(result, schema);
if (!v.ok) return [{json: {ok: false, failure_class: 'CONTRACT_FAILURE',
  failure_signature: 'CONTRACT_INVALID', error: v.errors.join(' | '),
  job_record: s.job_record}}];
return [{json: {ok: true, %s: result, job_record: s.job_record}}];""" % (
            embed_schema(validate_schema),
            out_key,
        )
        val = code_node("Validate %s" % job_type, JS_VALIDATOR + val_js, P(6, 2))
        wf.add_node(val)
        wf.add(extract, val)
        return wf

    return builder


# ======================================================== 10 AutoDev Baseline
def build_10(cfg):
    return build_single_job_workflow(
        "10 AutoDev Baseline",
        "baseline",
        "autodev.issue.v1",
        "s.issue",
        "s.issue.run_id + ':baseline:1'",
        "s.issue.run_id + ':baseline:1'",
        "s.fixture",
        "s.backend",
        "autodev.baseline.v1",
        "baseline",
    )(cfg)


# ============================================================ 30 AutoDev Plan
def build_30(cfg):
    plan_input = "Object.assign({}, s.issue, {'x-metadata': Object.assign({}, s.issue['x-metadata'] || {}, {research: s.research || null})})"
    wf = build_single_job_workflow(
        "30 AutoDev Plan",
        "plan",
        "autodev.issue.v1",
        plan_input,
        "s.issue.run_id + ':plan:1'",
        "s.issue.run_id + ':plan:1'",
        "s.fixture",
        "s.backend",
        "autodev.plan.v1",
        "plan",
    )(cfg)
    # append the deterministic plan gate after the validation node
    gate_js = """const s = $json;
const plan = s.result || null;
const schema = %s;
const v = validateAutodevContract(plan, schema);
if (!v.ok) {
  return [{json: {ok: false, failure_class: 'CONTRACT_FAILURE',
    failure_signature: 'CONTRACT_INVALID', error: v.errors.join(' | '),
    job_record: s.job_record}}];
}
const ctx = $('Sub-Workflow Trigger').first().json;
const issue = ctx.issue || {};
const baselineHead = (ctx.baseline && ctx.baseline.repository && ctx.baseline.repository.head) || '';
const reasons = [];
if (plan.run_id !== issue.run_id) reasons.push('PLAN_RUN_ID_MISMATCH');
if (baselineHead && plan.repository_head !== baselineHead) reasons.push('PLAN_HEAD_MISMATCH');
if (!plan.acceptance_criteria || !plan.acceptance_criteria.length) reasons.push('ACCEPTANCE_CRITERIA_MISSING');
if (!plan.build_scope || !plan.build_scope.allowed_files || !plan.build_scope.allowed_files.length) reasons.push('BUILD_SCOPE_MISSING');
if (!plan.required_tests || !plan.required_tests.length) reasons.push('REQUIRED_TESTS_INVALID');
if (!plan.context || !plan.context.fingerprint) reasons.push('CONTEXT_FINGERPRINT_MISSING');
if (plan.safety && (plan.safety.sentinel_absent !== true || plan.safety.repo_unchanged !== true)) reasons.push('FORBIDDEN_MUTATION');
const planTargets = [].concat((plan.targets && plan.targets.files) || [],
  (plan.build_scope && plan.build_scope.allowed_files) || []);
if (planTargets.some((path) => path === '.plan-canary-sentinel' || path === './.plan-canary-sentinel')) reasons.push('FORBIDDEN_TARGET');
const approved = reasons.length === 0;
return [{json: {
  ok: true,
  plan: plan,
  plan_fingerprint: s.job_record ? s.job_record.output_fingerprint : '',
  job_record: s.job_record,
  gate: {status: approved ? 'APPROVED' : 'REJECTED',
         reason_code: approved ? 'PLAN_GATE_APPROVED' : reasons.join(',')}
}}];""" % embed_schema("autodev.plan.v1")
    gate = code_node("Plan Gate", JS_VALIDATOR + gate_js, [6 * 240, 2 * 160])
    # rewire: Extract plan -> Plan Gate (instead of Validate plan)
    wf.connections["Extract plan"]["main"] = [
        [{"node": "Plan Gate", "type": "main", "index": 0}]
    ]
    wf.add_node(gate)
    # A worker failure is a real plan failure, not a missing artifact. Keep
    # its classification/signature visible to the orchestrator and status UI.
    failure = code_node(
        "Plan Failure Gate",
        """const s = $json;
return [{json: {ok: false, plan: null, plan_fingerprint: '',
  job_record: s.job_record || {}, failure_class: s.failure_class || 'INFRA_FAILURE',
  failure_signature: s.failure_signature || null, error: s.error || null,
  gate: {status: 'BLOCKED', reason_code: s.failure_class || 'INFRA_FAILURE',
    failure_signature: s.failure_signature || null, error: s.error || null}}}];""",
        [6 * 240, 1 * 160],
    )
    wf.add_node(failure)
    wf.add("Failed plan", failure)
    wf.add("Timeout", failure)
    return wf


# ============================================================ 40 AutoDev Build
def build_40(cfg):
    def builder(cfg):
        wf = WF("40 AutoDev Build")
        P = lambda x, y: [x * 240, y * 160]  # noqa: E731
        wf.add_node(
            node(
                "Sub-Workflow Trigger",
                "n8n-nodes-base.executeWorkflowTrigger",
                {},
                P(-1, 0),
                1,
            )
        )
        prep_js = """const s = $json;
const plan = s.plan || {};
const issue = s.issue || {};
const input = {
  contract: 'autodev.build-input.v1', version: 'v1',
  run_id: issue.run_id,
  attempt_id: s.attempt_id_build || (issue.run_id + ':build:' + ((s.attempt_build || 0) + 1)),
  plan_fingerprint: s.plan_fingerprint || '',
  repository_head: s.baseline_head || '',
  targets: plan.targets || {files: []},
  acceptance_criteria: plan.acceptance_criteria || [],
  required_tests: plan.required_tests || [],
  build_scope: plan.build_scope || {allowed_files: []},
  changes_expected: plan.changes_expected !== false,
  task_description: issue.task_description || '',
  strategy_delta: null,
  failure_context: null
};
return [{json: {
  run_id: issue.run_id, job_id: issue.run_id + ':build:' + ((s.attempt_build || 0) + 1),
  job_type: 'build', attempt_id: input.attempt_id,
  input_contract: 'autodev.build-input.v1', input: input,
  backend: s.backend || 'opencode-builder-8001', fixture: s.fixture || null,
  provider: (s.provider || null),
  model: (s.model || null),
  model_revision: (s.model_revision || null),
  task_class: 'build'
}}];"""
        prep = code_node("Prep Build Input", prep_js, P(0, 0))
        wf.add("Sub-Workflow Trigger", prep)
        dispatch = http_node(
            "Dispatch Build",
            "POST",
            cfg.jobs(),
            "JSON.stringify($json)",
            P(1, 0),
            cfg.cr_harness,
        )
        wf.add_node(prep)
        wf.add_node(dispatch)
        wf.add(prep, dispatch)

        w = wait_node("Wait", 5, P(2, 0))
        poll = http_node(
            "Poll",
            "GET",
            cfg.adapter
            + "/v1/jobs/{{ $json.data ? $json.data.job_id : $json.job_id }}",
            "{}",
            P(3, 0),
            cfg.cr_harness,
            send_body=False,
            params_extra={
                "url": cfg.adapter
                + "/v1/jobs/{{ $json.data ? $json.data.job_id : $json.job_id }}"
            },
        )
        parse = code_node(
            "Parse",
            """const raw = $json;
const d = (raw && raw.data) ? raw.data : raw;
return [{json: d}];""",
            P(4, 0),
        )
        done = str_if("Done?", "$json.status", "completed", P(5, 0))
        failed = str_if("Failed?", "$json.status", "failed", P(6, 0))
        inc = code_node(
            "Incr",
            """const s = $json;
return [{json: Object.assign({}, s, {polls: (s.polls || 0) + 1})}];""",
            P(7, 0),
        )
        lim = num_if("Limit?", "$json.polls", "gte", 40, P(8, 0))
        timeout = code_node(
            "Timeout",
            """const s = $json;
return [{json: {ok: false, failure_class: 'TIMEOUT',
  failure_signature: 'POLL_TIMEOUT', error: 'poll limit reached'}}];""",
            P(9, 0),
        )
        for n in (w, poll, parse, done, failed, inc, lim, timeout):
            wf.add_node(n)
        wf.add(dispatch, w)
        wf.add(w, poll)
        wf.add(poll, parse)
        wf.add(parse, done)
        wf.add(done, failed, 1)
        wf.add(failed, inc, 1)
        wf.add(inc, lim)
        wf.add(lim, w, 1)
        wf.add(lim, timeout, 0)

        extract = code_node(
            "Extract Build",
            """const s = $json;
const rec = s;
return [{json: {
  job_record: {job_id: rec.job_id, status: rec.status, job_type: rec.job_type,
    attempt_id: rec.attempt_id, backend: rec.backend, provider: rec.provider,
    model: rec.model, input_contract: rec.input_contract,
    input_fingerprint: rec.input_fingerprint,
    output_contract: rec.output_contract, output_fingerprint: rec.output_fingerprint,
    started_at: rec.started_at, ended_at: rec.ended_at, duration_ms: rec.duration_ms,
    failure_class: rec.failure_class, failure_signature: rec.failure_signature,
    strategy_delta: rec.strategy_delta, result_ref: rec.result_ref, error: rec.error},
  result: rec.result || null
}}];""",
            P(5, 1),
        )
        wf.add_node(extract)
        wf.add(done, extract, 0)
        fail = code_node(
            "Failed Build",
            """const s = $json;
return [{json: {ok: false, failure_class: s.failure_class || 'UNKNOWN',
  failure_signature: s.failure_signature || null, error: s.error || null,
  job_record: {job_id: s.job_id, attempt_id: s.attempt_id, status: s.status,
    backend: s.backend, provider: s.provider, model: s.model,
    input_contract: s.input_contract, input_fingerprint: s.input_fingerprint,
    output_contract: s.output_contract, output_fingerprint: null,
    started_at: s.started_at, ended_at: s.ended_at, duration_ms: s.duration_ms,
    failure_class: s.failure_class, failure_signature: s.failure_signature,
    strategy_delta: s.strategy_delta, result_ref: s.result_ref, error: s.error}}}];""",
            P(6, 1),
        )
        wf.add_node(fail)
        wf.add(failed, fail, 0)
        val_js = """const s = $json;
const result = s.result;
const schema = %s;
const v = validateAutodevContract(result, schema);
if (!v.ok) return [{json: {ok: false, failure_class: 'CONTRACT_FAILURE',
  failure_signature: 'CONTRACT_INVALID', error: v.errors.join(' | '),
  job_record: s.job_record}}];
return [{json: {ok: true, build_result: result, job_record: s.job_record}}];""" % (
            embed_schema("autodev.build-result.v1")
        )
        val = code_node("Validate Build", JS_VALIDATOR + val_js, P(6, 2))
        wf.add_node(val)
        wf.add(extract, val)
        return wf

    return builder(cfg)


# ============================================================ 50 AutoDev Verify
def build_50(cfg):
    def builder(cfg):
        wf = WF("50 AutoDev Verify")
        P = lambda x, y: [x * 240, y * 160]  # noqa: E731
        wf.add_node(
            node(
                "Sub-Workflow Trigger",
                "n8n-nodes-base.executeWorkflowTrigger",
                {},
                P(-1, 0),
                1,
            )
        )
        prep_js = """const s = $json;
const plan = s.plan || {};
const issue = s.issue || {};
const attemptId = s.verify_attempt_id || (issue.run_id + ':verify:' + ((s.attempt_build || 0) + (s.attempt_fix || 0) + 1));
const input = {
  contract: 'autodev.build-input.v1', version: 'v1',
  run_id: issue.run_id, attempt_id: attemptId,
  plan_fingerprint: s.plan_fingerprint || '',
  repository_head: s.baseline_head || '',
  targets: plan.targets || {files: []},
  acceptance_criteria: plan.acceptance_criteria || [],
  required_tests: plan.required_tests || [],
  build_scope: plan.build_scope || {allowed_files: []},
  changes_expected: plan.changes_expected !== false,
  task_description: issue.task_description || '',
  strategy_delta: null, failure_context: null
};
return [{json: {
  run_id: issue.run_id, job_id: issue.run_id + ':verify:' + attemptId.split(':').pop(),
  job_type: 'verify', attempt_id: attemptId,
  input_contract: 'autodev.build-input.v1', input: input,
  backend: s.backend || 'opencode-builder-8001', fixture: s.fixture || null,
  provider: (s.provider || null),
  model: (s.model || null),
  model_revision: (s.model_revision || null),
  task_class: 'verify'
}}];"""
        prep = code_node("Prep Verify Input", prep_js, P(0, 0))
        wf.add("Sub-Workflow Trigger", prep)
        dispatch = http_node(
            "Dispatch Verify",
            "POST",
            cfg.jobs(),
            "JSON.stringify($json)",
            P(1, 0),
            cfg.cr_harness,
        )
        wf.add_node(prep)
        wf.add_node(dispatch)
        wf.add(prep, dispatch)
        w = wait_node("Wait", 5, P(2, 0))
        poll = http_node(
            "Poll",
            "GET",
            cfg.adapter
            + "/v1/jobs/{{ $json.data ? $json.data.job_id : $json.job_id }}",
            "{}",
            P(3, 0),
            cfg.cr_harness,
            send_body=False,
            params_extra={
                "url": cfg.adapter
                + "/v1/jobs/{{ $json.data ? $json.data.job_id : $json.job_id }}"
            },
        )
        parse = code_node(
            "Parse",
            """const raw = $json;
const d = (raw && raw.data) ? raw.data : raw;
return [{json: d}];""",
            P(4, 0),
        )
        done = str_if("Done?", "$json.status", "completed", P(5, 0))
        failed = str_if("Failed?", "$json.status", "failed", P(6, 0))
        inc = code_node(
            "Incr",
            """const s = $json;
return [{json: Object.assign({}, s, {polls: (s.polls || 0) + 1})}];""",
            P(7, 0),
        )
        lim = num_if("Limit?", "$json.polls", "gte", 40, P(8, 0))
        timeout = code_node(
            "Timeout",
            """const s = $json;
return [{json: {ok: false, failure_class: 'TIMEOUT',
  failure_signature: 'POLL_TIMEOUT', error: 'poll limit reached'}}];""",
            P(9, 0),
        )
        for n in (w, poll, parse, done, failed, inc, lim, timeout):
            wf.add_node(n)
        wf.add(dispatch, w)
        wf.add(w, poll)
        wf.add(poll, parse)
        wf.add(parse, done)
        wf.add(done, failed, 1)
        wf.add(failed, inc, 1)
        wf.add(inc, lim)
        wf.add(lim, w, 1)
        wf.add(lim, timeout, 0)
        extract = code_node(
            "Extract Verify",
            """const s = $json;
const rec = s;
return [{json: {
  job_record: {job_id: rec.job_id, status: rec.status, job_type: rec.job_type,
    attempt_id: rec.attempt_id, backend: rec.backend, provider: rec.provider,
    model: rec.model, input_contract: rec.input_contract,
    input_fingerprint: rec.input_fingerprint,
    output_contract: rec.output_contract, output_fingerprint: rec.output_fingerprint,
    started_at: rec.started_at, ended_at: rec.ended_at, duration_ms: rec.duration_ms,
    failure_class: rec.failure_class, failure_signature: rec.failure_signature,
    strategy_delta: rec.strategy_delta, result_ref: rec.result_ref, error: rec.error},
  result: rec.result || null
}}];""",
            P(5, 1),
        )
        wf.add_node(extract)
        wf.add(done, extract, 0)
        fail = code_node(
            "Failed Verify",
            """const s = $json;
return [{json: {ok: false, failure_class: s.failure_class || 'UNKNOWN',
  failure_signature: s.failure_signature || null, error: s.error || null,
  job_record: {job_id: s.job_id, attempt_id: s.attempt_id, status: s.status,
    backend: s.backend, provider: s.provider, model: s.model,
    input_contract: s.input_contract, input_fingerprint: s.input_fingerprint,
    output_contract: s.output_contract, output_fingerprint: null,
    started_at: s.started_at, ended_at: s.ended_at, duration_ms: s.duration_ms,
    failure_class: s.failure_class, failure_signature: s.failure_signature,
    strategy_delta: s.strategy_delta, result_ref: s.result_ref, error: s.error}}}];""",
            P(6, 1),
        )
        wf.add_node(fail)
        wf.add(failed, fail, 0)
        val_js = """const s = $json;
const result = s.result;
const schema = %s;
const v = validateAutodevContract(result, schema);
if (!v.ok) return [{json: {ok: false, failure_class: 'CONTRACT_FAILURE',
  failure_signature: 'CONTRACT_INVALID', error: v.errors.join(' | '),
  job_record: s.job_record}}];
return [{json: {ok: true, verification: result, job_record: s.job_record}}];""" % (
            embed_schema("autodev.verification.v1")
        )
        val = code_node("Validate Verify", JS_VALIDATOR + val_js, P(6, 2))
        wf.add_node(val)
        wf.add(extract, val)
        return wf

    return builder(cfg)


# ============================================================ 80 AutoDev Fix
def build_80(cfg):
    def builder(cfg):
        wf = WF("80 AutoDev Fix")
        P = lambda x, y: [x * 240, y * 160]  # noqa: E731
        wf.add_node(
            node(
                "Sub-Workflow Trigger",
                "n8n-nodes-base.executeWorkflowTrigger",
                {},
                P(-1, 0),
                1,
            )
        )
        prep_js = """const s = $json;
const plan = s.plan || {};
const issue = s.issue || {};
const verification = s.verification || {};
const attemptNo = (s.attempt_fix || 0) + 1;
const input = {
  contract: 'autodev.build-input.v1', version: 'v1',
  run_id: issue.run_id, attempt_id: issue.run_id + ':fix:' + attemptNo,
  plan_fingerprint: s.plan_fingerprint || '',
  repository_head: s.baseline_head || '',
  targets: plan.targets || {files: []},
  acceptance_criteria: plan.acceptance_criteria || [],
  required_tests: plan.required_tests || [],
  build_scope: plan.build_scope || {allowed_files: []},
  changes_expected: plan.changes_expected !== false,
  task_description: issue.task_description || '',
  strategy_delta: 'include failing test output; run targeted fix',
  failure_context: {
    failure_signature: verification.failure_signature || '',
    failure_class: verification.failure_class || 'UNKNOWN',
    new_evidence: verification.new_evidence || []
  }
};
return [{json: {
  run_id: issue.run_id, job_id: issue.run_id + ':fix:' + attemptNo,
  job_type: 'fix', attempt_id: input.attempt_id,
  input_contract: 'autodev.build-input.v1', input: input,
  backend: s.backend || 'opencode-builder-8001', fixture: s.fixture || null,
  provider: (s.provider || null),
  model: (s.model || null),
  model_revision: (s.model_revision || null),
  task_class: 'build'
}}];"""
        prep = code_node("Prep Fix Input", prep_js, P(0, 0))
        wf.add("Sub-Workflow Trigger", prep)
        dispatch = http_node(
            "Dispatch Fix",
            "POST",
            cfg.jobs(),
            "JSON.stringify($json)",
            P(1, 0),
            cfg.cr_harness,
        )
        wf.add_node(prep)
        wf.add_node(dispatch)
        wf.add(prep, dispatch)
        w = wait_node("Wait", 5, P(2, 0))
        poll = http_node(
            "Poll",
            "GET",
            cfg.adapter
            + "/v1/jobs/{{ $json.data ? $json.data.job_id : $json.job_id }}",
            "{}",
            P(3, 0),
            cfg.cr_harness,
            send_body=False,
            params_extra={
                "url": cfg.adapter
                + "/v1/jobs/{{ $json.data ? $json.data.job_id : $json.job_id }}"
            },
        )
        parse = code_node(
            "Parse",
            """const raw = $json;
const d = (raw && raw.data) ? raw.data : raw;
return [{json: d}];""",
            P(4, 0),
        )
        done = str_if("Done?", "$json.status", "completed", P(5, 0))
        failed = str_if("Failed?", "$json.status", "failed", P(6, 0))
        inc = code_node(
            "Incr",
            """const s = $json;
return [{json: Object.assign({}, s, {polls: (s.polls || 0) + 1})}];""",
            P(7, 0),
        )
        lim = num_if("Limit?", "$json.polls", "gte", 40, P(8, 0))
        timeout = code_node(
            "Timeout",
            """const s = $json;
return [{json: {ok: false, failure_class: 'TIMEOUT',
  failure_signature: 'POLL_TIMEOUT', error: 'poll limit reached'}}];""",
            P(9, 0),
        )
        for n in (w, poll, parse, done, failed, inc, lim, timeout):
            wf.add_node(n)
        wf.add(dispatch, w)
        wf.add(w, poll)
        wf.add(poll, parse)
        wf.add(parse, done)
        wf.add(done, failed, 1)
        wf.add(failed, inc, 1)
        wf.add(inc, lim)
        wf.add(lim, w, 1)
        wf.add(lim, timeout, 0)
        extract = code_node(
            "Extract Fix",
            """const s = $json;
const rec = s;
return [{json: {
  job_record: {job_id: rec.job_id, status: rec.status, job_type: rec.job_type,
    attempt_id: rec.attempt_id, backend: rec.backend, provider: rec.provider,
    model: rec.model, input_contract: rec.input_contract,
    input_fingerprint: rec.input_fingerprint,
    output_contract: rec.output_contract, output_fingerprint: rec.output_fingerprint,
    started_at: rec.started_at, ended_at: rec.ended_at, duration_ms: rec.duration_ms,
    failure_class: rec.failure_class, failure_signature: rec.failure_signature,
    strategy_delta: rec.strategy_delta, result_ref: rec.result_ref, error: rec.error},
  result: rec.result || null
}}];""",
            P(5, 1),
        )
        wf.add_node(extract)
        wf.add(done, extract, 0)
        fail = code_node(
            "Failed Fix",
            """const s = $json;
return [{json: {ok: false, failure_class: s.failure_class || 'UNKNOWN',
  failure_signature: s.failure_signature || null, error: s.error || null,
  job_record: {job_id: s.job_id, attempt_id: s.attempt_id, status: s.status,
    backend: s.backend, provider: s.provider, model: s.model,
    input_contract: s.input_contract, input_fingerprint: s.input_fingerprint,
    output_contract: s.output_contract, output_fingerprint: null,
    started_at: s.started_at, ended_at: s.ended_at, duration_ms: s.duration_ms,
    failure_class: s.failure_class, failure_signature: s.failure_signature,
    strategy_delta: s.strategy_delta, result_ref: s.result_ref, error: s.error}}}];""",
            P(6, 1),
        )
        wf.add_node(fail)
        wf.add(failed, fail, 0)
        val_js = """const s = $json;
const result = s.result;
const schema = %s;
const v = validateAutodevContract(result, schema);
if (!v.ok) return [{json: {ok: false, failure_class: 'CONTRACT_FAILURE',
  failure_signature: 'CONTRACT_INVALID', error: v.errors.join(' | '),
  job_record: s.job_record}}];
return [{json: {ok: true, build_result: result, job_record: s.job_record}}];""" % (
            embed_schema("autodev.build-result.v1")
        )
        val = code_node("Validate Fix", JS_VALIDATOR + val_js, P(6, 2))
        wf.add_node(val)
        wf.add(extract, val)
        return wf

    return builder(cfg)


# ======================================================== 20 Research Batch ==
def build_20(cfg):
    def builder(cfg):
        wf = WF("20 AutoDev Research Batch")
        P = lambda x, y: [x * 240, y * 160]  # noqa: E731
        wf.add_node(
            node(
                "Sub-Workflow Trigger",
                "n8n-nodes-base.executeWorkflowTrigger",
                {},
                P(-1, 0),
                1,
            )
        )
        prep_js = """const s = $json;
const runId = s.issue.run_id;
const backend = s.backend || 'opencode-builder-8001';
const jobs = ['code', 'docs', 'tests'].map((area) => ({
  job_id: runId + ':research.' + area + ':1',
  job_type: 'research.' + area,
  attempt_id: runId + ':research.' + area + ':1',
  input_contract: 'autodev.issue.v1',
  input: s.issue,
  backend: backend,
  fixture: s.fixture || null,
  provider: s.provider || null,
  model: s.model || null,
  model_revision: s.model_revision || null,
  task_class: 'research'
}));
return [{json: {
  run_id: runId, batch_id: runId + ':research-batch',
  jobs: jobs, barrier: 'all'
}}];"""
        prep = code_node("Prep Research Batch", prep_js, P(0, 0))
        wf.add("Sub-Workflow Trigger", prep)
        dispatch = http_node(
            "Dispatch Research Batch",
            "POST",
            cfg.batches(),
            "JSON.stringify($json)",
            P(1, 0),
            cfg.cr_harness,
        )
        wf.add_node(prep)
        wf.add_node(dispatch)
        wf.add(prep, dispatch)
        w = wait_node("Wait", 5, P(2, 0))
        poll = http_node(
            "Poll Batch",
            "GET",
            cfg.adapter
            + "/v1/batches/{{ $json.data ? $json.data.batch_id : $json.batch_id }}",
            "{}",
            P(3, 0),
            cfg.cr_harness,
            send_body=False,
            params_extra={
                "url": cfg.adapter
                + "/v1/batches/{{ $json.data ? $json.data.batch_id : $json.batch_id }}"
            },
        )
        parse = code_node(
            "Parse Batch",
            """const raw = $json;
const d = (raw && raw.data) ? raw.data : raw;
return [{json: d}];""",
            P(4, 0),
        )
        done = str_if("Batch Done?", "$json.status", "completed", P(5, 0))
        failed = str_if("Batch Failed?", "$json.status", "interrupted", P(6, 0))
        inc = code_node(
            "Incr",
            """const s = $json;
return [{json: Object.assign({}, s, {polls: (s.polls || 0) + 1})}];""",
            P(7, 0),
        )
        lim = num_if("Limit?", "$json.polls", "gte", 40, P(8, 0))
        timeout = code_node(
            "Timeout",
            """const s = $json;
return [{json: {ok: false, failure_class: 'TIMEOUT',
  failure_signature: 'POLL_TIMEOUT', error: 'poll limit reached'}}];""",
            P(9, 0),
        )
        for n in (w, poll, parse, done, failed, inc, lim, timeout):
            wf.add_node(n)
        wf.add(dispatch, w)
        wf.add(w, poll)
        wf.add(poll, parse)
        wf.add(parse, done)
        wf.add(done, failed, 1)
        wf.add(failed, inc, 1)
        wf.add(inc, lim)
        wf.add(lim, w, 1)
        wf.add(lim, timeout, 0)

        join_js = (
            """const s = $json;
const jobs = s.jobs || [];
const byType = {};
for (const j of jobs) {
  if (j.job_type && j.result) byType[j.job_type] = j;
}
const code = byType['research.code'] || {};
const docs = byType['research.docs'] || {};
const tests = byType['research.tests'] || {};
const area = (r) => (r.result && r.result.areas) ? r.result.areas : {};
const spans = jobs.filter(j => j.started_at && j.ended_at).map(j => ({
  job_id: j.job_id, job_type: j.job_type,
  started_at: j.started_at, ended_at: j.ended_at, duration_ms: j.duration_ms
}));
const overlap = (a, b) => a.started_at < b.ended_at && b.started_at < a.ended_at;
let overlapProven = false;
for (let i = 0; i < spans.length; i++) {
  for (let k = i + 1; k < spans.length; k++) {
    if (overlap(spans[i], spans[k])) overlapProven = true;
  }
}
const research = {
  contract: 'autodev.research.v1', version: 'v1',
  run_id: s.run_id,
  areas: {
    code: (area(code).code || '') + (area(code).docs || '') + (area(code).tests || ''),
    docs: (area(docs).docs || '') + (area(docs).code || '') + (area(docs).tests || ''),
    tests: (area(tests).tests || '') + (area(tests).code || '') + (area(tests).docs || '')
  },
  findings: [], recommendations: [],
  parallelism: {jobs: spans, overlap_proven: overlapProven}
};
"""
            + JS_VALIDATOR
            + """
const schema = %s;
const v = validateAutodevContract(research, schema);
if (!v.ok) return [{json: {ok: false, failure_class: 'CONTRACT_FAILURE',
  failure_signature: 'CONTRACT_INVALID', error: v.errors.join(' | ')}}];
return [{json: {ok: true, research: research}}];"""
            % embed_schema("autodev.research.v1")
        )
        join = code_node("Join Research", join_js, P(5, 1))
        wf.add_node(join)
        wf.add(done, join, 0)
        fail = code_node(
            "Batch Failed",
            """const s = $json;
const jobs = s.jobs || [];
const failedJob = jobs.find(j => j.status === 'failed' || j.status === 'interrupted') || {};
return [{json: {ok: false, failure_class: failedJob.failure_class || 'INFRA_FAILURE',
  failure_signature: failedJob.failure_signature || 'BATCH_FAILED',
  error: failedJob.error || 'research batch failed'}}];""",
            P(6, 1),
        )
        wf.add_node(fail)
        wf.add(failed, fail, 0)
        return wf

    return builder(cfg)


# ======================================================== 60 Review Batch ==
def build_60(cfg):
    def builder(cfg):
        wf = WF("60 AutoDev Review Batch")
        P = lambda x, y: [x * 240, y * 160]  # noqa: E731
        wf.add_node(
            node(
                "Sub-Workflow Trigger",
                "n8n-nodes-base.executeWorkflowTrigger",
                {},
                P(-1, 0),
                1,
            )
        )
        prep_js = """const s = $json;
const runId = s.issue.run_id;
const backend = s.backend || 'opencode-builder-8001';
const build = s.build || {};
const buildInput = {
  contract: 'autodev.build-result.v1', version: 'v1',
  run_id: runId,
  attempt_id: build.attempt_id || runId + ':build:1',
  status: 'success',
  changed_files: build.changed_files || [],
  summary: build.summary || '',
  test_results: build.test_results || {passed: 0, failed: 0}
};
const attemptNo = (s.attempt_build || 0) + (s.attempt_fix || 0);
const jobs = ['correctness', 'security', 'quality'].map((area) => ({
  job_id: runId + ':review.' + area + ':' + attemptNo,
  job_type: 'review.' + area,
  attempt_id: runId + ':review.' + area + ':' + attemptNo,
  input_contract: 'autodev.build-result.v1',
  input: buildInput,
  backend: backend,
  fixture: s.fixture || null,
  provider: s.provider || null,
  model: s.model || null,
  model_revision: s.model_revision || null,
  task_class: 'review'
}));
return [{json: {
  run_id: runId, batch_id: runId + ':review-batch:' + attemptNo,
  jobs: jobs, barrier: 'all'
}}];"""
        prep = code_node("Prep Review Batch", prep_js, P(0, 0))
        wf.add("Sub-Workflow Trigger", prep)
        dispatch = http_node(
            "Dispatch Review Batch",
            "POST",
            cfg.batches(),
            "JSON.stringify($json)",
            P(1, 0),
            cfg.cr_harness,
        )
        wf.add_node(prep)
        wf.add_node(dispatch)
        wf.add(prep, dispatch)
        w = wait_node("Wait", 5, P(2, 0))
        poll = http_node(
            "Poll Batch",
            "GET",
            cfg.adapter
            + "/v1/batches/{{ $json.data ? $json.data.batch_id : $json.batch_id }}",
            "{}",
            P(3, 0),
            cfg.cr_harness,
            send_body=False,
            params_extra={
                "url": cfg.adapter
                + "/v1/batches/{{ $json.data ? $json.data.batch_id : $json.batch_id }}"
            },
        )
        parse = code_node(
            "Parse Batch",
            """const raw = $json;
const d = (raw && raw.data) ? raw.data : raw;
return [{json: d}];""",
            P(4, 0),
        )
        done = str_if("Batch Done?", "$json.status", "completed", P(5, 0))
        failed = str_if("Batch Failed?", "$json.status", "interrupted", P(6, 0))
        inc = code_node(
            "Incr",
            """const s = $json;
return [{json: Object.assign({}, s, {polls: (s.polls || 0) + 1})}];""",
            P(7, 0),
        )
        lim = num_if("Limit?", "$json.polls", "gte", 40, P(8, 0))
        timeout = code_node(
            "Timeout",
            """const s = $json;
return [{json: {ok: false, failure_class: 'TIMEOUT',
  failure_signature: 'POLL_TIMEOUT', error: 'poll limit reached'}}];""",
            P(9, 0),
        )
        for n in (w, poll, parse, done, failed, inc, lim, timeout):
            wf.add_node(n)
        wf.add(dispatch, w)
        wf.add(w, poll)
        wf.add(poll, parse)
        wf.add(parse, done)
        wf.add(done, failed, 1)
        wf.add(failed, inc, 1)
        wf.add(inc, lim)
        wf.add(lim, w, 1)
        wf.add(lim, timeout, 0)

        join_js = (
            """const s = $json;
const jobs = s.jobs || [];
const reviews = [];
for (const j of jobs) {
  const r = j.result || {};
  const revs = r.reviews || [];
  if (revs.length) reviews.push(revs[0]);
}
const blocked = reviews.some(rv =>
  rv.findings.some(f => f.category === 'security' &&
    (f.severity === 'HIGH' || f.severity === 'CRITICAL') && f.blocking === true));
const blockingFindings = reviews.flatMap(rv => rv.findings).filter(f => f.blocking === true);
const spans = jobs.filter(j => j.started_at && j.ended_at).map(j => ({
  job_id: j.job_id, job_type: j.job_type,
  started_at: j.started_at, ended_at: j.ended_at, duration_ms: j.duration_ms
}));
const overlap = (a, b) => a.started_at < b.ended_at && b.started_at < a.ended_at;
let overlapProven = false;
for (let i = 0; i < spans.length; i++) {
  for (let k = i + 1; k < spans.length; k++) {
    if (overlap(spans[i], spans[k])) overlapProven = true;
  }
}
const review = {
  contract: 'autodev.review-batch.v1', version: 'v1',
  run_id: s.run_id,
  reviews: reviews,
  blocked: blocked,
  blocking_findings: blockingFindings,
  parallelism: {jobs: spans, overlap_proven: overlapProven}
};
"""
            + JS_VALIDATOR
            + """
const schema = %s;
const v = validateAutodevContract(review, schema);
if (!v.ok) return [{json: {ok: false, failure_class: 'CONTRACT_FAILURE',
  failure_signature: 'CONTRACT_INVALID', error: v.errors.join(' | ')}}];
return [{json: {ok: true, review: review}}];"""
            % embed_schema("autodev.review-batch.v1")
        )
        join = code_node("Join Review", join_js, P(5, 1))
        wf.add_node(join)
        wf.add(done, join, 0)
        fail = code_node(
            "Batch Failed",
            """const s = $json;
const jobs = s.jobs || [];
const failedJob = jobs.find(j => j.status === 'failed' || j.status === 'interrupted') || {};
return [{json: {ok: false, failure_class: failedJob.failure_class || 'INFRA_FAILURE',
  failure_signature: failedJob.failure_signature || 'BATCH_FAILED',
  error: failedJob.error || 'review batch failed'}}];""",
            P(6, 1),
        )
        wf.add_node(fail)
        wf.add(failed, fail, 0)
        return wf

    return builder(cfg)


# ============================================================ 70 Decision ==
def build_70(cfg):
    wf = WF("70 AutoDev Decision")
    P = lambda x, y: [x * 240, y * 160]  # noqa: E731
    wf.add_node(
        node(
            "Sub-Workflow Trigger",
            "n8n-nodes-base.executeWorkflowTrigger",
            {},
            P(-1, 0),
            1,
        )
    )
    decision_js = (
        """const s = $json;
const review = s.review || {};
const verification = s.verification || {};
const runId = s.issue.run_id;
const findings = (review.reviews || []).flatMap(rv => rv.findings || []);
const securityBlocking = findings.some(f =>
  f.category === 'security' &&
  (f.severity === 'HIGH' || f.severity === 'CRITICAL') && f.blocking === true);
const splitRequested = findings.some(f => f.rule === 'REVIEW-SPLIT-REQUEST');
const correctnessFail = (review.reviews || []).some(rv =>
  rv.category === 'correctness' && rv.verdict === 'FAIL');
const qualityFail = (review.reviews || []).some(rv =>
  rv.category === 'quality' && rv.verdict === 'FAIL');
let decision, reasonCode, next;
if (securityBlocking) {
  decision = 'BLOCKED'; reasonCode = 'BLOCKING_HIGH_OR_CRITICAL_FINDING'; next = 'terminal';
} else if (splitRequested) {
  decision = 'SPLIT'; reasonCode = 'REVIEW_REQUESTED_SPLIT'; next = 'split';
} else if (correctnessFail) {
  decision = 'FIX'; reasonCode = 'CORRECTNESS_FINDINGS'; next = 'fix';
} else if (qualityFail) {
  decision = 'FIX'; reasonCode = 'NON_BLOCKING_REVIEW_FINDINGS'; next = 'fix';
} else if (verification && verification.passed !== true) {
  decision = 'FIX'; reasonCode = 'VERIFY_FAILED'; next = 'fix';
} else {
  decision = 'DONE'; reasonCode = 'ALL_HARD_GATES_GREEN'; next = 'terminal';
}
const decisionContract = {
  contract: 'autodev.decision.v1', version: 'v1',
  run_id: runId, decision: decision, reason_code: reasonCode, next: next,
  evidence: {
    verification_ref: s.verify_job ? (s.verify_job.result_ref || '') : '',
    review_ref: s.review_job ? (s.review_job.result_ref || '') : ''
  }
};
"""
        + JS_VALIDATOR
        + """
const schema = %s;
const v = validateAutodevContract(decisionContract, schema);
if (!v.ok) return [{json: {ok: false, failure_class: 'CONTRACT_FAILURE',
  failure_signature: 'CONTRACT_INVALID', error: v.errors.join(' | ')}}];
return [{json: {ok: true, decision_contract: decisionContract}}];"""
        % embed_schema("autodev.decision.v1")
    )
    wf.add_node(code_node("Decision Policy", decision_js, P(0, 0)))
    wf.add("Sub-Workflow Trigger", "Decision Policy")
    wf.add_node(
        code_node(
            "Prep Artifact",
            """const s = $json;
return [{json: {artifact: s.decision_contract}}];""",
            P(1, 0),
        )
    )
    wf.add_node(
        http_node(
            "Store Decision Artifact",
            "POST",
            "http://192.168.1.136:8081/v1/artifacts/PLACEHOLDER/decision",
            "JSON.stringify($json)",
            P(2, 0),
            cfg.cr_harness,
            params_extra={
                "url": cfg.adapter
                + "/v1/artifacts/{{ $json.artifact.run_id }}/decision"
            },
        )
    )
    wf.add("Decision Policy", "Prep Artifact")
    wf.add("Prep Artifact", "Store Decision Artifact")
    wf.add_node(
        code_node(
            "Return Decision",
            """const s = $('Decision Policy').first().json;
return [{json: {ok: true, decision_contract: s.decision_contract}}];""",
            P(3, 0),
        )
    )
    wf.add("Store Decision Artifact", "Return Decision")
    return wf


# ============================================================ 90 Split ==
def build_90(cfg):
    wf = WF("90 AutoDev Split")
    P = lambda x, y: [x * 240, y * 160]  # noqa: E731
    wf.add_node(
        node(
            "Sub-Workflow Trigger",
            "n8n-nodes-base.executeWorkflowTrigger",
            {},
            P(-1, 0),
            1,
        )
    )
    split_js = (
        """const s = $json;
const runId = s.issue.run_id;
const reasonCode = (s.retry && s.retry.reason_code) || (s.decision && s.decision.reason_code) || 'SPLIT_REQUIRED';
const reason = reasonCode;
const subtasks = [
  {id: 'st-1', title: 'Isolate failing component',
   description: 'Isolate the failing component and capture its exact contract (inputs, outputs, failure).'},
  {id: 'st-2', title: 'Implement component',
   description: 'Implement the component against the isolated contract with focused tests.'},
  {id: 'st-3', title: 'Verify and integrate',
   description: 'Run the focused test suite, verify acceptance criteria, then integrate.'}
];
const split = {
  contract: 'autodev.split.v1', version: 'v1',
  parent_run_id: runId, reason: reason, reason_code: reasonCode,
  subtasks: subtasks,
  dependencies: [['st-1', 'st-2'], ['st-2', 'st-3']],
  acceptance_criteria: ['subtask st-1 delivered', 'subtask st-2 delivered', 'subtask st-3 delivered'],
  limits: {max_split_depth: 2, max_subtasks: 5, current_depth: 1}
};
"""
        + JS_VALIDATOR
        + """
const schema = %s;
const v = validateAutodevContract(split, schema);
if (!v.ok) return [{json: {ok: false, failure_class: 'CONTRACT_FAILURE',
  failure_signature: 'CONTRACT_INVALID', error: v.errors.join(' | ')}}];
return [{json: {ok: true, split: split}}];"""
        % embed_schema("autodev.split.v1")
    )
    wf.add_node(code_node("Split Policy", split_js, P(0, 0)))
    wf.add("Sub-Workflow Trigger", "Split Policy")
    wf.add_node(
        code_node(
            "Prep Artifact",
            """const s = $json;
return [{json: {artifact: s.split}}];""",
            P(1, 0),
        )
    )
    wf.add_node(
        http_node(
            "Store Split Artifact",
            "POST",
            cfg.adapter + "/v1/artifacts/{{ $json.artifact.parent_run_id }}/split",
            "JSON.stringify($json)",
            P(2, 0),
            cfg.cr_harness,
        )
    )
    wf.add("Split Policy", "Prep Artifact")
    wf.add("Prep Artifact", "Store Split Artifact")
    wf.add_node(
        code_node(
            "Return Split",
            """const s = $('Split Policy').first().json;
return [{json: {ok: true, split: s.split}}];""",
            P(3, 0),
        )
    )
    wf.add("Store Split Artifact", "Return Split")
    return wf


JS_VALIDATOR = r"""function validateAutodevContract(payload, schema) {
  const errors = [];
  try {
    if (schema && schema.type === 'object' && typeof payload !== 'object') {
      errors.push('$: expected object, got ' + typeof payload);
    } else {
      validateNode(payload, schema, '$', errors, schema);
    }
  } catch (e) {
    return { ok: false, contract: schema && schema.$id, errors: ['validator error: ' + e.message], error_count: 1 };
  }
  const contract = schema && schema.$id ? schema.$id : null;
  return { ok: errors.length === 0, contract, errors, error_count: errors.length };
}
function validateNode(value, schema, path, errors, root) {
  if (schema === true) return;
  if (schema === false) { errors.push(path + ': schema forbids value'); return; }
  if (schema.$ref) {
    const name = schema.$ref.replace('#/$defs/', '');
    const defs = (root.$defs || {})[name];
    if (!defs) throw new Error('unresolved $ref ' + schema.$ref);
    validateNode(value, defs, path, errors, root);
    return;
  }
  if (schema.oneOf) {
    let matched = 0;
    for (const sub of schema.oneOf) {
      const subErrors = [];
      validateNode(value, sub, path, subErrors, root);
      if (subErrors.length === 0) matched++;
    }
    if (matched !== 1) {
      errors.push(path + ': must match exactly one of ' + schema.oneOf.length + ' alternatives (matched ' + matched + ')');
    }
    return;
  }
  if (schema.type) {
    const expected = Array.isArray(schema.type) ? schema.type : [schema.type];
    const ok = expected.some((t) => typeCheck(value, t));
    if (!ok) {
      errors.push(path + ': expected ' + expected.join(' or ') + ', got ' + jsTypeName(value));
      return;
    }
  }
  if (schema.const !== undefined) {
    if (JSON.stringify(value) !== JSON.stringify(schema.const)) {
      errors.push(path + ': must equal ' + pyRepr(schema.const));
    }
    return;
  }
  if (schema.enum) {
    if (!schema.enum.some((e) => JSON.stringify(e) === JSON.stringify(value))) {
      errors.push(path + ': must be one of [' + schema.enum.map(pyRepr).join(', ') + ']');
    }
    return;
  }
  if (typeof value === 'string') {
    if (schema.minLength !== undefined && value.length < schema.minLength) {
      errors.push(path + ': length must be >= ' + schema.minLength);
    }
    if (schema.maxLength !== undefined && value.length > schema.maxLength) {
      errors.push(path + ': length must be <= ' + schema.maxLength);
    }
    if (schema.pattern) {
      const re = new RegExp(schema.pattern);
      if (!re.test(value)) errors.push(path + ': must match pattern ' + pyRepr(schema.pattern));
    }
    return;
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    if (schema.minimum !== undefined && value < schema.minimum) {
      errors.push(path + ': must be >= ' + schema.minimum);
    }
    if (schema.maximum !== undefined && value > schema.maximum) {
      errors.push(path + ': must be <= ' + schema.maximum);
    }
    return;
  }
  if (Array.isArray(value)) {
    if (schema.minItems !== undefined && value.length < schema.minItems) {
      errors.push(path + ': must have at least ' + schema.minItems + ' items');
    }
    if (schema.maxItems !== undefined && value.length > schema.maxItems) {
      errors.push(path + ': must have at most ' + schema.maxItems + ' items');
    }
    if (schema.items) {
      value.forEach((item, i) => validateNode(item, schema.items, path + '[' + i + ']', errors, root));
    }
    return;
  }
  if (typeof value === 'object' && value !== null) {
    const props = schema.properties || {};
    for (const [name, sub] of Object.entries(props)) {
      if (name in value) validateNode(value[name], sub, path + '.' + name, errors, root);
    }
    for (const name of schema.required || []) {
      if (!(name in value)) errors.push(path + ': ' + name + ' is required');
    }
    const addl = schema.additionalProperties === undefined ? true : schema.additionalProperties;
    if (addl === false) {
      for (const key of Object.keys(value)) {
        if (!(key in props)) errors.push(path + ': additional property ' + pyRepr(key) + ' not allowed');
      }
    } else if (typeof addl === 'object') {
      for (const key of Object.keys(value)) {
        if (!(key in props)) validateNode(value[key], addl, path + '.' + key, errors, root);
      }
    }
    return;
  }
}
function typeCheck(value, expected) {
  switch (expected) {
    case 'integer': return typeof value === 'number' && Number.isInteger(value);
    case 'number': return typeof value === 'number' && Number.isFinite(value);
    case 'string': return typeof value === 'string';
    case 'boolean': return typeof value === 'boolean';
    case 'object': return typeof value === 'object' && value !== null && !Array.isArray(value);
    case 'array': return Array.isArray(value);
    case 'null': return value === null;
    default: throw new Error('unsupported type ' + expected);
  }
}
function jsTypeName(value) {
  if (value === null) return 'NoneType';
  if (Array.isArray(value)) return 'list';
  if (typeof value === 'object') return 'dict';
  if (typeof value === 'string') return 'str';
  if (typeof value === 'boolean') return 'bool';
  if (typeof value === 'number') return Number.isInteger(value) ? 'int' : 'float';
  return typeof value;
}
function pyRepr(value) {
  if (value === null) return 'None';
  if (typeof value === 'boolean') return value ? 'True' : 'False';
  if (typeof value === 'string') return "'" + value.replace(/'/g, "\\'") + "'";
  return String(value);
}
"""

BUILDERS = {
    "00 AutoDev API Start": build_00,
    "01 AutoDev Orchestrator": build_01,
    "02 AutoDev API Status": build_02,
    "10 AutoDev Baseline": build_10,
    "20 AutoDev Research Batch": build_20,
    "30 AutoDev Plan": build_30,
    "40 AutoDev Build": build_40,
    "50 AutoDev Verify": build_50,
    "60 AutoDev Review Batch": build_60,
    "70 AutoDev Decision": build_70,
    "80 AutoDev Fix": build_80,
    "90 AutoDev Split": build_90,
}


def main():
    config_path, outdir = sys.argv[1], sys.argv[2]
    with open(config_path) as f:
        cfg = Cfg(json.load(f))
    os.makedirs(outdir, exist_ok=True)
    for name, builder in BUILDERS.items():
        wf = builder(cfg)
        fn = wf.out(outdir)
        print(
            "GENERATED",
            fn,
            "nodes=",
            len(wf.nodes),
            "edges=",
            sum(len(v["main"]) for v in wf.connections.values()),
        )


if __name__ == "__main__":
    main()
