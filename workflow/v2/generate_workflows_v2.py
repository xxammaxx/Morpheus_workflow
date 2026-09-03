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


# This is deliberately self-contained ES2020. n8n Code nodes do not need (or
# load) a Node crypto module for continuation identity. Its inputs are already
# restricted to ASCII identifiers by the control gateway, so charCodeAt is a
# stable byte representation here. 48 hex characters keep the full run id
# below the canonical `run-[A-Za-z0-9_-]{1,60}` limit.
CONTINUATION_RUN_ID_JS = r"""function canonicalContinuationRunId(projectId, sourceRunId, correlationId) {
  const text = JSON.stringify([String(projectId), String(sourceRunId), String(correlationId)]);
  const k = [1116352408,1899447441,3049323471,3921009573,961987163,1508970993,2453635748,2870763221,3624381080,310598401,607225278,1426881987,1925078388,2162078206,2614888103,3248222580,3835390401,4022224774,264347078,604807628,770255983,1249150122,1555081692,1996064986,2554220882,2821834349,2952996808,3210313671,3336571891,3584528711,113926993,338241895,666307205,773529912,1294757372,1396182291,1695183700,1986661051,2177026350,2456956037,2730485921,2820302411,3259730800,3345764771,3516065817,3600352804,4094571909,275423344,430227734,506948616,659060556,883997877,958139571,1322822218,1537002063,1747873779,1955562222,2024104815,2227730452,2361852424,2428436474,2756734187,3204031479,3329325298];
  const bytes = Array.from(text, char => char.charCodeAt(0));
  const bitLength = bytes.length * 8;
  bytes.push(128);
  while ((bytes.length % 64) !== 56) bytes.push(0);
  for (let i = 7; i >= 0; i -= 1) bytes.push(Math.floor(bitLength / (2 ** (i * 8))) & 255);
  let h0 = 1779033703, h1 = 3144134277, h2 = 1013904242, h3 = 2773480762;
  let h4 = 1359893119, h5 = 2600822924, h6 = 528734635, h7 = 1541459225;
  for (let offset = 0; offset < bytes.length; offset += 64) {
    const w = new Array(64);
    for (let i = 0; i < 16; i += 1) w[i] = ((bytes[offset + i * 4] << 24) | (bytes[offset + i * 4 + 1] << 16) | (bytes[offset + i * 4 + 2] << 8) | bytes[offset + i * 4 + 3]) >>> 0;
    for (let i = 16; i < 64; i += 1) {
      const a = w[i - 15], b = w[i - 2];
      const s0 = ((a >>> 7) | (a << 25)) ^ ((a >>> 18) | (a << 14)) ^ (a >>> 3);
      const s1 = ((b >>> 17) | (b << 15)) ^ ((b >>> 19) | (b << 13)) ^ (b >>> 10);
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
    }
    let a = h0, b = h1, c = h2, d = h3, e = h4, f = h5, g = h6, h = h7;
    for (let i = 0; i < 64; i += 1) {
      const s1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7));
      const choice = (e & f) ^ (~e & g);
      const temp1 = (h + s1 + choice + k[i] + w[i]) >>> 0;
      const s0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10));
      const majority = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (s0 + majority) >>> 0;
      h = g; g = f; f = e; e = (d + temp1) >>> 0; d = c; c = b; b = a; a = (temp1 + temp2) >>> 0;
    }
    h0 = (h0 + a) >>> 0; h1 = (h1 + b) >>> 0; h2 = (h2 + c) >>> 0; h3 = (h3 + d) >>> 0;
    h4 = (h4 + e) >>> 0; h5 = (h5 + f) >>> 0; h6 = (h6 + g) >>> 0; h7 = (h7 + h) >>> 0;
  }
  const digest = [h0, h1, h2, h3, h4, h5, h6, h7].map(value => value.toString(16).padStart(8, '0')).join('');
  return 'run-cont-' + digest.slice(0, 48);
}"""

RUN_OWNERSHIP_GUARD_JS = r"""function requestedRunOwnership(proposed, existing) {
  const isContinuation = proposed.created_via === 'CONTROL_TOWER_CONTINUATION';
  const exactContinuationReplay = Boolean(existing) && isContinuation &&
    String(existing.project_id || '') === String(proposed.project_id || '') &&
    String(existing.source_run_id || '') === String(proposed.source_run_id || '') &&
    String(existing.correlation_id || '') === String(proposed.correlation_id || '') &&
    String(existing.created_via || '') === 'CONTROL_TOWER_CONTINUATION';
  const ownershipConflict = Boolean(existing) && !exactContinuationReplay;
  return {ownership_ok: !ownershipConflict, continuation_replay: exactContinuationReplay,
    ownership_code: ownershipConflict ? 'RUN_ID_OWNERSHIP_CONFLICT' : ''};
}"""


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


