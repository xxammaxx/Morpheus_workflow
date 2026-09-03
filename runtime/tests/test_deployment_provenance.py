import json, subprocess
from pathlib import Path
import pytest

from scripts.deployment_provenance import atomic_write, semantic_hash, validate

def good(tmp_path):
    return {"contract":"autodev.deployment-provenance.v1","version":"v1","repository":"xxammaxx/Morpheus_workflow","source_commit_sha":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),"source_branch":"test","deployed_at":"2026-09-03T00:00:00Z","mode":"reconcile-existing-runtime","runtime_artifacts":[{"source_path":"x","deployed_path":"/x","source_sha256":"a"*64,"deployed_sha256":"a"*64,"match":True}],"n8n_workflows":[{"workflow_name":"w","source_semantic_sha256":"b"*64,"live_semantic_sha256":"b"*64,"match":True}],"services":[{"name":"svc","active":True}],"verification":{"runtime_artifacts_match":True,"n8n_workflows_match":True,"required_services_healthy":True}}

def test_workflow_normalization_preserves_material_fields():
    a={"id":"1","updatedAt":"x","nodes":[{"type":"n","parameters":{"responseCode":202},"credentials":{"x":{"id":"7"}}}],"connections":{}}
    b={**a,"id":"2","updatedAt":"y"}
    assert semantic_hash(a)==semantic_hash(b)
    c=json.loads(json.dumps(a)); c["nodes"][0]["parameters"]["responseCode"]=200
    assert semantic_hash(a)!=semantic_hash(c)

def test_failed_verification_cannot_update(tmp_path):
    r=good(tmp_path); r["runtime_artifacts"][0]["match"]=False
    with pytest.raises(ValueError): atomic_write(r,str(tmp_path/"p.json"))
    assert not (tmp_path/"p.json").exists()

def test_atomic_update_keeps_previous_record(tmp_path):
    path=tmp_path/"p.json"; r=good(tmp_path); atomic_write(r,str(path)); before=path.read_text()
    bad=good(tmp_path); bad["n8n_workflows"][0]["match"]=False
    with pytest.raises(ValueError): atomic_write(bad,str(path))
    assert path.read_text()==before

def test_invalid_sha_rejected(tmp_path):
    r=good(tmp_path); r["source_commit_sha"]="bad"
    with pytest.raises(ValueError): validate(r)

def test_partial_verification_rejected(tmp_path):
    r=good(tmp_path); r["runtime_artifacts"][0]["deployed_sha256"]="c"*64
    with pytest.raises(ValueError): validate(r)
