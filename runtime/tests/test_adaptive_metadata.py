"""Regression tests for immutable adaptive benchmark provenance."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "adapter"))
os.environ.setdefault("AUTODEV_V2_STATE", tempfile.mkdtemp(prefix="morpheus-adaptive-metadata-"))

from contracts import registry  # noqa: E402
import harness_adapter_v2 as adapter  # noqa: E402


def metadata(**overrides):
    value = {
        "contract": "autodev.adaptive-metadata.v1", "version": "v1",
        "experiment_id": "morpheus-test-001", "benchmark_task_id": "d-001",
        "benchmark_split": "development", "candidate_id": None,
        "factor": "BASELINE", "context_policy": "disabled",
        "repo_explorer_policy": "disabled", "experience_policy": "disabled",
        "config_hash": "a" * 64, "task_set_hash": "b" * 64,
        "harness_version": "v1",
    }
    value.update(overrides)
    return value


def issue_with_metadata(value):
    return {
        "contract": "autodev.issue.v1", "version": "v1", "run_id": "run-test-001",
        "repository_ref": "owner/repo", "workspace": "ws-test",
        "task_description": "Implement a small serialization helper with tests.",
        "x-metadata": {"adaptive_metadata": value},
    }


def test_adaptive_metadata_contract_accepts_canonical_value():
    assert registry.validate(metadata(), "autodev.adaptive-metadata.v1")["ok"]


@pytest.mark.parametrize("change", [
    {"factor": "NOT_A_FACTOR"},
    {"experiment_id": "../../other-experiment"},
])
def test_metadata_tampering_fails_closed(change):
    value = metadata(**change)
    _, error = adapter._dispatch(
        "run-test-001", "run-test-001:baseline:1", "baseline",
        "run-test-001:baseline:1", "autodev.issue.v1", issue_with_metadata(value),
        "embedded", fixture="malformed_response",
    )
    assert error and error["error"]["code"] == "ADAPTIVE_METADATA_INVALID"


def test_valid_metadata_is_attached_to_adapter_record():
    record, error = adapter._dispatch(
        "run-test-002", "run-test-002:baseline:1", "baseline",
        "run-test-002:baseline:1", "autodev.issue.v1", issue_with_metadata(metadata()),
        "embedded", fixture="malformed_response",
    )
    assert error is None
    assert record["adaptive_metadata"] == metadata()


def test_config_hash_rebind_is_not_equal():
    assert not adapter._adaptive_metadata_equal(metadata(), metadata(config_hash="c" * 64))


@pytest.mark.parametrize("body_metadata, expected", [
    (metadata(config_hash="c" * 64), "ADAPTIVE_METADATA_REBIND"),
    ({**metadata(), "unexpected": True}, "ADAPTIVE_METADATA_INVALID"),
])
def test_job_envelope_metadata_binding_fails_closed(body_metadata, expected):
    assert adapter._validate_adaptive_metadata_binding(body_metadata, metadata()).startswith(expected)


def test_job_envelope_metadata_binding_accepts_exact_copy():
    assert adapter._validate_adaptive_metadata_binding(metadata(), metadata()) is None


def test_plan_scope_failure_is_reproduced_without_relaxing_contract():
    plan = {
        "targets": {"files": ["runtime/providers/catalog.py", "runtime/providers/router.py"]},
        "build_scope": {"allowed_files": ["runtime/providers/catalog.py"]},
    }
    errors = adapter._plan_scope_errors(plan)
    assert errors == [
        "$.build_scope: targets outside allowed_files: runtime/providers/router.py"
    ]
