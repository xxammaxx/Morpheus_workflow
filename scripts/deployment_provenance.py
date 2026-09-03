#!/usr/bin/env python3
"""Verified deployment provenance attestation and its single canonical reader.

The writer receives source hashes from Git objects and live observations from
the host. It never accepts a caller-supplied head as proof of deployment.
"""
from __future__ import annotations

import argparse, datetime as dt, hashlib, json, os, pathlib, subprocess, sys, tempfile
from typing import Any

CONTRACT = "autodev.deployment-provenance.v1"
STORE = "/var/lib/autodev-harness-v2/deployment-provenance.json"
HOST = "root@192.168.1.136"
WORKFLOW_DIR = pathlib.Path(__file__).parents[1] / "n8n/workflows/autodev"
SERVICE_NAMES = ("autodev-harness-v2", "morpheus-control-tower")

def sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()

def normalize_workflow(value: Any) -> Any:
    # These are n8n instance/runtime metadata. Node semantics, credentials,
    # expressions, settings, response codes, and connections remain intact.
    ignored = {"id", "createdAt", "updatedAt", "versionId", "active", "isArchived", "staticData", "pinData", "tags", "meta"}
    if isinstance(value, dict): return {k: normalize_workflow(v) for k, v in sorted(value.items()) if k not in ignored}
    if isinstance(value, list): return [normalize_workflow(v) for v in value]
    return value

def semantic_hash(value: Any) -> str:
    return sha((json.dumps(normalize_workflow(value), sort_keys=True, separators=(",", ":")) + "\n").encode())

def git_blob(commit: str, path: str) -> bytes:
    p = subprocess.run(["git", "cat-file", "-p", f"{commit}:{path}"], capture_output=True)
    if p.returncode: raise ValueError(f"SOURCE_ARTIFACT_MISSING:{path}")
    return p.stdout

def valid_commit(commit: str) -> bool:
    return bool(__import__("re").fullmatch(r"[0-9a-f]{40}", commit)) and subprocess.run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], capture_output=True).returncode == 0

def artifact_paths(commit: str) -> list[tuple[str, str]]:
    # The integration deployment convention installs the adapter execution
    # tree. Host-specific systemd units and the separately deployed dashboard
    # are health-checked below, but are not this runtime's source artifact set.
    roots = [("adapter/harness_adapter_v2.py", "/opt/autodev-harness-v2/harness_adapter_v2.py")]
    for top, dest in (("runtime/contracts", "/opt/autodev-harness-v2/contracts"), ("runtime/hamh", "/opt/autodev-harness-v2/hamh"), ("runtime/providers", "/opt/autodev-harness-v2/providers")):
        names = subprocess.run(["git", "ls-tree", "-r", "--name-only", commit, "--", top], text=True, capture_output=True, check=True).stdout.splitlines()
        for path in names:
            if "/tests/" in path or path.endswith("/__init__.pyc") or "/static/vendor/" in path: continue
            if path == "runtime/contracts/schemas/autodev.deployment-provenance.v1.schema.json": continue
            roots.append((path, dest + "/" + path[len(top)+1:]))
    return roots

def source_observations(commit: str) -> list[dict[str, str]]:
    if not valid_commit(commit): raise ValueError("SOURCE_COMMIT_INVALID")
    out = []
    for source, deployed in artifact_paths(commit):
        out.append({"source_path": source, "deployed_path": deployed, "source_sha256": sha(git_blob(commit, source))})
    return out

def remote_json(code: str) -> Any:
    p = subprocess.run(["ssh", "-o", "BatchMode=yes", HOST, "python3", "-"], input=code, text=True, capture_output=True, check=False)
    if p.returncode: raise RuntimeError("REMOTE_VERIFICATION_FAILED:" + p.stderr[-500:])
    return json.loads(p.stdout)

def verify_live(artifacts: list[dict[str, str]], workflows: list[dict[str, str]]) -> tuple[list[dict], list[dict], list[dict]]:
    payload = json.dumps({"artifacts": artifacts, "workflow_names": [x["workflow_name"] for x in workflows]})
    code = """import hashlib,json,os,subprocess,urllib.request
p=json.loads(%r); out=[]
for a in p['artifacts']:
 try:
  with open(a['deployed_path'],'rb') as f: h=hashlib.sha256(f.read()).hexdigest()
 except OSError: h=''
 out.append(dict(a,deployed_sha256=h,match=h==a['source_sha256']))
services=[{'name':n,'active':subprocess.run(['systemctl','is-active','--quiet',n]).returncode==0} for n in ('autodev-harness-v2','morpheus-control-tower')]
print(json.dumps({'artifacts':out,'services':services}))
""" % payload
    result = remote_json(code)
    # n8n is queried from the host so its protected API key never leaves it.
    names = json.dumps([x["workflow_name"] for x in workflows])
    n8n_code = """import hashlib,json,os,urllib.request
names=%s
key=open('/var/lib/n8n-spec-kit/secrets/ghiw-n8n-api-key').read().strip(); req=urllib.request.Request('http://192.168.1.52:5678/api/v1/workflows?limit=250',headers={'X-N8N-API-KEY':key})
with urllib.request.urlopen(req,timeout=30) as r: data=json.load(r)
found={x.get('name'):x for x in data.get('data',[])}; out=[]
for n in names:
 x=found.get(n); live='' if x is None else hashlib.sha256((json.dumps({k:v for k,v in sorted(x.items()) if k not in {'id','createdAt','updatedAt','versionId','active','isArchived','staticData','pinData','tags','meta'}},sort_keys=True,separators=(',',':'))+'\\n').encode()).hexdigest()
 out.append({'workflow_name':n,'live_semantic_sha256':live})
print(json.dumps(out))
""" % names
    wf = remote_json(n8n_code)
    by = {x["workflow_name"]: x["live_semantic_sha256"] for x in wf}
    workflows = [dict(x, live_semantic_sha256=by.get(x["workflow_name"], ""), match=by.get(x["workflow_name"], "") == x["source_semantic_sha256"]) for x in workflows]
    return result["artifacts"], workflows, result["services"]

