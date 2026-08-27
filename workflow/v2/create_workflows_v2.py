#!/usr/bin/env python3
"""AutoDev Harness v2 — n8n setup & creation script (run on the Proxmox host).

Steps:
  1. create Data Tables autodev_runs + autodev_attempts (Public API)
  2. create credentials: autodev-n8n-api, autodev-harness-token,
     autodev-api-auth (httpHeaderAuth, values from files — never argv)
  3. generate the 12 workflows (config with real IDs)
  4. create workflows via Public API
  5. activate 00 / 01 / 02
  6. export final workflow JSONs to the repo output dir

Usage: python3 create_workflows_v2.py <repo_root> <export_dir>
Secrets are read from: /var/lib/n8n-spec-kit/secrets/ghiw-n8n-api-key,
/var/lib/autodev-harness-v2/token, /var/lib/autodev-harness-v2/api-token.
"""

import json
import os
import secrets
import subprocess
import sys
import urllib.request

BASE = "http://192.168.1.52:5678"
API_KEY_PATH = "/var/lib/n8n-spec-kit/secrets/ghiw-n8n-api-key"
HARNESS_TOKEN_PATH = "/var/lib/autodev-harness-v2/token"
API_TOKEN_PATH = "/var/lib/autodev-harness-v2/api-token"
REPO_ROOT = sys.argv[1] if len(sys.argv) > 1 else "/tmp"
EXPORT_DIR = (
    sys.argv[2]
    if len(sys.argv) > 2
    else os.path.join(REPO_ROOT, "n8n", "workflows", "autodev")
)


def api(method, path, body=None):
    with open(API_KEY_PATH) as f:
        key = f.read().strip()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"X-N8N-API-KEY": key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"message": raw}


def create_table(name, columns):
    st, resp = api(
        "POST",
        "/api/v1/data-tables",
        {"name": name, "columns": [{"name": c, "type": "string"} for c in columns]},
    )
    if st == 409:
        st, resp = api("GET", "/api/v1/data-tables?limit=250")
        for t in resp.get("data", []):
            if t["name"] == name:
                return t["id"]
        raise SystemExit("table %s exists but not found in list" % name)
    if st not in (200, 201):
        raise SystemExit("create table %s failed: %s" % (name, resp))
    return resp["id"]


def create_credential(name, header_name, value):
    st, resp = api("GET", "/api/v1/credentials?limit=250")
    for c in resp.get("data", []):
        if c["name"] == name:
            return c["id"], c["name"]
    st, resp = api(
        "POST",
        "/api/v1/credentials",
        {
            "name": name,
            "type": "httpHeaderAuth",
            "data": {"name": header_name, "value": value, "allowedDomains": "*"},
        },
    )
    if st in (200, 201):
        return resp["id"], resp["name"]
    raise SystemExit("create credential %s failed: %s" % (name, resp))


def find_credential(name):
    st, resp = api("GET", "/api/v1/credentials?limit=250")
    if st != 200:
        raise SystemExit("credential listing failed: %s" % (resp,))
    for credential in resp.get("data", []):
        if credential.get("name") == name:
            return {"id": credential["id"], "name": credential["name"]}
    raise SystemExit("required managed credential is missing: %s" % name)


