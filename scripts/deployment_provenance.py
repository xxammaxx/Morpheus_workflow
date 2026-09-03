#!/usr/bin/env python3
"""Fail-closed deployment provenance attestation and canonical reader."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from typing import Any

CONTRACT = "autodev.deployment-provenance.v1"
STORE = "/var/lib/autodev-harness-v2/deployment-provenance.json"
HOST = "root@192.168.1.136"
WORKFLOW_ROOT = "n8n/workflows/autodev"
SERVICE_NAMES = ("autodev-harness-v2", "morpheus-control-tower")
WORKFLOW_INSTANCE_METADATA = frozenset({
    "id", "createdAt", "updatedAt", "versionId", "versionCounter",
    "active", "activeVersion", "activeVersionId", "sourceWorkflowId", "isArchived",
    "staticData", "pinData", "tags", "meta", "shared", "nodeGroups", "description",
    "triggerCount",
})

def sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()

def normalize_workflow(value: Any, context: str = "value") -> Any:
    """The one recursive normalizer used by source and live hashing."""
    if isinstance(value, dict):
        ignored = {"webhookId"} if context == "node" else set()
        return {key: normalize_workflow(value[key], "node" if key == "nodes" else "value")
                for key in sorted(value) if key not in ignored}
    if isinstance(value, list): return [normalize_workflow(item, "node" if context == "node" else "value") for item in value]
    return value

def normalize_workflow_document(value: Any) -> Any:
    """Drop only top-level n8n instance metadata; retain nested semantic ids."""
    if not isinstance(value, dict): raise ValueError("WORKFLOW_DEFINITION_INVALID")
    return normalize_workflow({key: value[key] for key in value if key not in WORKFLOW_INSTANCE_METADATA})

def semantic_hash(value: Any) -> str:
    return sha((json.dumps(normalize_workflow_document(value), sort_keys=True, separators=(",", ":")) + "\n").encode())

def git_blob(commit: str, path: str) -> bytes:
    result = subprocess.run(["git", "cat-file", "-p", f"{commit}:{path}"], capture_output=True)
    if result.returncode: raise ValueError(f"SOURCE_ARTIFACT_MISSING:{path}")
    return result.stdout

def valid_commit(commit: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{40}", commit)) and subprocess.run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], capture_output=True).returncode == 0

def artifact_paths(commit: str) -> list[tuple[str, str]]:
    roots = [("adapter/harness_adapter_v2.py", "/opt/autodev-harness-v2/harness_adapter_v2.py")]
    for top, dest in (("runtime/contracts", "/opt/autodev-harness-v2/contracts"), ("runtime/hamh", "/opt/autodev-harness-v2/hamh"), ("runtime/providers", "/opt/autodev-harness-v2/providers")):
        names = subprocess.run(["git", "ls-tree", "-r", "--name-only", commit, "--", top], text=True, capture_output=True, check=True).stdout.splitlines()
        for path in names:
            if "/tests/" in path or path.endswith("/__init__.pyc") or "/static/vendor/" in path: continue
            if path == "runtime/contracts/schemas/autodev.deployment-provenance.v1.schema.json": continue
            roots.append((path, dest + "/" + path[len(top) + 1:]))
    return roots

def source_observations(commit: str) -> list[dict[str, str]]:
    if not valid_commit(commit): raise ValueError("SOURCE_COMMIT_INVALID")
    return [{"source_path": source, "deployed_path": deployed, "source_sha256": sha(git_blob(commit, source))} for source, deployed in artifact_paths(commit)]

def workflow_sources(commit: str) -> list[dict[str, str]]:
    if not valid_commit(commit): raise ValueError("SOURCE_COMMIT_INVALID")
    paths = subprocess.run(["git", "ls-tree", "-r", "--name-only", commit, "--", WORKFLOW_ROOT], text=True, capture_output=True, check=True).stdout.splitlines()
    paths = sorted(path for path in paths if path.startswith(WORKFLOW_ROOT + "/") and path.endswith(".json"))
    if not paths: raise ValueError("DECLARED_WORKFLOW_SET_EMPTY")
    return [{"source_path": path, "workflow_name": pathlib.PurePosixPath(path).stem} for path in paths]

def remote_json(code: str) -> Any:
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", HOST, "python3", "-"], input=code, text=True, capture_output=True, check=False)
    if result.returncode: raise RuntimeError("REMOTE_VERIFICATION_FAILED:" + result.stderr[-500:])
    return json.loads(result.stdout)

def verify_live(artifacts: list[dict[str, str]], workflows: list[dict[str, Any]]) -> tuple[list[dict], list[dict], list[dict], bool, bool]:
    payload = json.dumps({"artifacts": artifacts})
    code = """import hashlib,json,subprocess