def validate(record: dict) -> None:
    required = ("contract","version","repository","source_commit_sha","source_branch","deployed_at","mode","runtime_artifacts","n8n_workflows","services","verification")
    if any(k not in record for k in required) or record["contract"] != CONTRACT or record["version"] != "v1" or not valid_commit(record["source_commit_sha"]): raise ValueError("PROVENANCE_CONTRACT_INVALID")
    if not record["verification"] == {"runtime_artifacts_match": True, "n8n_workflows_match": True, "required_services_healthy": True}: raise ValueError("PROVENANCE_CONTRACT_INVALID")
    if not all(a["match"] and a["source_sha256"] == a["deployed_sha256"] for a in record["runtime_artifacts"]): raise ValueError("FAILED_VERIFICATION")
    if not all(w["match"] and w["source_semantic_sha256"] == w["live_semantic_sha256"] for w in record["n8n_workflows"]): raise ValueError("FAILED_VERIFICATION")
    if not all(s["active"] for s in record["services"]): raise ValueError("FAILED_VERIFICATION")

def atomic_write(record: dict, path: str = STORE) -> None:
    validate(record); parent=os.path.dirname(path); os.makedirs(parent, exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.deployment-provenance.', dir=parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f: json.dump(record,f,indent=2,sort_keys=True); f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
        try:
            d=os.open(parent,os.O_DIRECTORY); os.fsync(d); os.close(d)
        except OSError: pass
        with open(path,encoding='utf-8') as f: reread=json.load(f)
        validate(reread)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def attest(commit: str, mode: str) -> dict:
    artifacts=source_observations(commit)
    workflows=[]
    for p in sorted(WORKFLOW_DIR.glob('*.json')):
        workflows.append({'workflow_name':p.stem,'source_semantic_sha256':semantic_hash(json.loads(p.read_text()))})
    a,w,s=verify_live(artifacts,workflows)
    record={'contract':CONTRACT,'version':'v1','repository':'xxammaxx/Morpheus_workflow','source_commit_sha':commit,'source_branch':subprocess.check_output(['git','branch','--show-current'],text=True).strip(),'deployed_at':dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),'mode':mode,'runtime_artifacts':a,'n8n_workflows':w,'services':s,'verification':{'runtime_artifacts_match':all(x['match'] for x in a),'n8n_workflows_match':all(x['match'] for x in w),'required_services_healthy':all(x['active'] for x in s)}}
    validate(record)
    raw=json.dumps(record,sort_keys=True,separators=(',',':'))
    remote_json("""import json,os,tempfile
record=json.loads(%r); path=%r; parent=os.path.dirname(path); os.makedirs(parent,exist_ok=True)
fd,tmp=tempfile.mkstemp(prefix='.deployment-provenance.',dir=parent)
with os.fdopen(fd,'w',encoding='utf-8') as f:
 json.dump(record,f,indent=2,sort_keys=True); f.write('\\n'); f.flush(); os.fsync(f.fileno())
os.replace(tmp,path)
try:
 d=os.open(parent,os.O_DIRECTORY); os.fsync(d); os.close(d)
except OSError: pass
with open(path,encoding='utf-8') as f: json.load(f)
print(json.dumps({'written':True,'path':path}))
""" % (raw, STORE))
    return record

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument('command',choices=('attest','read')); p.add_argument('--commit',required=False); p.add_argument('--mode',default='reconcile-existing-runtime')
    args=p.parse_args()
    if args.command=='read':
        r=remote_json("import json; print(json.dumps(json.load(open(%r))))" % STORE); validate(r); print(json.dumps({'PROVENANCE_CONTRACT':r['contract'],'DEPLOYED_SOURCE_COMMIT':r['source_commit_sha'],'PROVENANCE_MODE':r['mode'],'RUNTIME_ARTIFACTS_MATCH':r['verification']['runtime_artifacts_match'],'N8N_WORKFLOWS_MATCH':r['verification']['n8n_workflows_match'],'REQUIRED_SERVICES_HEALTHY':r['verification']['required_services_healthy'],'PROVENANCE_VALID':True},sort_keys=True)); return 0
    if not args.commit: p.error('--commit is required for attest')
    print(json.dumps(attest(args.commit,args.mode),sort_keys=True)); return 0
if __name__=='__main__':
    try: raise SystemExit(main())
    except (ValueError,RuntimeError,subprocess.CalledProcessError) as e: print(str(e),file=sys.stderr); raise SystemExit(1)