def main():
    os.makedirs(EXPORT_DIR, exist_ok=True)
    with open(API_KEY_PATH) as f:
        n8n_key = f.read().strip()
    with open(HARNESS_TOKEN_PATH) as f:
        harness_token = f.read().strip()
    if not os.path.exists(API_TOKEN_PATH):
        with open(API_TOKEN_PATH, "w") as f:
            f.write(secrets.token_urlsafe(48))
        os.chmod(API_TOKEN_PATH, 0o600)
    with open(API_TOKEN_PATH) as f:
        api_token = f.read().strip()

    runs_id = create_table(
        "autodev_runs",
        [
            "run_id",
            "state",
            "task_ref",
            "repository_ref",
            "current_job",
            "decision",
            "reason_code",
            "created_at",
            "updated_at",
            "result_ref",
            "trace_id",
            "backend",
        ],
    )
    attempts_id = create_table(
        "autodev_attempts",
        [
            "run_id",
            "job_id",
            "attempt_id",
            "status",
            "input_contract",
            "input_fingerprint",
            "output_contract",
            "output_fingerprint",
            "provider",
            "model",
            "started_at",
            "ended_at",
            "failure_signature",
            "strategy_delta",
            "result_ref",
        ],
    )
    projects_id = create_table(
        "autodev_projects",
        ["project_id", "name", "repository_url", "blueprint_ref", "project_mode",
         "status", "current_run_id", "current_issue", "created_at", "updated_at",
         "blueprint_sha256", "blueprint_coverage"],
    )
    issues_id = create_table(
        "autodev_issues",
        ["project_id", "issue_number", "title", "body", "state", "morpheus_status",
         "depends_on", "changes_expected", "github_url", "blueprint_section", "updated_at"],
    )
    audit_id = create_table(
        "autodev_audit",
        ["timestamp", "actor", "role", "command", "target", "project_id", "run_id",
         "result", "correlation_id"],
    )
    print("TABLES runs=%s attempts=%s projects=%s issues=%s audit=%s" %
          (runs_id, attempts_id, projects_id, issues_id, audit_id))

    cr_n8n_id, cr_n8n_name = create_credential(
        "autodev-n8n-api", "X-N8N-API-KEY", n8n_key
    )
    cr_harn_id, cr_harn_name = create_credential(
        "autodev-harness-token", "X-Harness-Token", harness_token
    )
    cr_api_id, cr_api_name = create_credential(
        "autodev-api-auth", "X-AutoDev-Token", api_token
    )
    github_cred = find_credential("GitHub account")
    runner_ssh_cred = find_credential("dev-runner-ssh")
    print("CREDS n8n=%s harness=%s api=%s" % (cr_n8n_id, cr_harn_id, cr_api_id))

    gen = os.path.join(REPO_ROOT, "workflow", "v2", "generate_workflows_v2.py")
    created = {}

    def run_generation(extra=None):
        config = {
            "n8n_base": "http://192.168.1.52:5678",
            "adapter_base": "http://192.168.1.136:8081",
            "webhook_base": "http://192.168.1.52:5678",
            "tables": {"runs": runs_id, "attempts": attempts_id, "projects": projects_id,
                        "issues": issues_id, "audit": audit_id},
            "creds": {
                "n8n_api": {"id": cr_n8n_id, "name": cr_n8n_name},
                "harness_token": {"id": cr_harn_id, "name": cr_harn_name},
                "api_auth": {"id": cr_api_id, "name": cr_api_name},
                "github_api": github_cred,
                "runner_ssh": runner_ssh_cred,
            },
        }
        if extra:
            config.update(extra)
        cfg_path = os.path.join(REPO_ROOT, "workflow", "v2", "config.json")
        with open(cfg_path, "w") as f:
            json.dump(config, f, indent=2)
        subprocess.run([sys.executable, gen, cfg_path, EXPORT_DIR], check=True)

    def find_existing():
        st, resp = api("GET", "/api/v1/workflows?limit=250")
        return {
            w["name"]: w["id"]
            for w in resp.get("data", [])
            if "AutoDev" in w["name"] and "Harness" not in w["name"]
        }

    def upsert_names(names, wf_ids_extra=None):
        run_generation(wf_ids_extra)
        existing = find_existing()
        out = {}
        for name in names:
            fn = os.path.join(EXPORT_DIR, name + ".json")
            wf = json.load(open(fn))
            if name in existing:
                st, resp = api("PUT", "/api/v1/workflows/" + existing[name], wf)
                verb = "UPDATED"
            else:
                st, resp = api("POST", "/api/v1/workflows", wf)
                verb = "CREATED"
            if st not in (200, 201):
                raise SystemExit("upsert %s failed: %s" % (name, resp))
            out[name] = resp["id"]
            print("%s %s -> %s (nodes=%d)" % (verb, name, resp["id"], len(wf["nodes"])))
        return out

    SUB = ["10 AutoDev Baseline", "20 AutoDev Research Batch", "30 AutoDev Plan",
           "40 AutoDev Build", "50 AutoDev Verify", "60 AutoDev Review Batch",
           "70 AutoDev Decision", "80 AutoDev Fix", "90 AutoDev Split"]

    # pass 1a: sub-workflows 10-90 (no cross-references)
    sub_ids = upsert_names(SUB)
    for name, wid in sub_ids.items():
        st, resp = api("POST", "/api/v1/workflows/%s/activate" % wid)
        print("ACTIVATE SUB", name, st)

    # pass 1b: orchestrator referencing real sub ids
    orch = upsert_names(["01 AutoDev Orchestrator"], {"workflow_ids": sub_ids})
    st, resp = api("POST", "/api/v1/workflows/%s/activate" % orch["01 AutoDev Orchestrator"])
    print("ACTIVATE ORCH", st, resp.get("active"))

    # pass 1c: start + status workflows referencing orchestrator
    api_wfs = upsert_names(["00 AutoDev API Start", "02 AutoDev API Status",
                            "05 AutoDev Control Gateway", "06 AutoDev Project Analysis",
                            "07 AutoDev Blueprint Bootstrap", "08 AutoDev Project Reassessment"],
                           {"workflow_ids": dict(sub_ids, **orch)})
    for name in ("00 AutoDev API Start", "02 AutoDev API Status",
                 "05 AutoDev Control Gateway", "06 AutoDev Project Analysis",
                 "07 AutoDev Blueprint Bootstrap", "08 AutoDev Project Reassessment"):
        st, resp = api("POST", "/api/v1/workflows/%s/activate" % api_wfs[name])
        print("ACTIVATE", name, st, resp.get("active"))

    created = dict(sub_ids, **orch, **api_wfs)

    # export roundtrip (final production JSONs)
    for name, wid in created.items():
        st, resp = api("GET", "/api/v1/workflows/" + wid)
        fn = os.path.join(EXPORT_DIR, name + ".json")
        with open(fn, "w") as f:
            json.dump(resp, f, indent=2, ensure_ascii=False)
        print("EXPORTED", fn)

    with open(os.path.join(EXPORT_DIR, "..", "workflow-ids.json"), "w") as f:
        json.dump(created, f, indent=2)
    print("DONE")


if __name__ == "__main__":
    main()
