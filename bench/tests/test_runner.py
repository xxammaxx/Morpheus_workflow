import json
import os
import tempfile
from pathlib import Path

import pytest

from bench.runner.runner import (
    BenchmarkError,
    FACTORS,
    HttpClient,
    experience_for,
    load_task_set,
    local_fixture_verifier,
    materialize_local_fixture,
    run_one,
    safe_relative_path,
    sha256_json,
    task_hash,
    task_set_hash,
)
os.environ.setdefault("AUTODEV_V2_STATE", tempfile.mkdtemp(prefix="morpheus-bench-adapter-test-"))
import adapter.harness_adapter_v2 as adapter


class FakeN8N:
    def __init__(self, run_id):
        self.run_id = run_id

    def request(self, method, path, body=None, timeout=None):
        if method == "POST":
            return 202, {"run_id": self.run_id, "status": "ACCEPTED"}
        return 200, {"run_id": self.run_id, "state": "DONE", "correlation_id": "ct-test"}


class FakeAdapter:
    def __init__(self, run_id, metadata):
        self.run_id = run_id
        self.metadata = metadata

    def request(self, method, path, body=None, timeout=None):
        if path == "/healthz":
            return 200, {"status": "ok"}
        if path == "/v1/status/runtime":
            return 200, {"automatic_paid_agent_escalation": False, "providers": [{"provider": "opencode", "model": "big-pickle", "free_eligible": True, "actual_cost_proof": True}]}
        return 200, {"data": {"job_type": "plan", "adaptive_metadata": self.metadata, "duration_ms": 1, "result": {"contract": "autodev.plan.v1", "targets": {"files": ["src/config.py"], "symbols": ["parse_mode"]}}}}


def test_all_task_sets_are_executable_and_frozen():
    development = load_task_set("development")
    validation = load_task_set("validation")
    holdout = load_task_set("holdout", allow_holdout=True)
    assert len(development) == 4
    assert len(validation) == 2
    assert len(holdout) == 2
    assert {task["task_class"] for task in development} == {"STRUCTURED_OUTPUT", "REPOSITORY_NAVIGATION", "READ_ONLY_ANALYSIS", "TOOL_SELECTION"}
    assert {task["task_class"] for task in validation} == {"SMALL_CODE_CHANGE", "FAILURE_RECOVERY"}
    assert all(len(task["task_hash"]) == 64 for task in development + validation + holdout)
    assert task_set_hash(development) == "6e1d9cb88d5ab46bc99f4c6d0e85c69633e411af48490d2cae90848653c2b962"


def test_holdout_loader_is_closed_by_default():
    with pytest.raises(BenchmarkError, match="HOLDOUT_ACCESS_DENIED"):
        load_task_set("holdout")


def test_task_hash_changes_when_input_changes():
    task = load_task_set("development")[0]
    changed = dict(task)
    changed["input"] = {"changed": True}
    assert task_hash(task) != task_hash(changed)


@pytest.mark.parametrize("value", ["../escape", "/absolute", "a\\b", "a//b", "a/.git/x"])
def test_task_path_security(value):
    with pytest.raises(BenchmarkError):
        safe_relative_path(value)


def test_fixture_materialization_and_cleanup_verifier():
    task = load_task_set("validation")[0]
    root = materialize_local_fixture(task)
    try:
        expected = task["verifier"]["expected_files"]["src/slug.py"]
        (root / "src/slug.py").write_text(expected, encoding="utf-8")
        assert local_fixture_verifier(task, root) == (True, "PASS")
    finally:
        import shutil
        shutil.rmtree(root)


def test_experience_excludes_same_task_and_holdout(tmp_path):
    tasks = load_task_set("development")
    (tmp_path / "prior.json").write_text(json.dumps({"split": "development", "task_id": "d-002", "verification_result": "PASS"}), encoding="utf-8")
    with pytest.raises(BenchmarkError, match="EXPERIENCE_SOURCE_EMPTY"):
        experience_for(tasks, tmp_path, tasks[1], "EXPERIENCE_TOP1")
    assert experience_for(tasks, tmp_path, tasks[0], "EXPERIENCE_TOP1")[0]["task_id"] == "d-002"
    assert not any(item["task_id"].startswith("h-") for item in experience_for(tasks, tmp_path, tasks[0], "EXPERIENCE_TOP3"))


def test_runner_uses_canonical_n8n_and_persists_idempotent_result(tmp_path):
    task = load_task_set("development")[0]
    split_hash = task_set_hash([task])
    config = {"provider": "opencode", "model": "big-pickle", "factor": "BASELINE", "policies": ("disabled", "disabled", "disabled"), "max_attempts": 1, "timeout_seconds": 180, "verifier": task["verifier"], "runtime_generation": "canonical-n8n"}
    config_hash = sha256_json(config)
    metadata = {"contract": "autodev.adaptive-metadata.v1", "version": "v1", "experiment_id": "morpheus-test-001", "benchmark_task_id": "d-001", "benchmark_split": "development", "candidate_id": None, "factor": "BASELINE", "context_policy": "disabled", "repo_explorer_policy": "disabled", "experience_policy": "disabled", "config_hash": config_hash, "task_set_hash": split_hash, "harness_version": "v1"}
    identity = "morpheus-test-001:d-001:BASELINE:" + config_hash
    import hashlib
    run_id = "run-mb-" + hashlib.sha256(identity.encode()).hexdigest()[:20]
    result = run_one(task, split="development", split_digest=split_hash, factor="BASELINE", experiment_id="morpheus-test-001", candidate_id=None, n8n=FakeN8N(run_id), adapter=FakeAdapter(run_id, metadata), evidence_dir=tmp_path, provider="opencode", model="big-pickle", repository_ref="fixture-only", max_wait=1, experience=[])
    assert result["run_id"] == run_id
    assert result["verification_result"] == "PASS"
    assert result["actual_cost"] == "UNKNOWN"
    assert result["result_hash"]
    replay = run_one(task, split="development", split_digest=split_hash, factor="BASELINE", experiment_id="morpheus-test-001", candidate_id=None, n8n=FakeN8N(run_id), adapter=FakeAdapter(run_id, metadata), evidence_dir=tmp_path, provider="opencode", model="big-pickle", repository_ref="fixture-only", max_wait=1, experience=[])
    assert replay["replay"] == "REPLAY_EXISTING"


def test_factor_policy_is_closed():
    assert FACTORS == ("BASELINE", "CONTEXT_COMPILER", "CONTEXT_PLUS_EXPLORER", "EXPERIENCE_TOP1", "EXPERIENCE_TOP3")


def test_adapter_fixture_materialization_is_bounded(monkeypatch, tmp_path):
    monkeypatch.setattr(adapter, "BUILDER_WS_ROOT", str(tmp_path))
    workspace = tmp_path / "run-1"
    assert adapter._materialize_benchmark_fixture(str(workspace), {"files": {"src/a.py": "VALUE = 1\n"}}) == str(workspace)
    assert (workspace / "src/a.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    with pytest.raises(RuntimeError, match="BENCHMARK_FIXTURE_PATH_INVALID"):
        adapter._materialize_benchmark_fixture(str(tmp_path / "run-2"), {"files": {"../escape": "x"}})