p=json.loads(%r); out=[]
for a in p['artifacts']:
 try:
  with open(a['deployed_path'],'rb') as f: h=hashlib.sha256(f.read()).hexdigest()
 except OSError: h=''
 out.append(dict(a,deployed_sha256=h,match=h==a['source_sha256']))
services=[{'name':n,'active':subprocess.run(['systemctl','is-active','--quiet',n]).returncode==0} for n in %r]
print(json.dumps({'artifacts':out,'services':services}))
""" % (payload, SERVICE_NAMES)
    result = remote_json(code)
    names = json.dumps([item["workflow_name"] for item in workflows])
    n8n_code = """import json,pathlib,urllib.request
names=%s
key=pathlib.Path('/var/lib/n8n-spec-kit/secrets/ghiw-n8n-api-key').read_text().strip(); headers={'X-N8N-API-KEY':key}
def get(url):
 req=urllib.request.Request(url,headers=headers)
 with urllib.request.urlopen(req,timeout=30) as response: return json.load(response)
listed=get('http://192.168.1.52:5678/api/v1/workflows?limit=250'); found={item.get('name'):item for item in listed.get('data',[])}
out=[]; full=True; activation=True
for name in names:
 summary=found.get(name)
 if summary is None: out.append({'workflow_name':name,'live_definition':None}); full=False; activation=False; continue
 activation=activation and summary.get('active') is True
 try: definition=get('http://192.168.1.52:5678/api/v1/workflows/'+str(summary['id']))
 except Exception: definition=None
 if not isinstance(definition,dict) or not isinstance(definition.get('nodes'),list) or not isinstance(definition.get('connections'),dict): full=False
 out.append({'workflow_name':name,'live_definition':definition})