def respond_node(name, pos, response_body="={{ JSON.stringify($json) }}", tv=2, response_code=None):
    parameters = {"respondWith": "json", "responseBody": response_body}
    if response_code is not None:
        parameters["options"] = {"responseCode": response_code}
    return node(
        name,
        "n8n-nodes-base.respondToWebhook",
        parameters,
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


def github_http_node(name, method, url, body_expr, pos, cred, send_body=True):
    """A GitHub API call through n8n's managed GitHub credential.

    The control center never receives this credential and no URL is accepted
    from the browser without first being normalized by the gateway code node.
    """
    p = {
        "method": method,
        "url": "=" + url,
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "githubApi",
        "sendHeaders": True,
        "headerParameters": {"parameters": [
            {"name": "Accept", "value": "application/vnd.github+json"},
            {"name": "X-GitHub-Api-Version", "value": "2022-11-28"},
        ]},
        "sendBody": send_body,
        "specifyBody": "json",
        "jsonBody": "={{ " + body_expr + " }}",
        "options": {},
    }
    return node(name, "n8n-nodes-base.httpRequest", p, pos, 4, {"githubApi": cred})


def ssh_exec_node(name, command, pos, cred):
    return node(
        name,
        "n8n-nodes-base.ssh",
        {"operation": "execute", "command": command, "authentication": "privateKey"},
        pos,
        1,
        {"sshPrivateKey": cred},
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
        self.cr_github = cfg.get("creds", {}).get("github_api")
        self.cr_ssh = cfg.get("creds", {}).get("runner_ssh")
        self.projects = cfg.get("tables", {}).get("projects", "")
        self.issues = cfg.get("tables", {}).get("issues", "")
        self.audit = cfg.get("tables", {}).get("audit", "")

    def rows(self, table):
        return "%s/api/v1/data-tables/%s/rows" % (self.n8n, table)

    def jobs(self):
        return self.adapter + "/v1/jobs"

    def wfid(self, name):
        return self.wf_ids.get(name, "PENDING_" + name)

    def batches(self):
        return self.adapter + "/v1/batches"

    def project_rows(self):
        return self.rows(self.projects)

    def issue_rows(self):
        return self.rows(self.issues)

    def audit_rows(self):
        return self.rows(self.audit)


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
        "value: s.issue.run_id}, {columnName: 'state', condition: 'neq', "
        "value: 'ABORTED'}], type: 'and'}, data: row, returnData: true, state: s}}];"
        % (state, current_job, extra_fields)
    )
    c = code_node(name_prefix + " Prep", js, pos)
    h = http_node(
        name_prefix + " Update",
        "PATCH",
        cfg.rows(cfg.runs) + "/update",
        "JSON.stringify($json)",
        (pos[0] + 1, pos[1]),
        cfg.cr_n8n,
    )
    # PATCH returns an empty array when the terminal ABORTED row wins the
    # race. Keep one input item so the restore node can observe that result;
    # it then emits no item and stops the stale orchestrator branch.
    h["alwaysOutputData"] = True
    r = code_node(
        name_prefix + " Restore",
        "const result = $json;\n"
        "const persisted = Array.isArray(result) ? result.length > 0 : "
        "result === true || (result && typeof result === 'object' && "
        "Object.keys(result).length > 0);\n"
        "if (!persisted) return [];\n"
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
const requestedRunId = typeof task.run_id === 'string' && /^run-[A-Za-z0-9_-]{1,60}$/.test(task.run_id) ? task.run_id : '';
const runId = requestedRunId || 'run-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
const issue = {
  contract: 'autodev.issue.v1', version: 'v1', run_id: runId,
  task_ref: task.task_ref || '', repository_ref: task.repository_ref || '',
  workspace: task.workspace || 'autodev-v2',
  task_description: task.task_description || '',
  acceptance_hint: task.acceptance_hint || '',
  max_attempts: task.max_attempts || 2,
  created_at: now.toISOString(),
  trace_id: 'trace-' + runId, source: 'autodev-start-api',
  'x-metadata': {project_id: task.project_id || '', project_mode: task.project_mode || 'MANUAL',
    changes_expected: typeof task.changes_expected === 'boolean' ? task.changes_expected : undefined,
    no_change_required: task.no_change_required === true,
    benchmark_fixture: task.benchmark_fixture || (task['x-metadata'] && task['x-metadata'].benchmark_fixture) || null,
    issue_number: task.issue_number || '', correlation_id: task.correlation_id ||
      (task['x-metadata'] && task['x-metadata'].correlation_id) || '',
    source_run_id: task.source_run_id || (task['x-metadata'] && task['x-metadata'].source_run_id) || '',
    continuation_reason: task.continuation_reason || (task['x-metadata'] && task['x-metadata'].continuation_reason) || '',
    requested_action: task.requested_action || (task['x-metadata'] && task['x-metadata'].requested_action) || '',
    created_via: task.created_via || (task['x-metadata'] && task['x-metadata'].created_via) || 'CONTROL_TOWER_START',
    requested_by: task.requested_by || (task['x-metadata'] && task['x-metadata'].requested_by) || ''},
};
"""
        + JS_VALIDATOR
        + """
const schema = %s;
const v = validateAutodevContract(issue, schema);
const envelopeAdaptive = raw.adaptive_metadata || null;
const taskAdaptive = (task['x-metadata'] && task['x-metadata'].adaptive_metadata) || null;
const adaptiveMetadata = envelopeAdaptive || taskAdaptive;
const adaptiveSchema = %s;
const adaptiveValidation = adaptiveMetadata === null
  ? {ok: true, errors: []}
  : validateAutodevContract(adaptiveMetadata, adaptiveSchema);
const adaptiveFields = ['experiment_id','benchmark_task_id','benchmark_split','candidate_id','factor','context_policy','repo_explorer_policy','experience_policy','config_hash','task_set_hash','harness_version'];
const adaptiveBindingValid = envelopeAdaptive === null || taskAdaptive === null ||
  adaptiveFields.every((key) => envelopeAdaptive[key] === taskAdaptive[key]);
if (adaptiveValidation.ok && adaptiveMetadata !== null) {
  issue['x-metadata'].adaptive_metadata = adaptiveMetadata;
}
const fixture = (raw.fixture && ['invalid_plan','verify_fail_delta','verify_fail_no_delta','no_signature','attempt_limit','security_critical_blocking','review_fix','review_split'].includes(raw.fixture)) ? raw.fixture : null;
const backend = (raw.backend === 'embedded' || raw.backend === 'opencode-builder-8001') ? raw.backend : 'opencode-builder-8001';
const taskMetadata = task['x-metadata'] && typeof task['x-metadata'] === 'object' ? task['x-metadata'] : {};
const envelopeMetadata = raw['x-metadata'] && typeof raw['x-metadata'] === 'object' ? raw['x-metadata'] : {};
const hasOwn = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const firstExplicit = (key) => hasOwn(task, key) ? task[key] : (hasOwn(raw, key) ? raw[key] : undefined);
const requestedProvider = firstExplicit('provider');
const requestedModel = firstExplicit('model');
const provider = requestedProvider === undefined || requestedProvider === null ? null : requestedProvider;
const model = requestedModel === undefined || requestedModel === null ? null : requestedModel;
const modelRevision = firstExplicit('model_revision') === undefined || firstExplicit('model_revision') === null ? null : firstExplicit('model_revision');
const providerValid = provider === null || (typeof provider === 'string' && /^[A-Za-z0-9._/-]{1,64}$/.test(provider));
const modelValid = model === null || (typeof model === 'string' && /^[A-Za-z0-9._/@:-]{1,128}$/.test(model));
const modelRevisionValid = modelRevision === null || (typeof modelRevision === 'string' && /^[A-Za-z0-9._/-]{1,64}$/.test(modelRevision));
const explicitMetadata = (key) => {
  const taskHas = hasOwn(taskMetadata, key);
  const envelopeHas = hasOwn(envelopeMetadata, key);
  if (taskHas && envelopeHas && JSON.stringify(taskMetadata[key]) !== JSON.stringify(envelopeMetadata[key])) return {value: taskMetadata[key], contradiction: true};
  return {value: taskHas ? taskMetadata[key] : (envelopeHas ? envelopeMetadata[key] : undefined), contradiction: false};
};
const routePolicyField = explicitMetadata('route_policy');
const expectedProviderField = explicitMetadata('expected_provider');
const expectedModelField = explicitMetadata('expected_model');
const routePolicy = routePolicyField.value;
const expectedProvider = expectedProviderField.value;
const expectedModel = expectedModelField.value;
const adaptiveRouteLocked = routePolicy === 'FAIL_CLOSED' && adaptiveMetadata !== null;
const routeBindingErrors = [];
if (routePolicyField.contradiction || expectedProviderField.contradiction || expectedModelField.contradiction) routeBindingErrors.push('ROUTE_BINDING_REBIND');
if (routePolicy !== undefined && routePolicy !== 'FAIL_CLOSED') routeBindingErrors.push('ROUTE_POLICY_INVALID');
if (expectedProvider !== undefined && (typeof expectedProvider !== 'string' || !providerValid || provider !== expectedProvider)) routeBindingErrors.push('ROUTE_BINDING_REBIND');
if (expectedModel !== undefined && (typeof expectedModel !== 'string' || !modelValid || model !== expectedModel)) routeBindingErrors.push('ROUTE_BINDING_REBIND');
if (adaptiveRouteLocked && (provider === null || model === null || expectedProvider !== provider || expectedModel !== model)) routeBindingErrors.push('ROUTE_BINDING_REBIND');
const deepseekRequested = /deepseek/i.test(String(provider || '')) || /deepseek/i.test(String(model || ''));
const intakeErrors = (deepseekRequested ? v.errors.concat(['DEEPSEEK_RETIRED']) : v.errors)
  .concat(providerValid ? [] : ['BAD_PROVIDER'])
  .concat(modelValid ? [] : ['BAD_MODEL'])
  .concat(modelRevisionValid ? [] : ['BAD_MODEL_REVISION'])
  .concat(routeBindingErrors)
  .concat(adaptiveValidation.errors || [])
  .concat(adaptiveBindingValid ? [] : ['ADAPTIVE_METADATA_REBIND']);
if (routePolicy !== undefined) issue['x-metadata'].route_policy = routePolicy;
if (expectedProvider !== undefined) issue['x-metadata'].expected_provider = expectedProvider;
if (expectedModel !== undefined) issue['x-metadata'].expected_model = expectedModel;
return [{ json: { intake_valid: v.ok && adaptiveValidation.ok && adaptiveBindingValid && providerValid && modelValid && modelRevisionValid && routeBindingErrors.length === 0 && !deepseekRequested, errors: intakeErrors, issue: issue,
  fixture: fixture, backend: backend, provider: provider, model: model,
  model_revision: modelRevision, run_id: runId } }];
"""
        % (embed_schema("autodev.issue.v1"), embed_schema("autodev.adaptive-metadata.v1"))
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
  data: [{run_id: s.issue.run_id, project_id: (s.issue['x-metadata'] || {}).project_id || '',
  issue_number: (s.issue['x-metadata'] || {}).issue_number || '', state: 'ACCEPTED', task_ref: s.issue.task_ref || '',
  repository_ref: s.issue.repository_ref || '', current_job: 'intake', decision: '',
  reason_code: 'INTAKE_OK', created_at: s.issue.created_at, updated_at: s.issue.created_at,
  result_ref: '', trace_id: s.issue.trace_id || '', backend: s.backend,
  correlation_id: (s.issue['x-metadata'] || {}).correlation_id || '',
  source_run_id: (s.issue['x-metadata'] || {}).source_run_id || '',
  continuation_reason: (s.issue['x-metadata'] || {}).continuation_reason || '',
  requested_action: (s.issue['x-metadata'] || {}).requested_action || '',
  created_via: (s.issue['x-metadata'] || {}).created_via || 'CONTROL_TOWER_START',
  requested_by: (s.issue['x-metadata'] || {}).requested_by || '',
  experiment_id: ((s.issue['x-metadata'] || {}).adaptive_metadata || {}).experiment_id || '',
  benchmark_task_id: ((s.issue['x-metadata'] || {}).adaptive_metadata || {}).benchmark_task_id || '',
  benchmark_split: ((s.issue['x-metadata'] || {}).adaptive_metadata || {}).benchmark_split || '',
  candidate_id: ((s.issue['x-metadata'] || {}).adaptive_metadata || {}).candidate_id || '',
  factor: ((s.issue['x-metadata'] || {}).adaptive_metadata || {}).factor || '',
  config_hash: ((s.issue['x-metadata'] || {}).adaptive_metadata || {}).config_hash || '',
  task_set_hash: ((s.issue['x-metadata'] || {}).adaptive_metadata || {}).task_set_hash || '',
  harness_version: ((s.issue['x-metadata'] || {}).adaptive_metadata || {}).harness_version || '',
  context_policy: ((s.issue['x-metadata'] || {}).adaptive_metadata || {}).context_policy || '',
  repo_explorer_policy: ((s.issue['x-metadata'] || {}).adaptive_metadata || {}).repo_explorer_policy || '',
  experience_policy: ((s.issue['x-metadata'] || {}).adaptive_metadata || {}).experience_policy || ''}], returnType: 'all'}}];""",
            P(2, 1),
        )
    )
    wf.add_node(
        http_node(
            "Fetch Requested Run",
            "GET",
            cfg.rows(cfg.runs),
            "{}",
            P(3, 1),
            cfg.cr_n8n,
            send_body=False,
            params_extra={
                "url": cfg.rows(cfg.runs), "sendQuery": True,
                "queryParameters": {"parameters": [{"name": "filter", "value": "={{ JSON.stringify({filters:[{columnName:'run_id',condition:'eq',value:$('Prepare Run Row').first().json.data[0].run_id}]}) }}"}]},
            },
        )
    )
    wf.nodes[-1]["alwaysOutputData"] = True
    wf.add_node(
        code_node(
            "Guard Requested Run Ownership",
            RUN_OWNERSHIP_GUARD_JS + """
const carrier=$('Prepare Run Row').first().json,proposed=(carrier.data||[])[0]||{},raw=$json;
const rows=Array.isArray(raw.data)?raw.data:[],existing=rows[0]||null;
return[{json:{...carrier,existing_run:existing,...requestedRunOwnership(proposed,existing)}}];""",
            P(4, 1),
        )
    )
    wf.add_node(bool_if("Requested Run Ownership Allowed?", "$json.ownership_ok === true", P(5, 1)))
    wf.add_node(respond_node("Respond Run ID Ownership Conflict", P(6, 2), "={{ JSON.stringify({status:'error',code:$json.ownership_code||'RUN_ID_OWNERSHIP_CONFLICT',run_id:(($json.data||[])[0]||{}).run_id,project_id:(($json.data||[])[0]||{}).project_id}) }}"))
    wf.add_node(bool_if("Continuation Intake Replay?", "$json.continuation_replay === true", P(6, 1)))
    wf.add_node(respond_node("Respond Existing Continuation", P(7, 2), "={{ JSON.stringify({run_id:($json.existing_run||{}).run_id,status:'ACCEPTED',replay:true,status_url:'" + cfg.webhook + "/webhook/autodev/status?run_id=' + ($json.existing_run||{}).run_id}) }}"))
    wf.add_node(
        http_node(
            "Insert Run Row",
            "POST",
            cfg.rows(cfg.runs) + "/upsert",
            "JSON.stringify({filter:{filters:[{columnName:'run_id',condition:'eq',value:$json.data[0].run_id}]},data:$json.data[0],returnData:true})",
            P(7, 1),
            cfg.cr_n8n,
        )
    )
    wf.nodes[-1]["alwaysOutputData"] = True
    wf.add_node(
        respond_node(
            "Respond 202",
            P(4, 0),
            "={{ JSON.stringify({ run_id: $('Prepare Run Row').first().json.data[0].run_id, status: 'ACCEPTED', status_url: '"
            + cfg.webhook
            + "/webhook/autodev/status?run_id=' + $('Prepare Run Row').first().json.data[0].run_id }) }}",
            response_code=202,
        )
    )
    wf.add_node(
        code_node(
            "Restore Intake Carrier",
            "const original=$('Prepare Run Row').first().json,row=(original.data||[])[0]||{};return[{json:{...original,run_id:row.run_id}}];",
            P(4, 0),
        )
    )
    wf.add_node(
        execute_wf_node(
            cfg,
            "Run Orchestrator",
            "01 AutoDev Orchestrator",
            P(5, 0),
            {"executeOnce": True, "waitForSubWorkflow": False},
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
    wf.add("Prepare Run Row", "Fetch Requested Run")
    wf.add("Fetch Requested Run", "Guard Requested Run Ownership")
    wf.add("Guard Requested Run Ownership", "Requested Run Ownership Allowed?")
    wf.add("Requested Run Ownership Allowed?", "Respond Run ID Ownership Conflict", 1)
    wf.add("Requested Run Ownership Allowed?", "Continuation Intake Replay?", 0)
    wf.add("Continuation Intake Replay?", "Respond Existing Continuation", 0)
    wf.add("Continuation Intake Replay?", "Insert Run Row", 1)
    wf.add("Insert Run Row", "Respond 202")
    wf.add("Insert Run Row", "Restore Intake Carrier")
    wf.add("Restore Intake Carrier", "Pass Intake")
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
  adaptive_metadata: (issue['x-metadata'] || {}).adaptive_metadata || null,
  run_row: {state: 'ACCEPTED', project_id: (issue['x-metadata'] || {}).project_id || '', issue_number: (issue['x-metadata'] || {}).issue_number || '', task_ref: issue.task_ref || '', repository_ref: issue.repository_ref || '', current_job: 'baseline', reason_code: 'INTAKE_OK', correlation_id: (issue['x-metadata'] || {}).correlation_id || '', source_run_id: (issue['x-metadata'] || {}).source_run_id || '', continuation_reason: (issue['x-metadata'] || {}).continuation_reason || '', requested_action: (issue['x-metadata'] || {}).requested_action || '', created_via: (issue['x-metadata'] || {}).created_via || 'CONTROL_TOWER_START', requested_by: (issue['x-metadata'] || {}).requested_by || '', experiment_id: ((issue['x-metadata'] || {}).adaptive_metadata || {}).experiment_id || '', benchmark_task_id: ((issue['x-metadata'] || {}).adaptive_metadata || {}).benchmark_task_id || '', benchmark_split: ((issue['x-metadata'] || {}).adaptive_metadata || {}).benchmark_split || '', candidate_id: ((issue['x-metadata'] || {}).adaptive_metadata || {}).candidate_id || '', factor: ((issue['x-metadata'] || {}).adaptive_metadata || {}).factor || '', config_hash: ((issue['x-metadata'] || {}).adaptive_metadata || {}).config_hash || '', task_set_hash: ((issue['x-metadata'] || {}).adaptive_metadata || {}).task_set_hash || '', harness_version: ((issue['x-metadata'] || {}).adaptive_metadata || {}).harness_version || '', context_policy: ((issue['x-metadata'] || {}).adaptive_metadata || {}).context_policy || '', repo_explorer_policy: ((issue['x-metadata'] || {}).adaptive_metadata || {}).repo_explorer_policy || '', experience_policy: ((issue['x-metadata'] || {}).adaptive_metadata || {}).experience_policy || ''},
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
    build_runner = execute_wf_node(
        cfg, "Run Build", "40 AutoDev Build", P(18, 0), {"executeOnce": True}
    )
    # A rejected adapter dispatch is a terminal build failure, not a reason
    # to leave the canonical run stuck in BUILDING.  Continue with the
    # existing Post-Build -> Build Failed state transition so the adapter
    # error remains visible in n8n execution data while the run is terminal.
    build_runner["onError"] = "continueRegularOutput"
    wf.add_node(build_runner)
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

    # A successful run is followed by a canonical project reassessment.  The
    # reassessment workflow owns the GitHub refresh and AUTO/MANUAL decision;
    # the browser never advances a project locally.
    wf.add_node(
        http_node(
            "Project Reassessment",
            "POST",
            cfg.webhook + "/webhook/autodev/project/reassess",
            "JSON.stringify({project_id: (($json.issue || {})['x-metadata'] || {}).project_id || '', project_mode: (($json.issue || {})['x-metadata'] || {}).project_mode || 'MANUAL', repository_url: ($json.issue || {}).repository_ref || '', run_id: ($json.issue || {}).run_id || ''})",
            P(36, 2),
            cfg.cr_api,
        )
    )
    wf.add("Done State Restore", "Project Reassessment")

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
  adaptive_metadata: (input['x-metadata'] || {}).adaptive_metadata || null,
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
    adaptive_metadata: rec.adaptive_metadata || null,
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
    adaptive_metadata: s.adaptive_metadata || null,
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
const expectedAdaptive = (issue['x-metadata'] || {}).adaptive_metadata || null;
const observedAdaptive = (plan['x-metadata'] || {}).adaptive_metadata ||
  (s.job_record || {}).adaptive_metadata || null;
const reasons = [];
if (plan.run_id !== issue.run_id) reasons.push('PLAN_RUN_ID_MISMATCH');
if (baselineHead && plan.repository_head !== baselineHead) reasons.push('PLAN_HEAD_MISMATCH');
if (!plan.acceptance_criteria || !plan.acceptance_criteria.length) reasons.push('ACCEPTANCE_CRITERIA_MISSING');
if (!plan.build_scope || !plan.build_scope.allowed_files || !plan.build_scope.allowed_files.length) reasons.push('BUILD_SCOPE_MISSING');
if (!plan.required_tests || !plan.required_tests.length) reasons.push('REQUIRED_TESTS_INVALID');
if (!plan.context || !plan.context.fingerprint) reasons.push('CONTEXT_FINGERPRINT_MISSING');
if (plan.safety && (plan.safety.sentinel_absent !== true || plan.safety.repo_unchanged !== true)) reasons.push('FORBIDDEN_MUTATION');
const adaptiveFields = ['experiment_id','benchmark_task_id','benchmark_split','candidate_id','factor','context_policy','repo_explorer_policy','experience_policy','config_hash','task_set_hash','harness_version'];
if (expectedAdaptive && adaptiveFields.some((key) => (observedAdaptive || {})[key] !== expectedAdaptive[key])) reasons.push('ADAPTIVE_METADATA_MISMATCH');
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
  failure_context: null,
  'x-metadata': {adaptive_metadata: (issue['x-metadata'] || {}).adaptive_metadata || null}
};
return [{json: {
  run_id: issue.run_id, job_id: issue.run_id + ':build:' + ((s.attempt_build || 0) + 1),
  job_type: 'build', attempt_id: input.attempt_id,
  input_contract: 'autodev.build-input.v1', input: input,
  backend: s.backend || 'opencode-builder-8001', fixture: s.fixture || null,
  provider: (s.provider || null),
  model: (s.model || null),
  model_revision: (s.model_revision || null),
  adaptive_metadata: (input['x-metadata'] || {}).adaptive_metadata || null,
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
  strategy_delta: null, failure_context: null,
  'x-metadata': {adaptive_metadata: (issue['x-metadata'] || {}).adaptive_metadata || null}
};
return [{json: {
  run_id: issue.run_id, job_id: issue.run_id + ':verify:' + attemptId.split(':').pop(),
  job_type: 'verify', attempt_id: attemptId,
  input_contract: 'autodev.build-input.v1', input: input,
  backend: s.backend || 'opencode-builder-8001', fixture: s.fixture || null,
  provider: (s.provider || null),
  model: (s.model || null),
  model_revision: (s.model_revision || null),
  adaptive_metadata: (input['x-metadata'] || {}).adaptive_metadata || null,
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
  },
  'x-metadata': {adaptive_metadata: (issue['x-metadata'] || {}).adaptive_metadata || null}
};
return [{json: {
  run_id: issue.run_id, job_id: issue.run_id + ':fix:' + attemptNo,
  job_type: 'fix', attempt_id: input.attempt_id,
  input_contract: 'autodev.build-input.v1', input: input,
  backend: s.backend || 'opencode-builder-8001', fixture: s.fixture || null,
  provider: (s.provider || null),
  model: (s.model || null),
  model_revision: (s.model_revision || null),
  adaptive_metadata: (input['x-metadata'] || {}).adaptive_metadata || null,
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
  adaptive_metadata: (s.issue['x-metadata'] || {}).adaptive_metadata || null,
  task_class: 'research',
  timeout_s: 600
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
            + "/v1/batches/{{ $json.data ? $json.data.batch_id : $json.batch_id }}?polls={{ $json.polls || 0 }}",
            "{}",
            P(3, 0),
            cfg.cr_harness,
            send_body=False,
            params_extra={
                "url": cfg.adapter
                + "/v1/batches/{{ $json.data ? $json.data.batch_id : $json.batch_id }}?polls={{ $json.polls || 0 }}"
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
        lim = num_if("Limit?", "$json.polls", "gte", 240, P(8, 0))
        timeout = code_node(
            "Timeout",
            """const s = $json;
return [{json: {ok: false, failure_class: 'TIMEOUT',
  failure_signature: 'POLL_TIMEOUT', error: 'poll limit reached'}}];""",
            P(9, 0),
        )
        for n in (w, poll, parse, done, failed, inc, lim, timeout):
            wf.add_node(n)
        retry = bool_if(
            "Retry Interrupted?",
            "!String($json.batch_id || '').includes(':recovery-')",
            P(6, 1),
        )
        recover = code_node(
            "Prepare Research Recovery",
            """const s = $json;
const original = (($items('Prep Research Batch')[0] || {}).json || {});
const recovery = 1;
const jobs = (original.jobs || []).map((job) => {
  const area = String(job.job_type || 'research.unknown').split('.').pop();
  const id = original.run_id + ':research.' + area + ':recovery-' + recovery;
  return Object.assign({}, job, {
    job_id: id,
    attempt_id: id,
    recovery_of: job.job_id
  });
});
return [{json: {
  run_id: original.run_id,
  batch_id: original.run_id + ':research-batch:recovery-' + recovery,
  jobs: jobs,
  barrier: 'all',
  recovery_of: s.batch_id,
  recovery_attempt: recovery
}}];""",
            P(7, 1),
        )
        wf.add_node(retry)
        wf.add_node(recover)
        wf.add(dispatch, w)
        wf.add(w, poll)
        wf.add(poll, parse)
        wf.add(parse, done)
        wf.add(done, failed, 1)
        wf.add(failed, retry, 0)
        wf.add(retry, recover, 0)
        wf.add(recover, dispatch)
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
        wf.add(retry, fail, 1)
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


# ============================================ Control Center runtime layer ==
def build_05_control_gateway(cfg):
    """n8n-owned, authenticated command boundary for the Control Tower."""
    wf = WF("05 AutoDev Control Gateway")
    P = lambda x, y: [x * 260, y * 170]  # noqa: E731
    wf.add_node(webhook_node("Control Webhook", "autodev/control", "POST", cfg.cr_api, P(0, 0)))
    wf.add_node(code_node("Validate Control Command", r"""const raw=$json.body||$json, e=raw&&typeof raw==='object'?raw:{}, p=e.payload;
const op=new Set(['START_PROJECT','START_ISSUE','START_REPO_ANALYSIS','START_BLUEPRINT_PROJECT','PAUSE_RUN','RESUME_RUN','ABORT_RUN','RETRY_STAGE','RETRY_RUN','EXCLUDE_MODEL_FOR_RUN','EXCLUDE_PROVIDER_FOR_RUN','APPROVE_HUMAN_GATE']);
const adm=new Set(['RUN_ROUTER_TEST','RUN_MCP_TEST','RUN_SYSTEM_TEST','REFRESH_CATALOG','SYNC_CREDENTIALS']);
const errors=[]; const command=e.command, role=e.actor&&e.actor.role;
if(e.contract!=='autodev.control-command.v1'||e.version!=='v1')errors.push('CONTRACT_INVALID');
if(!op.has(command)&&!adm.has(command))errors.push('COMMAND_NOT_ALLOWED');
if(!['OPERATOR','ADMIN'].includes(role))errors.push('ROLE_INVALID');
if(adm.has(command)&&role!=='ADMIN')errors.push('ROLE_FORBIDDEN');
if(!/^[A-Za-z0-9_.:-]{3,96}$/.test(String(e.correlation_id||'')))errors.push('CORRELATION_ID_INVALID');
if(!e.target||typeof e.target!=='object'||Array.isArray(e.target))errors.push('TARGET_INVALID');
const targetKeys=new Set(['run_id','project_id','issue_number']);
if(Object.keys(e.target||{}).some(k=>!targetKeys.has(k)))errors.push('TARGET_KEY_NOT_ALLOWED');
if(Object.values(e.target||{}).some(v=>(typeof v!=='string'&&typeof v!=='number')||typeof v==='boolean'||!/^[A-Za-z0-9_.:#-]{1,96}$/.test(String(v))))errors.push('TARGET_VALUE_INVALID');
if(!p||typeof p!=='object'||Array.isArray(p))errors.push('PAYLOAD_INVALID');
if(['PAUSE_RUN','ABORT_RUN','RETRY_STAGE','RETRY_RUN','EXCLUDE_MODEL_FOR_RUN','EXCLUDE_PROVIDER_FOR_RUN','APPROVE_HUMAN_GATE'].includes(command)&&!/^run-[A-Za-z0-9_-]{6,60}$/.test(String(p&&p.run_id||'')))errors.push('RUN_ID_INVALID');
if(command==='RESUME_RUN'){
  const continuationKeys=new Set(['project_id','source_run_id','run_id','issue_number','continuation_reason','requested_action']);
  if(Object.keys(p||{}).some(k=>!continuationKeys.has(k)))errors.push('CONTINUATION_FIELD_NOT_ALLOWED');
  if(!/^[A-Za-z0-9_.:#-]{1,96}$/.test(String(p&&p.project_id||'')))errors.push('PROJECT_ID_INVALID');
  if(!/^run-[A-Za-z0-9_-]{1,60}$/.test(String(p&&p.source_run_id||p&&p.run_id||'')))errors.push('SOURCE_RUN_ID_INVALID');
  if(p&&p.issue_number!==undefined&&!/^[A-Za-z0-9_.:#-]{1,96}$/.test(String(p.issue_number)))errors.push('ISSUE_NUMBER_INVALID');
  if(!String(p&&p.continuation_reason||'').trim()||String(p.continuation_reason).length>240)errors.push('CONTINUATION_REASON_INVALID');
  if(!String(p&&p.requested_action||'').trim()||String(p.requested_action).length>240)errors.push('REQUESTED_ACTION_INVALID');
}
const repo=String(p&&p.repository_url||''); let parts=[];
if(repo){const match=repo.match(/^https:\/\/github\.com\/([^/]+)\/([^/?#]+)$/);if(!match)errors.push('REPOSITORY_URL_INVALID');else parts=[match[1],match[2]]}
if(['START_ISSUE','START_REPO_ANALYSIS'].includes(command)&&!repo)errors.push('REPOSITORY_REQUIRED');
if(command==='START_ISSUE'&&!(/^#?[1-9][0-9]{0,8}$/.test(String(p&&p.issue||''))||/^https:\/\/github\.com\/[^/]+\/[^/]+\/issues\/[1-9][0-9]{0,8}$/.test(String(p&&p.issue||''))))errors.push('ISSUE_INVALID');
if(['START_PROJECT','START_BLUEPRINT_PROJECT'].includes(command)&&typeof(p&&p.blueprint_md)!=='string')errors.push('BLUEPRINT_REQUIRED');
if(typeof(p&&p.blueprint_md)==='string'&&p.blueprint_md.length>512000)errors.push('BLUEPRINT_TOO_LARGE');
if(Object.keys(p||{}).some(k=>/authorization|cookie|token|secret|password|api[_-]?key|private[_-]?key|reasoning|chain.?of.?thought/i.test(k)))errors.push('SECRET_FIELD_REJECTED');
if(/deepseek/i.test(String(p&&p.model||'')+' '+String(p&&p.provider||'')))errors.push('DEEPSEEK_RETIRED');
const issueRaw=String(p&&p.issue||''), issue=parts.length===2?(issueRaw.match(/\/issues\/([1-9][0-9]{0,8})$/)||[])[1]||issueRaw.replace(/^#/,''):'';
return [{json:{valid:!errors.length,errors,envelope:e,command,role,payload:p||{},github_owner:parts[0]||'',github_repo:parts[1]||'',issue_url:parts.length===2&&issue?`https://api.github.com/repos/${parts[0]}/${parts[1]}/issues/${issue}`:'',route:command,audit_row:{timestamp:new Date().toISOString(),actor:'control-tower',role,command,target:JSON.stringify(e.target||{}),project_id:p&&p.project_id||'',run_id:p&&p.run_id||'',result:errors.length?'REJECTED':'ACCEPTED',correlation_id:String(e.correlation_id||'')}}}];""", P(1, 0)))
    wf.add_node(bool_if("Command Valid?", "$json.valid === true", P(2, 0)))
    wf.add_node(respond_node("Reject Command", P(3, -1), "={{ JSON.stringify({status: 'error', code: 'COMMAND_REJECTED', errors: $json.errors || []}) }}"))
    wf.add_node(http_node("Persist Command Audit", "POST", cfg.audit_rows(), "JSON.stringify({data: [$json.audit_row], returnType: 'all'})", P(3, 1), cfg.cr_n8n))
    wf.add_node(code_node("Restore Valid Command", "const v=$('Validate Control Command').first().json; return [{json:v}];", P(4, 1)))
    wf.add("Control Webhook", "Validate Control Command"); wf.add("Validate Control Command", "Command Valid?"); wf.add("Command Valid?", "Reject Command", 1); wf.add("Command Valid?", "Persist Command Audit", 0); wf.add("Persist Command Audit", "Restore Valid Command")

    wf.add_node(if_node("Is Issue Start?", [{"leftValue":"={{$json.route}}","rightValue":"=START_ISSUE","operator":{"type":"string","operation":"equals"}}], P(5,1)))
    wf.add_node(github_http_node("Fetch GitHub Issue", "GET", "{{ $json.issue_url }}", "{}", P(6,1), cfg.cr_github, False))
    wf.add_node(code_node("Prepare Canonical Issue Start", r"""const v=$('Restore Valid Command').first().json,i=$json||{},p=v.payload,n=Number(p.issue||i.number||0),repositoryRef=String(p.repository_url||'').replace(/^https:\/\/github\.com\//,'').replace(/\/$/,''); const task={task_ref:`github:${v.github_owner}/${v.github_repo}#${n}`,repository_ref:repositoryRef,workspace:p.workspace||`${v.github_owner}-${v.github_repo}`,task_description:[i.title,i.body,p.additional_instruction].filter(Boolean).join('\n\n'),acceptance_hint:p.acceptance_hint||'',max_attempts:Number(p.max_attempts||2),'x-metadata':{project_id:p.project_id||'',project_mode:p.project_mode||'MANUAL',issue_number:n,correlation_id:v.envelope.correlation_id}}; return [{json:{start_request:{task,backend:p.backend||'opencode-builder-8001',fixture:p.fixture||null}}}];""", P(7,1)))
    wf.add_node(http_node("Start Canonical Run", "POST", cfg.webhook+"/webhook/autodev/start", "JSON.stringify($json.start_request)", P(8,1), cfg.cr_api))
    wf.add_node(code_node("Issue Start Result", "const v=$('Restore Valid Command').first().json; return [{json:{status:'ACCEPTED',command:v.command,correlation_id:v.envelope.correlation_id,result:$json,source:'n8n-control-gateway'}}];", P(9,1)))
    wf.add_node(respond_node("Respond Issue Start", P(10,1)))
    wf.add("Restore Valid Command", "Is Issue Start?"); wf.add("Is Issue Start?", "Fetch GitHub Issue", 0); wf.add("Fetch GitHub Issue", "Prepare Canonical Issue Start"); wf.add("Prepare Canonical Issue Start", "Start Canonical Run"); wf.add("Start Canonical Run", "Issue Start Result"); wf.add("Issue Start Result", "Respond Issue Start")

    wf.add_node(if_node("Is Router Test?", [{"leftValue":"={{$json.route}}","rightValue":"=RUN_ROUTER_TEST","operator":{"type":"string","operation":"equals"}}], P(5,2)))
    wf.add_node(http_node("Read Router Runtime", "GET", cfg.adapter+"/v1/status/runtime", "{}", P(6,2), cfg.cr_harness, send_body=False))
    router_test_js = r"""const r=$json.data||$json;
const providers=Array.isArray(r.providers)?r.providers:[];
const p=$('Restore Valid Command').first().json.payload||{};
const name=String(p.test||'Dynamischer Router');
const deep=providers.some(x=>/deepseek/i.test(String(x.provider||'')+' '+String(x.model||'')));
const free=providers.filter(x=>x.free_eligible===true&&x.catalog_eligible!==false&&x.router_eligible!==false);
const tools=free.filter(x=>x.capabilities&&x.capabilities.TOOL_CAPABLE===true);
const vision=free.filter(x=>x.capabilities&&x.capabilities.VISION_CAPABLE===true);
const structured=free.filter(x=>x.capabilities&&x.capabilities.STRUCTURED_OUTPUT_CAPABLE===true);
const healthy=providers.filter(x=>x.health==='HEALTHY');
const checksByTest={
  'Dynamischer Router':{free_first_enabled:r.free_first_enabled===true,eligible_free_route:free.length>0,paid_fallback_disabled:r.automatic_paid_agent_escalation===false,deepseek_excluded:!deep},
  'Modellkatalog':{catalog_observed:Boolean(r.checked_at),providers_observed:providers.length>0,deepseek_excluded:!deep},
  'Free Pool':{catalog_refreshed:Boolean(r.checked_at),eligible_zero_cost_count:free.length},
  'Credential-Erkennung':{provider_health_observed:healthy.length>0,credential_values_not_exposed:providers.every(x=>!('key' in x)&&!('token' in x)&&!('secret' in x))},
  'Capability Filter':{capabilities_observed:providers.some(x=>x.capabilities&&typeof x.capabilities==='object'),eligible_pool_bounded:free.length<=providers.length,deepseek_excluded:!deep},
  'Tool Routing':{tool_capable_zero_cost_selected:tools.length>0,free_route_available:free.length>0},
  'Vision Routing':{vision_capable_zero_cost_selected:vision.length>0,free_route_available:free.length>0},
  'Structured Output':{structured_output_zero_cost_available:structured.length>0,free_route_available:free.length>0},
  'Transport Failover':{free_route_available:free.length>0,lease_state_observed:Boolean(r.provider_lease_state),paid_fallback_disabled:r.automatic_paid_agent_escalation===false},
  'Semantic Failover':{free_route_available:free.length>0,lease_state_observed:Boolean(r.provider_lease_state),deepseek_excluded:!deep},
  'Run Blacklist':{quarantined_routes_excluded:free.every(x=>x.quarantined!==true),free_route_available:free.length>0},
  'Paid Fallback Sperre':{paid_fallback_unavailable:r.automatic_paid_agent_escalation===false,free_first_enabled:r.free_first_enabled===true},
  'DeepSeek Sperre':{catalog_ineligible:!deep,explicit_request_rejected:true,provider_contact:false},
};
const checks=checksByTest[name]||checksByTest['Dynamischer Router'];
const ok=name==='DeepSeek Sperre'?checks.catalog_ineligible&&checks.explicit_request_rejected&&!checks.provider_contact:Object.values(checks).every(x=>x===true||typeof x==='number'&&x>0);
return [{json:{status:ok?'OK':'NICHT_OK',module:'router',test:name,source:'adapter',checks,details:{diagnostic:name,provider_count:providers.length,healthy_provider_count:healthy.length,eligible_zero_cost:free.length,tool_capable_zero_cost:tools.length,vision_capable_zero_cost:vision.length,structured_output_zero_cost:structured.length,lease_state_observed:Boolean(r.provider_lease_state)}}}];"""
    wf.add_node(code_node("Router Test Result", router_test_js, P(7,2))); wf.add_node(respond_node("Respond Router Test", P(8,2)))
    wf.add("Is Issue Start?", "Is Router Test?", 1); wf.add("Is Router Test?", "Read Router Runtime", 0); wf.add("Read Router Runtime", "Router Test Result"); wf.add("Router Test Result", "Respond Router Test")

    wf.add_node(if_node("Is MCP Test?", [{"leftValue":"={{$json.route}}","rightValue":"=RUN_MCP_TEST","operator":{"type":"string","operation":"equals"}}], P(5,3)))
    if cfg.cr_ssh:
        wf.add_node(ssh_exec_node("Discover MCP Tools", "/usr/local/bin/opencode mcp list 2>&1", P(6,3), cfg.cr_ssh))
        wf.add_node(code_node("MCP Test Result", "const o=String($json.stdout||$json.data||''),requested=String(($('Restore Valid Command').first().json.payload||{}).test||''),failed=/permission denied|command not found|error/i.test(o),configured=!/No MCP servers configured/i.test(o),named=!requested||o.toLowerCase().includes(requested.toLowerCase()); return [{json:{status:!configured?'NICHT_KONFIGURIERT':!failed&&named?'OK':'NICHT_OK',module:'mcp',test:requested,checks:{server_configured:configured,named_server_tested:named,discovery:!failed},safe_error_message:!configured?'No MCP servers configured':failed?'MCP discovery failed':named?null:'requested MCP server was not observed'}}];", P(7,3)))
        wf.add("Is Router Test?", "Is MCP Test?", 1); wf.add("Is MCP Test?", "Discover MCP Tools", 0); wf.add("Discover MCP Tools", "MCP Test Result")
    else:
        wf.add_node(code_node("MCP Test Result", "return [{json:{status:'BLOCKIERT_EXTERN',module:'mcp',test:String(($('Restore Valid Command').first().json.payload||{}).test||''),checks:{server_configured:false},safe_error_message:'Runner SSH credential unavailable'}}];", P(7,3))); wf.add("Is Router Test?", "Is MCP Test?", 1); wf.add("Is MCP Test?", "MCP Test Result", 0)
    wf.add_node(respond_node("Respond MCP Test", P(8,3))); wf.add("MCP Test Result", "Respond MCP Test")

    wf.add_node(if_node("Is System Test?", [{"leftValue":"={{$json.route}}","rightValue":"=RUN_SYSTEM_TEST","operator":{"type":"string","operation":"equals"}}], P(5,4)))
    wf.add_node(http_node("Read n8n System Status", "GET", cfg.n8n+"/api/v1/workflows?limit=1", "{}", P(6,4), cfg.cr_n8n, send_body=False))
    wf.add_node(http_node("Read Adapter Runtime", "GET", cfg.adapter+"/v1/status/runtime", "{}", P(7,4), cfg.cr_harness, send_body=False))
    if cfg.cr_ssh:
        wf.add_node(ssh_exec_node("Discover MCP Tools System Test", "/usr/local/bin/opencode mcp list 2>&1", P(8,4), cfg.cr_ssh))
        system_input = "const n=$('Read n8n System Status').first().json.data||$('Read n8n System Status').first().json,a=$('Read Adapter Runtime').first().json.data||$('Read Adapter Runtime').first().json,m=String($json.stdout||$json.data||''),n8nOk=Array.isArray(n)||Array.isArray(n.data),adapterOk=Boolean(a)&&a.free_first_enabled===true&&a.automatic_paid_agent_escalation===false,deepseekOk=a.deepseek_policy&&Object.values(a.deepseek_policy).every(v=>v===false),routerOk=adapterOk&&deepseekOk&&Array.isArray(a.providers)&&a.providers.some(p=>p.free_eligible===true),opencodeOk=a.ct8001_reachable===true&&a.opencode_binary_present===true&&/^\\d+\\.\\d+\\.\\d+/.test(String(a.opencode_version||'')),mcpConfigured=Boolean(m)&&!/No MCP servers configured/i.test(m),mcpStatus=mcpConfigured?( /permission denied|command not found|error/i.test(m)?'NICHT_OK':'OK'):'NICHT_KONFIGURIERT',modules={n8n:n8nOk?'OK':'NICHT_OK',adapter:adapterOk?'OK':'NICHT_OK',opencode:opencodeOk?'OK':'NICHT_OK',router:routerOk?'OK':'NICHT_OK',mcp:mcpStatus},ok=n8nOk&&adapterOk&&opencodeOk&&routerOk;return[{json:{status:ok?'OK':'NICHT_OK',overall:ok?'OK':'NICHT_OK',modules,optional_modules:mcpStatus==='NICHT_KONFIGURIERT'?['MCP']:[],source:'n8n-diagnostic-workflow',details:{n8n:n8nOk?'workflow API reachable':'workflow API unavailable',adapter:adapterOk?'runtime reachable':'runtime policy or adapter unavailable',opencode:opencodeOk?'CT8001 and OpenCode executable reachable':'OpenCode worker unavailable',router:routerOk?'eligible free route and deny policy valid':'router policy invalid or no eligible free route',mcp:mcpStatus}}}];"
    else:
        system_input = "const n=$('Read n8n System Status').first().json.data||$('Read n8n System Status').first().json,a=$json.data||$json,n8nOk=Array.isArray(n)||Array.isArray(n.data),adapterOk=Boolean(a)&&a.free_first_enabled===true&&a.automatic_paid_agent_escalation===false,deepseekOk=a.deepseek_policy&&Object.values(a.deepseek_policy).every(v=>v===false),opencodeOk=a.ct8001_reachable===true&&a.opencode_binary_present===true&&/^\\d+\\.\\d+\\.\\d+/.test(String(a.opencode_version||'')),routerOk=adapterOk&&deepseekOk&&Array.isArray(a.providers)&&a.providers.some(p=>p.free_eligible===true),modules={n8n:n8nOk?'OK':'NICHT_OK',adapter:adapterOk?'OK':'NICHT_OK',opencode:opencodeOk?'OK':'NICHT_OK',router:routerOk?'OK':'NICHT_OK',mcp:'BLOCKIERT_EXTERN'},ok=n8nOk&&adapterOk&&opencodeOk&&routerOk;return[{json:{status:ok?'OK':'NICHT_OK',overall:ok?'OK':'NICHT_OK',modules,optional_modules:['MCP'],source:'n8n-diagnostic-workflow',details:{n8n:n8nOk?'workflow API reachable':'workflow API unavailable',adapter:adapterOk?'runtime reachable':'runtime policy or adapter unavailable',opencode:opencodeOk?'CT8001 and OpenCode executable reachable':'OpenCode worker unavailable',router:routerOk?'eligible free route and deny policy valid':'router policy invalid or no eligible free route',mcp:'SSH diagnostic unavailable'}}}];"
    wf.add_node(code_node("System Test Result", system_input, P(9,4))); wf.add_node(respond_node("Respond System Test", P(10,4)))
    wf.add("Is MCP Test?", "Is System Test?", 1); wf.add("Is System Test?", "Read n8n System Status", 0); wf.add("Read n8n System Status", "Read Adapter Runtime");
    if cfg.cr_ssh: wf.add("Read Adapter Runtime", "Discover MCP Tools System Test"); wf.add("Discover MCP Tools System Test", "System Test Result")
    else: wf.add("Read Adapter Runtime", "System Test Result")
    wf.add("System Test Result", "Respond System Test")

    # Administrative mutations remain canonical n8n actions and call the
    # authenticated adapter boundary; the browser never controls providers.
    wf.add_node(if_node("Is Catalog Refresh?", [{"leftValue":"={{$json.route}}","rightValue":"=REFRESH_CATALOG","operator":{"type":"string","operation":"equals"}}], P(5,5)))
    wf.add_node(http_node("Refresh Provider Catalog", "POST", cfg.adapter+"/v1/catalog/refresh", "JSON.stringify({correlation_id:$json.envelope.correlation_id})", P(6,5), cfg.cr_harness))
    wf.add_node(code_node("Catalog Refresh Result", "const v=$('Restore Valid Command').first().json;return[{json:{status:$json.status||'NICHT_OK',module:'catalog',test:'REFRESH_CATALOG',command:v.command,correlation_id:v.envelope.correlation_id,result:$json,source:'n8n-control-gateway'}}];", P(7,5)))
    wf.add_node(respond_node("Respond Catalog Refresh", P(8,5)))
    wf.add_node(if_node("Is Credential Sync?", [{"leftValue":"={{$json.route}}","rightValue":"=SYNC_CREDENTIALS","operator":{"type":"string","operation":"equals"}}], P(5,6)))
    wf.add_node(http_node("Sync Provider Credentials", "POST", cfg.adapter+"/v1/credentials/sync", "JSON.stringify({correlation_id:$json.envelope.correlation_id})", P(6,6), cfg.cr_harness))
    wf.add_node(code_node("Credential Sync Result", "const v=$('Restore Valid Command').first().json;return[{json:{status:$json.status||'NICHT_OK',module:'credentials',test:'SYNC_CREDENTIALS',command:v.command,correlation_id:v.envelope.correlation_id,result:$json,source:'n8n-control-gateway'}}];", P(7,6)))
    wf.add_node(respond_node("Respond Credential Sync", P(8,6)))
    system_connections = wf.connections.get("Is System Test?", {}).get("main", [[]])
    wf.connections["Is System Test?"] = {"main": [system_connections[0] if system_connections else [], []]}
    wf.add("Is System Test?", "Is Catalog Refresh?", 1); wf.add("Is Catalog Refresh?", "Refresh Provider Catalog", 0); wf.add("Refresh Provider Catalog", "Catalog Refresh Result"); wf.add("Catalog Refresh Result", "Respond Catalog Refresh")
    wf.add("Is Catalog Refresh?", "Is Credential Sync?", 1); wf.add("Is Credential Sync?", "Sync Provider Credentials", 0); wf.add("Sync Provider Credentials", "Credential Sync Result"); wf.add("Credential Sync Result", "Respond Credential Sync"); wf.add("Is Credential Sync?", "Is Repo Analysis?", 1)

    wf.add_node(if_node("Is Repo Analysis?", [{"leftValue":"={{$json.route}}","rightValue":"=START_REPO_ANALYSIS","operator":{"type":"string","operation":"equals"}}], P(5,5)))
    wf.add_node(github_http_node("Fetch Repository Issues", "GET", "https://api.github.com/repos/{{ $json.github_owner }}/{{ $json.github_repo }}/issues?state=open&per_page=100", "{}", P(6,5), cfg.cr_github, False))
    wf.add_node(code_node("Pack Repository Issues", "const items=$input.all();return[{json:{issues:items.map(item=>item.json)}}];", P(7,5)))
    wf.add_node(http_node("Run Project Analysis", "POST", cfg.webhook+"/webhook/autodev/project/analyse", "JSON.stringify({envelope: $('Restore Valid Command').first().json.envelope, issues: $json.issues})", P(8,5), cfg.cr_api))
    wf.add("Is Repo Analysis?", "Fetch Repository Issues", 0); wf.add("Fetch Repository Issues", "Pack Repository Issues"); wf.add("Pack Repository Issues", "Run Project Analysis"); wf.add_node(respond_node("Respond Repo Analysis", P(9,5))); wf.add("Run Project Analysis", "Respond Repo Analysis")

    wf.add_node(bool_if("Is Blueprint Start?", "$json.route === 'START_BLUEPRINT_PROJECT' || $json.route === 'START_PROJECT'", P(5,6)))
    wf.add_node(http_node("Run Blueprint Bootstrap", "POST", cfg.webhook+"/webhook/autodev/project/blueprint", "JSON.stringify($('Restore Valid Command').first().json.envelope)", P(6,6), cfg.cr_api))
    wf.add("Is Repo Analysis?", "Is Blueprint Start?", 1); wf.add("Is Blueprint Start?", "Run Blueprint Bootstrap", 0); wf.add("Run Blueprint Bootstrap", "Respond Repo Analysis")
    wf.add_node(if_node("Is Project Resume?", [{"leftValue":"={{$json.route}}","rightValue":"=RESUME_RUN","operator":{"type":"string","operation":"equals"}}], P(5,7)))
    wf.add_node(http_node("Reassess Project", "POST", cfg.webhook+"/webhook/autodev/project/reassess", "JSON.stringify(Object.assign({}, $('Restore Valid Command').first().json.envelope.payload, {command: 'RESUME_RUN', correlation_id: $('Restore Valid Command').first().json.envelope.correlation_id, requested_by: $('Restore Valid Command').first().json.role}))", P(6,7), cfg.cr_api))
    wf.add_node(code_node("Project Resume Result", "const v=$('Restore Valid Command').first().json;return[{json:{status:$json.status||'ACCEPTED',command:v.command,correlation_id:v.envelope.correlation_id,result:$json,source:'n8n-project-reassessment'}}];", P(7,7)))
    wf.add_node(respond_node("Respond Project Resume", P(8,7)))
    wf.add_node(if_node("Is Canonical Run Action?", [{"leftValue":"={{['PAUSE_RUN','RESUME_RUN','ABORT_RUN','RETRY_STAGE','RETRY_RUN','EXCLUDE_MODEL_FOR_RUN','EXCLUDE_PROVIDER_FOR_RUN','APPROVE_HUMAN_GATE'].includes($json.route)}}","rightValue":"=true","operator":{"type":"boolean","operation":"equals"}}], P(5,8)))
    wf.add_node(code_node("Prepare Canonical Run Action", "const v=$('Restore Valid Command').first().json,p=v.payload||{},runId=String(p.run_id||''),filter={type:'and',filters:[{columnName:'run_id',condition:'eq',value:runId}]};return[{json:{command:v.command,correlation_id:v.envelope.correlation_id,run_id:runId,payload:p,filter,requested_at:new Date().toISOString()}}];", P(6,8)))
    wf.add_node(http_node("Fetch Canonical Run", "GET", cfg.rows(cfg.runs), "{}", P(7,8), cfg.cr_n8n, send_body=False, params_extra={"url": cfg.rows(cfg.runs), "sendQuery": True, "queryParameters": {"parameters": [{"name": "filter", "value": "={{ JSON.stringify($json.filter) }}"}]}}))
    wf.nodes[-1]["alwaysOutputData"] = True
    wf.add_node(code_node("Check Canonical Run", "const p=$('Prepare Canonical Run Action').first().json,rows=Array.isArray($json.data)?$json.data:[];return[{json:{...p,run_found:rows.length>0,existing_run:rows[0]||null}}];", P(8,8)))
    wf.add_node(bool_if("Canonical Run Found?", "$json.run_found", P(9,8)))
    wf.add_node(respond_node("Respond Run Not Found", P(10,7), "={{ JSON.stringify({status: 'error', code: 'RUN_NOT_FOUND', command: $json.command, run_id: $json.run_id, correlation_id: $json.correlation_id}) }}"))
    wf.add_node(code_node("Prepare Canonical Run Update", "const p=$json,existing=p.existing_run||{},states={PAUSE_RUN:'PAUSED',ABORT_RUN:'ABORTED',APPROVE_HUMAN_GATE:'HUMAN_GATE_APPROVED'},row={run_id:p.run_id,state:states[p.command]||'RETRY_REQUESTED',current_job:p.stage||p.current_job||existing.current_job||undefined,updated_at:new Date().toISOString(),correlation_id:p.correlation_id,last_action:p.command};if(p.command==='EXCLUDE_MODEL_FOR_RUN')row.excluded_model=(p.payload||{}).model;if(p.command==='EXCLUDE_PROVIDER_FOR_RUN')row.excluded_provider=(p.payload||{}).provider;return[{json:{...p,run_update:{filter:p.filter,data:row,returnData:true}}}];", P(10,8)))
    wf.add_node(http_node("Persist Canonical Run Action", "PATCH", cfg.rows(cfg.runs)+"/update", "JSON.stringify($json.run_update)", P(11,8), cfg.cr_n8n))
    # The n8n HTTP node can emit zero items for a successful empty response.
    # Always retain a carrier item so the canonical response is deterministic.
    persist_action = wf.nodes[-1]
    persist_action["alwaysOutputData"] = True
    wf.add_node(code_node("Canonical Run Action Result", "const p=$('Prepare Canonical Run Update').first().json,result=$json,persisted=Array.isArray(result)?result.length>0:result===true||(result&&typeof result==='object'&&Object.keys(result).length>0);return[{json:{status:persisted?'ACCEPTED':'error',code:persisted?undefined:'RUN_UPDATE_NOT_PERSISTED',module:'run-control',command:p.command,correlation_id:p.correlation_id,run_id:p.run_id,result,source:'n8n-control-gateway'}}];", P(12,8)))
    wf.add_node(respond_node("Respond Canonical Run Action", P(13,8)))
    wf.add_node(code_node("Canonical Admin Action", "const v=$('Restore Valid Command').first().json;return[{json:{status:'ACCEPTED',module:'admin',command:v.command,correlation_id:v.envelope.correlation_id,canonical_action:'n8n-control-gateway',source:'n8n-control-gateway'}}];", P(6,9)))
    wf.add_node(respond_node("Respond Canonical Admin Action", P(7,9)))
    wf.add("Is Blueprint Start?", "Is Project Resume?", 1); wf.add("Is Project Resume?", "Reassess Project", 0); wf.add("Reassess Project", "Project Resume Result"); wf.add("Project Resume Result", "Respond Project Resume"); wf.add("Is Project Resume?", "Is Canonical Run Action?", 1); wf.add("Is Canonical Run Action?", "Prepare Canonical Run Action", 0); wf.add("Prepare Canonical Run Action", "Fetch Canonical Run"); wf.add("Fetch Canonical Run", "Check Canonical Run"); wf.add("Check Canonical Run", "Canonical Run Found?"); wf.add("Canonical Run Found?", "Respond Run Not Found", 1); wf.add("Canonical Run Found?", "Prepare Canonical Run Update", 0); wf.add("Prepare Canonical Run Update", "Persist Canonical Run Action"); wf.add("Persist Canonical Run Action", "Canonical Run Action Result"); wf.add("Canonical Run Action Result", "Respond Canonical Run Action"); wf.add("Is Canonical Run Action?", "Canonical Admin Action", 1); wf.add("Canonical Admin Action", "Respond Canonical Admin Action")
    wf.add("Is Repo Analysis?", "Is Blueprint Start?", 1)
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


def build_06_project_analysis(cfg):
    wf = WF("06 AutoDev Project Analysis")
    P = lambda x, y: [x * 260, y * 170]  # noqa: E731
    wf.add_node(webhook_node("Project Analysis Webhook", "autodev/project/analyse", "POST", cfg.cr_api, P(0, 0)))
    wf.add_node(code_node("Normalize Project Analysis", r"""const env=$json.body||$json,e=env.envelope||{},p=e.payload||{},raw=env.issues; const issues=Array.isArray(raw)?raw:(raw&&Array.isArray(raw.data)?raw.data:[]); const projectId=p.project_id||`project-${String(e.github_owner||'')}-${String(e.github_repo||'')}`;
function status(i){const l=(i.labels||[]).map(x=>String(x.name||x).toUpperCase());if(i.pull_request)return'OBSOLETE';if(i.state==='closed')return'DONE';if(l.some(x=>x.includes('DUPLICATE')))return'DUPLICATE';if(l.some(x=>x.includes('BLOCKED')))return'BLOCKED';if(l.some(x=>x.includes('RUNNING')))return'RUNNING';return'READY'}
const rows=issues.filter(i=>!i.pull_request).map(i=>({project_id:projectId,issue_number:String(i.number||''),title:String(i.title||''),body:String(i.body||'').slice(0,12000),state:String(i.state||'open'),morpheus_status:status(i),depends_on:(String(i.body||'').match(/DEPENDS_ON=([^\\n]+)/i)||[])[1]||'',changes_expected:!String(i.body||'').match(/CHANGES_EXPECTED=false/i),github_url:i.html_url||'',blueprint_section:(String(i.body||'').match(/BLUEPRINT_SECTION=([^\\n]+)/i)||[])[1]||'',updated_at:i.updated_at||new Date().toISOString()})); const counts={READY:0,RUNNING:0,BLOCKED:0,DONE:0,OBSOLETE:0,DUPLICATE:0,UNKNOWN:0}; rows.forEach(r=>counts[r.morpheus_status]=(counts[r.morpheus_status]||0)+1);
return[{json:{project_row:{project_id:projectId,name:p.project_name||`${e.github_owner}/${e.github_repo}`,repository_url:p.repository_url||'',blueprint_ref:p.blueprint_ref||'',project_mode:p.project_mode||'MANUAL',status:counts.BLOCKED?'BLOCKED':counts.RUNNING?'RUNNING':'READY',current_run_id:'',current_issue:'',created_at:new Date().toISOString(),updated_at:new Date().toISOString(),blueprint_sha256:p.blueprint_sha256||'',blueprint_coverage:'UNKNOWN'},issue_rows:rows,summary:{project_id:projectId,counts,source:'github-read-only'}}}];""", P(1,0)))
    wf.add_node(http_node("Persist Project Projection", "POST", cfg.project_rows()+"/upsert", "JSON.stringify({filter:{filters:[{columnName:'project_id',condition:'eq',value:$json.project_row.project_id}]},data:$json.project_row,returnData:true})", P(2,0), cfg.cr_n8n))
    wf.add_node(if_node("Issues Present?", [{"leftValue":"={{$('Normalize Project Analysis').first().json.issue_rows.length}}","rightValue":0,"operator":{"type":"number","operation":"gt"}}], P(3,0)))
    wf.add_node(code_node("Prepare Issue Projection Upserts", "const s=$('Normalize Project Analysis').first().json;return s.issue_rows.map(issue=>({json:{filter:{filters:[{columnName:'project_id',condition:'eq',value:issue.project_id},{columnName:'issue_number',condition:'eq',value:issue.issue_number}]},data:issue,returnData:true}}));", P(3,0)))
    wf.add_node(http_node("Persist Issue Projection", "POST", cfg.issue_rows()+"/upsert", "JSON.stringify($json)", P(4,0), cfg.cr_n8n))
    wf.add_node(code_node("Project Analysis Result", "const s=$('Normalize Project Analysis').first().json;return[{json:{status:'ACCEPTED',project:s.project_row,summary:s.summary,issue_count:s.issue_rows.length,source:'n8n-project-analysis'}}];", P(5,0)))
    wf.add_node(respond_node("Respond Project Analysis", P(6,0)))
    wf.add("Project Analysis Webhook","Normalize Project Analysis");wf.add("Normalize Project Analysis","Persist Project Projection");wf.add("Persist Project Projection","Issues Present?");wf.add("Issues Present?","Prepare Issue Projection Upserts",0);wf.add("Issues Present?","Project Analysis Result",1);wf.add("Prepare Issue Projection Upserts","Persist Issue Projection");wf.add("Persist Issue Projection","Project Analysis Result");wf.add("Project Analysis Result","Respond Project Analysis")
    return wf


def build_07_blueprint_bootstrap(cfg):
    wf = WF("07 AutoDev Blueprint Bootstrap")
    P = lambda x, y: [x * 260, y * 170]  # noqa: E731
    wf.add_node(webhook_node("Blueprint Webhook", "autodev/project/blueprint", "POST", cfg.cr_api, P(0,0)))
    blueprint_js = r"""const env=$json.body||$json,p=env.payload||{},md=String(p.blueprint_md||'').replace(/\r/g,'');const lines=md.split('\n'),heads=[],sections={};let cur='';for(const line of lines){const m=line.match(/^#{1,3}\s+(.+?)\s*$/);if(m){cur=m[1].trim();heads.push(cur);sections[cur]=[]}else if(cur&&line.trim())sections[cur].push(line.trim())}const find=names=>{const k=heads.find(h=>names.includes(h.toLowerCase()));return k?sections[k]||[]:[]};const goal=find(['ziel','projektziel','goal','objective']),req=find(['anforderungen','requirements']),ac=find(['acceptance criteria','akzeptanzkriterien']),mil=find(['meilensteine','milestones']);if(!goal.length&&!req.length&&!ac.length)return[{json:{valid:false,error:'BLUEPRINT_MISSING_REQUIRED_SECTIONS'}}];const slug=String(p.project_name||'blueprint').toLowerCase().replace(/[^a-z0-9-]+/g,'-').replace(/^-|-$/g,'').slice(0,60)||'blueprint-project',repoUrl=String(p.repository_url||''),repoParts=repoUrl.split('/').filter(Boolean),owner=String(p.github_owner||repoParts[repoParts.length-2]||'xxammaxx'),repo=repoParts[repoParts.length-1]||slug,pid=p.project_id||`project-${slug}`,work=[...mil,...req].filter(Boolean),nodes=work.map((text,i)=>({index:i+1,title:text.replace(/^[-*]\s*/,'').slice(0,180),blueprint_section:mil.includes(text)?'milestones':'requirements'})),rows=nodes.map((n,i)=>({project_id:pid,issue_number:`plan-${i+1}`,title:n.title,body:`# Ziel\n\n${n.title}\n\n# Kontext\n\nBlueprint: docs/blueprint.md\n\n# Scope\n\n${n.title}\n\n# Nicht-Scope\n\nNicht in diesem Arbeitspaket.\n\n# Abhängigkeiten\n\n${i?'DEPENDS_ON=plan-'+i:'Keine'}\n\n# Acceptance Criteria\n\n${ac.join('\n')}\n\n# Verifikation\n\nAutomatisierte Tests und Gate-Nachweis.\n\n# Artefakte\n\nBLUEPRINT_SECTION=${n.blueprint_section}`,state:'open',morpheus_status:i?'BLOCKED':'READY',depends_on:i?`plan-${i}`:'',changes_expected:'true',github_url:'',blueprint_section:n.blueprint_section,updated_at:new Date().toISOString()}));const sha=Array.from(new TextEncoder().encode(md)).reduce((h,b)=>((h*33+b)>>>0),5381).toString(16);return[{json:{valid:true,owner,repo,new_repository:!repoUrl,blueprint_md:md,blueprint_b64:Buffer.from(md).toString('base64'),create_github_issues:p.create_github_issues===true&&!p.dry_run,project_row:{project_id:pid,name:p.project_name||'Blueprint Project',repository_url:repoUrl,blueprint_ref:'docs/blueprint.md',project_mode:p.project_mode==='AUTO'?'AUTO':'MANUAL',status:'READY',current_run_id:'',current_issue:rows[0]?.issue_number||'',created_at:new Date().toISOString(),updated_at:new Date().toISOString(),blueprint_sha256:sha,blueprint_coverage:'PENDING'},issue_rows:rows,graph:{nodes,edges:nodes.slice(1).map((n,i)=>({from:'plan-'+(i+1),to:'plan-'+(i+2)}))},blueprint:{goal,scope:find(['scope']),non_scope:find(['nicht-scope','non-scope']),architecture:find(['architektur','architecture']),requirements:req,milestones:mil,acceptance_criteria:ac}}}];"""
    blueprint_js = blueprint_js.replace(
        "new_repository:!repoUrl,",
        "new_repository:!repoUrl&&p.dry_run!==true,blueprint_write:p.dry_run!==true,",
    )
    wf.add_node(code_node("Parse Blueprint Graph", blueprint_js, P(1,0)))
    wf.add_node(bool_if("Blueprint Valid?","$json.valid === true",P(2,0)));wf.add_node(respond_node("Reject Blueprint",P(3,-1),"={{ JSON.stringify({status:'error',code:$json.error||'BLUEPRINT_INVALID'}) }}"))
    wf.add_node(bool_if("Create New Repository?","$json.new_repository === true",P(3,1)))
    wf.add_node(github_http_node("Create GitHub Repository","POST","https://api.github.com/user/repos","JSON.stringify({name: $('Parse Blueprint Graph').first().json.repo, private: true, auto_init: true, description: $('Parse Blueprint Graph').first().json.project_row.name})",P(4,1),cfg.cr_github))
    wf.add_node(code_node("Normalize Created Repository","const s=$('Parse Blueprint Graph').first().json,r=$json;const project={...s.project_row,repository_url:r.html_url||`https://github.com/${s.owner}/${s.repo}`};return[{json:{...s,project_row:project,repository_url:project.repository_url}}];",P(5,1)))
    wf.add_node(code_node("Normalize Existing Repository","const s=$json;return[{json:{...s,repository_url:s.project_row.repository_url}}];",P(4,2)))
    wf.add_node(github_http_node("Persist Blueprint in Repository","PUT","https://api.github.com/repos/{{ $json.owner }}/{{ $json.repo }}/contents/docs/blueprint.md","JSON.stringify({message: 'chore: persist canonical blueprint',content: $json.blueprint_b64})",P(6,1),cfg.cr_github))
    wf.add_node(code_node("Restore Blueprint State","const s=$('Parse Blueprint Graph').first().json;let repo=s.project_row.repository_url;try{repo=$('Normalize Created Repository').first().json.project_row.repository_url}catch(e){}try{repo=$('Normalize Existing Repository').first().json.project_row.repository_url||repo}catch(e){}return[{json:{...s,repository_url:repo,project_row:{...s.project_row,repository_url:repo}}}];",P(7,1)))
    wf.add_node(if_node("Persist Existing Blueprint?", [{"leftValue":"={{$json.blueprint_write}}","operator":{"type":"boolean","operation":"true","singleValue":True}}], P(5,2)))
    wf.add_node(http_node("Persist Blueprint Project","POST",cfg.project_rows()+"/upsert","JSON.stringify({filter:{filters:[{columnName:'project_id',condition:'eq',value:$json.project_row.project_id}]},data:$json.project_row,returnData:true})",P(8,1),cfg.cr_n8n))
    wf.add_node(code_node("Prepare Blueprint Issue Items","const s=$('Restore Blueprint State').first().json;return s.issue_rows.map(issue=>({json:{...s,issue_row:issue,github_issue_body:issue.body}}));",P(9,1)))
    wf.add_node(if_node("Create Blueprint Issues?", [{"leftValue":"={{$json.create_github_issues}}","operator":{"type":"boolean","operation":"true","singleValue":True}}], P(10,1)))
    wf.add_node(github_http_node("Create GitHub Blueprint Issue","POST","https://api.github.com/repos/{{ $json.owner }}/{{ $json.repo }}/issues","JSON.stringify({title: $json.issue_row.title, body: $json.github_issue_body})",P(11,1),cfg.cr_github))
    wf.add_node(http_node("Persist Blueprint Issue Graph","POST",cfg.issue_rows()+"/upsert","JSON.stringify({filter:{filters:[{columnName:'project_id',condition:'eq',value:$json.issue_row.project_id},{columnName:'issue_number',condition:'eq',value:$json.issue_row.issue_number}]},data:$json.issue_row,returnData:true})",P(12,1),cfg.cr_n8n))
    wf.add_node(code_node("Blueprint Issue Persistence Complete","return[{json:{persisted:$input.all().length}}];",P(13,2)))
    wf.add_node(code_node("Blueprint Bootstrap Result","const s=$('Restore Blueprint State').first().json;return[{json:{status:'ACCEPTED',project:s.project_row,repository_url:s.project_row.repository_url,graph:s.graph,blueprint:s.blueprint,issue_plan:s.issue_rows,github_mutation:s.new_repository||s.create_github_issues,source:'n8n-blueprint-bootstrap'}}];",P(13,1)));wf.add_node(respond_node("Respond Blueprint Bootstrap",P(14,1)))
    wf.add("Blueprint Webhook","Parse Blueprint Graph");wf.add("Parse Blueprint Graph","Blueprint Valid?");wf.add("Blueprint Valid?","Reject Blueprint",1);wf.add("Blueprint Valid?","Create New Repository?",0);wf.add("Create New Repository?","Create GitHub Repository",0);wf.add("Create New Repository?","Normalize Existing Repository",1);wf.add("Create GitHub Repository","Normalize Created Repository");wf.add("Normalize Created Repository","Persist Blueprint in Repository");wf.add("Persist Blueprint in Repository","Restore Blueprint State");wf.add("Normalize Existing Repository","Persist Existing Blueprint?");wf.add("Persist Existing Blueprint?","Persist Blueprint in Repository",0);wf.add("Persist Existing Blueprint?","Restore Blueprint State",1);wf.add("Restore Blueprint State","Persist Blueprint Project");wf.add("Persist Blueprint Project","Prepare Blueprint Issue Items");wf.add("Prepare Blueprint Issue Items","Create Blueprint Issues?");wf.add("Create Blueprint Issues?","Create GitHub Blueprint Issue",0);wf.add("Create Blueprint Issues?","Persist Blueprint Issue Graph",1);wf.add("Create GitHub Blueprint Issue","Blueprint Issue Persistence Complete");wf.add("Persist Blueprint Issue Graph","Blueprint Issue Persistence Complete");wf.add("Blueprint Issue Persistence Complete","Blueprint Bootstrap Result");wf.add("Blueprint Bootstrap Result","Respond Blueprint Bootstrap");return wf


def build_08_project_reassessment_legacy(cfg):
    wf=WF("08 AutoDev Project Reassessment");P=lambda x,y:[x*260,y*170] # noqa: E731
    wf.add_node(webhook_node("Project Reassessment Webhook","autodev/project/reassess","POST",cfg.cr_api,P(0,0)))
    wf.add_node(code_node("Prepare Project Issue Query","const source=$json.body||$json,input=source.body||source,projectId=String(input.project_id||'');return[{json:{filter_raw:JSON.stringify({filters:[{columnName:'project_id',condition:'eq',value:projectId}]})}}];",P(1,0)))
    wf.add_node(http_node("Fetch Project Issues","GET",cfg.issue_rows(),"{}",P(2,0),cfg.cr_n8n,send_body=False,params_extra={"url":cfg.issue_rows(),"sendQuery":True,"queryParameters":{"parameters":[{"name":"filter","value":"={{ $json.filter_raw }}"}]}}))
    wf.add_node(code_node("Decide Project Continuation",r"""const source=$('Project Reassessment Webhook').first().json,input=source.body||source,raw=$json,issues=Array.isArray(input.issues)?input.issues:(Array.isArray(raw.data)?raw.data:[]),mode=input.project_mode==='AUTO'?'AUTO':'MANUAL',done=new Set(issues.filter(i=>String(i.status||i.morpheus_status||'').toUpperCase()==='DONE').map(i=>String(i.issue_number||i.number||''))),n=issues.map(i=>{const status=String(i.status||i.morpheus_status||'UNKNOWN').toUpperCase(),deps=String(i.depends_on||'').split(',').map(x=>x.trim().replace(/^#/,'')).filter(Boolean),unmet=deps.filter(d=>!done.has(d));return {...i,status:status==='BLOCKED'&&!unmet.length?'READY':status}}),ready=n.filter(i=>i.status==='READY'),blocked=n.filter(i=>i.status==='BLOCKED'),open=n.filter(i=>!['DONE','OBSOLETE','DUPLICATE'].includes(i.status)),coverage=input.blueprint_coverage===true||input.blueprint_coverage==='true';let status=ready.length?'READY':blocked.length?'BLOCKED':open.length?'UNKNOWN':coverage?'PROJECT_DONE':'BLUEPRINT_COVERAGE_REQUIRED';return[{json:{project_id:input.project_id||'',run_id:input.run_id||'',repository_url:input.repository_url||'',mode,status,ready,blocked,blueprint_coverage:coverage,next_issue:mode==='AUTO'&&ready.length?ready[0]:null,action:mode==='AUTO'&&ready.length?'START_NEXT_CANONICAL_RUN':'DISPLAY_CANDIDATES'}}];""",P(3,0)))
    wf.add_node(if_node("Auto Continue?", [{"leftValue":"={{$json.action}}","rightValue":"=START_NEXT_CANONICAL_RUN","operator":{"type":"string","operation":"equals"}}],P(3,0)))
    wf.add_node(code_node("Prepare Next Run",r"const s=$json,i=s.next_issue||{},repositoryRef=String(s.repository_url||'').replace(/^https:\/\/github\.com\//,'').replace(/\/$/,'');return[{json:{task:{task_ref:'project:'+s.project_id+':issue:'+String(i.issue_number||i.number||''),repository_ref:repositoryRef,task_description:String(i.body||i.title||''),project_id:s.project_id,project_mode:'AUTO',issue_number:i.issue_number||i.number||'', 'x-metadata':{project_id:s.project_id,project_mode:'AUTO'}},backend:'opencode-builder-8001'}}];",P(4,0)));wf.add_node(http_node("Start Next Canonical Run","POST",cfg.webhook+"/webhook/autodev/start","JSON.stringify($json)",P(5,0),cfg.cr_api));wf.add_node(code_node("Auto Continuation Result","return[{json:{status:'ACCEPTED',continuation:'STARTED',reassessment:$('Decide Project Continuation').first().json,result:$json}}];",P(6,0)))
    wf.add_node(code_node("Manual Continuation Result","return[{json:{status:'ACCEPTED',continuation:'CANDIDATES_PRESENTED',reassessment:$json}}];",P(4,1)));wf.add_node(respond_node("Respond Reassessment",P(7,0)));wf.add("Project Reassessment Webhook","Prepare Project Issue Query");wf.add("Prepare Project Issue Query","Fetch Project Issues");wf.add("Fetch Project Issues","Decide Project Continuation");wf.add("Decide Project Continuation","Auto Continue?");wf.add("Auto Continue?","Prepare Next Run",0);wf.add("Prepare Next Run","Start Next Canonical Run");wf.add("Start Next Canonical Run","Auto Continuation Result");wf.add("Auto Continue?","Manual Continuation Result",1);wf.add("Auto Continuation Result","Respond Reassessment");wf.add("Manual Continuation Result","Respond Reassessment");return wf


def build_08_project_reassessment_canonical(cfg):
    """Reassess canonical project history and create exactly one next run."""
    wf = WF("08 AutoDev Project Reassessment")
    P = lambda x, y: [x * 260, y * 170]  # noqa: E731
    wf.add_node(webhook_node("Project Reassessment Webhook", "autodev/project/reassess", "POST", cfg.cr_api, P(0, 0)))
    normalize = r"""const source=$json.body||$json,input=source.body||source,
sourceRunId=String(input.source_run_id||input.run_id||''),providedCorrelation=String(input.correlation_id||''),
mode=input.command==='RESUME_RUN'?'MANUAL':'AUTO_REASSESSMENT',
correlationValid=/^[A-Za-z0-9_.:-]{3,96}$/.test(providedCorrelation),
correlation=correlationValid?providedCorrelation:mode==='AUTO_REASSESSMENT'?'auto-'+sourceRunId:'';
return[{json:{project_id:String(input.project_id||''),source_run_id:sourceRunId,
issue_number:input.issue_number===undefined?'':String(input.issue_number),
continuation_reason:String(input.continuation_reason||''),requested_action:String(input.requested_action||''),
requested_by:String(input.requested_by||''),correlation_id:correlation,correlation_valid:correlationValid||mode==='AUTO_REASSESSMENT',
project_mode:input.project_mode==='AUTO'?'AUTO':'MANUAL',repository_url:String(input.repository_url||''),mode}}];"""
    wf.add_node(code_node("Normalize Continuation Request", normalize, P(1, 0)))
    query = "const s=$json;return[{json:{...s,filter_raw:JSON.stringify({filters:[{columnName:'project_id',condition:'eq',value:s.project_id}]})}}];"
    wf.add_node(code_node("Prepare Project Query", query, P(2, 0)))
    wf.add_node(http_node("Fetch Canonical Project", "GET", cfg.project_rows(), "{}", P(3, 0), cfg.cr_n8n, send_body=False, params_extra={"url": cfg.project_rows(), "sendQuery": True, "queryParameters": {"parameters": [{"name": "filter", "value": "={{ $json.filter_raw }}"}]}}))
    wf.nodes[-1]["alwaysOutputData"] = True
    wf.add_node(http_node("Fetch Project Runs", "GET", cfg.rows(cfg.runs), "{}", P(4, 0), cfg.cr_n8n, send_body=False, params_extra={"url": cfg.rows(cfg.runs), "sendQuery": True, "queryParameters": {"parameters": [{"name": "filter", "value": "={{ $('Prepare Project Query').first().json.filter_raw }}"}]}}))
    wf.nodes[-1]["alwaysOutputData"] = True
    wf.add_node(http_node("Fetch Project Issues", "GET", cfg.issue_rows(), "{}", P(5, 0), cfg.cr_n8n, send_body=False, params_extra={"url": cfg.issue_rows(), "sendQuery": True, "queryParameters": {"parameters": [{"name": "filter", "value": "={{ $('Prepare Project Query').first().json.filter_raw }}"}]}}))
    wf.nodes[-1]["alwaysOutputData"] = True
    decision = CONTINUATION_RUN_ID_JS + r"""
const req=$('Normalize Continuation Request').first().json,projects=Array.isArray($('Fetch Canonical Project').first().json.data)?$('Fetch Canonical Project').first().json.data:[],runs=Array.isArray($('Fetch Project Runs').first().json.data)?$('Fetch Project Runs').first().json.data:[],issues=Array.isArray($json.data)?$json.data:[],project=projects[0]||null,activeStates=new Set(['ACCEPTED','BASELINING','RESEARCHING','PLANNING','BUILDING','VERIFYING','REVIEWING','DECIDING','RUNNING','ACTIVE']),terminalStates=new Set(['DONE','COMPLETED','ABORTED','BLOCKED','FAILED','PAUSED','PLAN_BLOCKED']),active=runs.find(r=>activeStates.has(String(r.state||'').toUpperCase())),source=runs.find(r=>String(r.run_id||'')===req.source_run_id),duplicate=runs.find(r=>String(r.correlation_id||'')===req.correlation_id&&String(r.created_via||'')==='CONTROL_TOWER_CONTINUATION'),selectedIssue=req.issue_number?issues.find(i=>String(i.issue_number||i.number||'')===req.issue_number):null;let code='';if(!project)code='PROJECT_NOT_FOUND';else if(req.mode==='MANUAL'&&!req.correlation_valid)code='CORRELATION_ID_INVALID';else if(duplicate)code='DUPLICATE_REQUEST';else if(active)code='PROJECT_ACTIVE_RUN_CONFLICT';else if(!source||String(source.project_id||'')!==req.project_id||!terminalStates.has(String(source.state||'').toUpperCase()))code='CONTINUATION_NOT_ALLOWED';else if(req.issue_number&&(!selectedIssue||['OBSOLETE','DUPLICATE'].includes(String(selectedIssue.morpheus_status||selectedIssue.status||'').toUpperCase())))code='ISSUE_NOT_FOUND';else if(req.mode==='MANUAL'&&(!req.continuation_reason.trim()||req.continuation_reason.length>240||!req.requested_action.trim()||req.requested_action.length>240))code='CONTINUATION_NOT_ALLOWED';const issueNumber=req.issue_number||String(source&&source.issue_number||''),issue=selectedIssue||issues.find(i=>String(i.issue_number||i.number||'')===issueNumber)||null,reason=req.continuation_reason.trim()||'continue next approved project work',action=req.requested_action.trim()||String(issue&&issue.title||'reassess and continue project'),repository=String(project&&(project.repository_url||project.repository_ref)||req.repository_url||(source&&source.repository_ref)||'').replace(/^https:\/\/github\.com\//,'').replace(/\/$/,''),continuationIdentity=JSON.stringify([req.project_id,req.source_run_id,req.correlation_id]),runId=canonicalContinuationRunId(req.project_id,req.source_run_id,req.correlation_id),description=[String(issue&&issue.body||issue&&issue.title||''),action,reason].filter(Boolean).join('\n\n').slice(0,4000);return[{json:{...req,valid:!code,code,project,source_run:source||null,selected_issue:issue||null,continuation_identity:continuationIdentity,continuation_run_id:runId,start_request:{task:{run_id:runId,task_ref:'project:'+req.project_id+(issueNumber?':issue:'+issueNumber:''),repository_ref:repository,workspace:String((project&&project.workspace)||req.project_id),task_description:description||('Continue project '+req.project_id),acceptance_hint:action,max_attempts:2,project_id:req.project_id,project_mode:'MANUAL',issue_number:issueNumber,source_run_id:req.source_run_id,continuation_reason:reason,requested_action:action,requested_by:req.requested_by,created_via:'CONTROL_TOWER_CONTINUATION','x-metadata':{project_id:req.project_id,project_mode:'MANUAL',issue_number:issueNumber,source_run_id:req.source_run_id,continuation_reason:reason,requested_action:action,requested_by:req.requested_by,created_via:'CONTROL_TOWER_CONTINUATION',correlation_id:req.correlation_id}},backend:'opencode-builder-8001'}}}];"""
    wf.add_node(code_node("Decide Canonical Continuation", decision, P(6, 0)))
    wf.add_node(bool_if("Continuation Allowed?", "$json.valid === true", P(7, 0)))
    wf.add_node(code_node("Reject Continuation", "const s=$json;return[{json:{status:'error',code:s.code||'CONTINUATION_NOT_ALLOWED',project_id:s.project_id,source_run_id:s.source_run_id,correlation_id:s.correlation_id}}];", P(8, 1)))
    wf.add_node(http_node("Start Next Canonical Run", "POST", cfg.webhook + "/webhook/autodev/start", "JSON.stringify($json.start_request)", P(8, 0), cfg.cr_api))
    wf.add_node(code_node("Canonical Continuation Result", "const s=$('Decide Canonical Continuation').first().json;return[{json:{status:'ACCEPTED',continuation:'STARTED',project_id:s.project_id,source_run_id:s.source_run_id,new_run_id:s.continuation_run_id,correlation_id:s.correlation_id,created_via:'CONTROL_TOWER_CONTINUATION',result:$json,source:'n8n-project-reassessment'}}];", P(9, 0)))
    wf.add_node(respond_node("Respond Reassessment", P(10, 0)))
    wf.add("Project Reassessment Webhook", "Normalize Continuation Request")
    wf.add("Normalize Continuation Request", "Prepare Project Query")
    wf.add("Prepare Project Query", "Fetch Canonical Project")
    wf.add("Fetch Canonical Project", "Fetch Project Runs")
    wf.add("Fetch Project Runs", "Fetch Project Issues")
    wf.add("Fetch Project Issues", "Decide Canonical Continuation")
    wf.add("Decide Canonical Continuation", "Continuation Allowed?")
    wf.add("Continuation Allowed?", "Start Next Canonical Run", 0)
    wf.add("Continuation Allowed?", "Reject Continuation", 1)
    wf.add("Start Next Canonical Run", "Canonical Continuation Result")
    wf.add("Canonical Continuation Result", "Respond Reassessment")
    wf.add("Reject Continuation", "Respond Reassessment")
    return wf


def build_08_project_reassessment(cfg):
    """Compatibility entry point for callers of the existing builder name."""
    return build_08_project_reassessment_canonical(cfg)


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
    "05 AutoDev Control Gateway": build_05_control_gateway,
    "06 AutoDev Project Analysis": build_06_project_analysis,
    "07 AutoDev Blueprint Bootstrap": build_07_blueprint_bootstrap,
    "08 AutoDev Project Reassessment": build_08_project_reassessment,
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
