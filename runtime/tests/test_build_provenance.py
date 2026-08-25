"""Regression coverage for deterministic Builder delta provenance."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contracts.provenance import (  # noqa: E402
    filtered_entries,
    classify_build_delta,
    make_manifest,
    manifests_equal,
    manifest_fingerprint,
    no_change_completion_allowed,
    parse_porcelain_v1_z,
)


def test_porcelain_preserves_spaces_tabs_unicode_and_deletes():
    raw = " M path with spaces/über.py\0?? tab\tname.py\0 D gone.py\0"
    assert parse_porcelain_v1_z(raw) == [
        {"path": "path with spaces/über.py", "change": "modify"},
        {"path": "tab\tname.py", "change": "add"},
        {"path": "gone.py", "change": "delete"},
    ]


def test_rename_is_delete_add_and_harness_artifacts_are_only_exclusion():
    raw = "R  new name.py\0old name.py\0?? build.jsonl\0?? .opencode/build.log\0"
    assert parse_porcelain_v1_z(raw) == [
        {"path": "old name.py", "change": "delete"},
        {"path": "new name.py", "change": "add"},
        {"path": "build.jsonl", "change": "add"},
        {"path": ".opencode/build.log", "change": "add"},
    ]
    assert filtered_entries(raw) == [
        {"path": "old name.py", "change": "delete"},
        {"path": "new name.py", "change": "add"},
    ]


def test_manifest_hash_is_stable_and_delivery_equivalence_is_exact():
    entries = [{"path": "src/a.py", "change": "modify"}]
    manifest = make_manifest(entries, lambda _path, _change: (3, "a" * 64))
    assert manifest == [{
        "path": "src/a.py", "change": "modify", "size": 3,
        "content_sha256": "a" * 64,
    }]
    assert manifest_fingerprint(manifest) == manifest_fingerprint(list(reversed(manifest)))
    assert manifests_equal(manifest, list(manifest))
    assert not manifests_equal(manifest, [{**manifest[0], "content_sha256": "b" * 64}])


def test_empty_delta_is_not_a_success_for_change_required_semantics():
    assert classify_build_delta([], ["src/a.py"], changes_expected=True,
                                workspace_clean_before=True)["failure_signature"] == "BUILD_NO_CHANGES"
    assert manifests_equal([], [])
    assert manifest_fingerprint([])


def test_regression_matrix_dirty_scope_and_worker_boundaries():
    manifest = [{"path": "src/a.py", "change": "modify", "size": 1,
                 "content_sha256": "a" * 64}]
    assert classify_build_delta(manifest, ["src/a.py"], changes_expected=True,
                                workspace_clean_before=True)["status"] == "success"
    assert classify_build_delta(manifest, ["src/b.py"], changes_expected=True,
                                workspace_clean_before=True)["failure_signature"] == "OUT_OF_SCOPE_MODIFICATION"
    assert classify_build_delta(manifest, ["src/a.py"], changes_expected=True,
                                workspace_clean_before=False)["failure_signature"] == "WORKSPACE_DIRTY_BEFORE_BUILD"
    assert classify_build_delta([], ["src/a.py"], changes_expected=True,
                                workspace_clean_before=True, worker_returncode=1,
                                worker_summary="")["failure_signature"] == "BUILD_NO_CHANGES"


def test_no_change_requires_explicit_semantics_and_independent_verify():
    assert no_change_completion_allowed(
        changes_expected=False, independent_verify_passed=True,
        head_unchanged=True, workspace_clean=True,
    )
    assert not no_change_completion_allowed(
        changes_expected=False, independent_verify_passed=False,
        head_unchanged=True, workspace_clean=True,
    )
    assert not no_change_completion_allowed(
        changes_expected=False, independent_verify_passed=True,
        head_unchanged=False, workspace_clean=True,
    )