print(json.dumps({'workflows':out,'full_definition_verified':full,'activation_verified':activation}))
""" % names
    live = remote_json(n8n_code)
    definitions = {item["workflow_name"]: item.get("live_definition") for item in live["workflows"]}
    enriched = []
    for item in workflows:
        definition = definitions.get(item["workflow_name"])
        live_hash = semantic_hash(definition) if live["full_definition_verified"] and definition is not None else ""
        enriched.append(dict(item, live_semantic_sha256=live_hash, match=live_hash == item["source_semantic_sha256"]))
    return result["artifacts"], enriched, result["services"], live["full_definition_verified"], live["activation_verified"]

def validate(record: dict) -> None:
    required = ("contract", "version", "repository", "source_commit_sha", "source_branch", "deployed_at", "mode", "runtime_artifacts", "n8n_workflows", "services", "verification")
    if any(key not in record for key in required) or record["contract"] != CONTRACT or record["version"] != "v1" or not valid_commit(record["source_commit_sha"]): raise ValueError("PROVENANCE_CONTRACT_INVALID")
    expected = {"runtime_artifacts_match": True, "n8n_workflows_match": True, "required_services_healthy": True, "workflow_full_definitions": True, "workflow_activation_verified": True}
    if record["verification"] != expected: raise ValueError("PROVENANCE_CONTRACT_INVALID")
    if not all(item["match"] and item["source_sha256"] == item["deployed_sha256"] for item in record["runtime_artifacts"]): raise ValueError("FAILED_VERIFICATION")
    if not all(item["match"] and item["source_semantic_sha256"] == item["live_semantic_sha256"] for item in record["n8n_workflows"]): raise ValueError("FAILED_VERIFICATION")
    if not all(item["active"] for item in record["services"]): raise ValueError("FAILED_VERIFICATION")

def atomic_write(record: dict, path: str = STORE) -> None:
    validate(record); parent = os.path.dirname(path); os.makedirs(parent, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".deployment-provenance.", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, sort_keys=True); handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            os.chown(path, 0, 0)
            os.chmod(path, 0o600)
        except PermissionError:
            if path == STORE: raise
        directory = os.open(parent, os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
        with open(path, encoding="utf-8") as handle: validate(json.load(handle))
    finally:
        if os.path.exists(temporary): os.unlink(temporary)

def attest(commit: str, mode: str) -> dict:
    artifacts = source_observations(commit)
    workflows = [dict(source, source_semantic_sha256=semantic_hash(json.loads(git_blob(commit, source["source_path"])))) for source in workflow_sources(commit)]
    artifacts, workflows, services, full, activation = verify_live(artifacts, workflows)
    record = {"contract": CONTRACT, "version": "v1", "repository": "xxammaxx/Morpheus_workflow", "source_commit_sha": commit, "source_branch": subprocess.check_output(["git", "branch", "--show-current"], text=True).strip(), "deployed_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"), "mode": mode, "runtime_artifacts": artifacts, "n8n_workflows": workflows, "services": services, "verification": {"runtime_artifacts_match": all(item["match"] for item in artifacts), "n8n_workflows_match": all(item["match"] for item in workflows), "required_services_healthy": all(item["active"] for item in services), "workflow_full_definitions": full, "workflow_activation_verified": activation}}
    validate(record)
    serialized = json.dumps(record, sort_keys=True, separators=(",", ":"))
    result = remote_json("""import json,os,tempfile
record=json.loads(%r); path=%r; parent=os.path.dirname(path); os.makedirs(parent,exist_ok=True)
fd,tmp=tempfile.mkstemp(prefix='.deployment-provenance.',dir=parent)
try:
 with os.fdopen(fd,'w',encoding='utf-8') as f: json.dump(record,f,indent=2,sort_keys=True); f.write('\\n'); f.flush(); os.fsync(f.fileno())
 os.replace(tmp,path); os.chown(path,0,0); os.chmod(path,0o600); d=os.open(parent,os.O_DIRECTORY); os.fsync(d); os.close(d)
 with open(path,encoding='utf-8') as f: json.load(f)
 print(json.dumps({'written':True,'path':path}))
finally:
 if os.path.exists(tmp): os.unlink(tmp)
""" % (serialized, STORE))
    if result.get("written") is not True: raise RuntimeError("PROVENANCE_WRITE_FAILED")
    return record

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("attest", "read")); parser.add_argument("--commit"); parser.add_argument("--expected-commit"); parser.add_argument("--mode", default="reconcile-existing-runtime"); args = parser.parse_args()
    if args.command == "read":
        record = remote_json("import json; print(json.dumps(json.load(open(%r))))" % STORE); validate(record)
        expected = args.expected_commit or subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        print(json.dumps({"PROVENANCE_CONTRACT": record["contract"], "DEPLOYED_SOURCE_COMMIT": record["source_commit_sha"], "PROVENANCE_MODE": record["mode"], "RUNTIME_ARTIFACTS_MATCH": record["verification"]["runtime_artifacts_match"], "N8N_WORKFLOWS_MATCH": record["verification"]["n8n_workflows_match"], "DEPLOYMENT_HEAD_MATCH": record["source_commit_sha"] == expected, "PROVENANCE_VALID": True}, sort_keys=True)); return 0
    if not args.commit: parser.error("--commit is required for attest")
    print(json.dumps(attest(args.commit, args.mode), sort_keys=True)); return 0

if __name__ == "__main__":
    try: raise SystemExit(main())
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as exc: print(str(exc), file=sys.stderr); raise SystemExit(1)
