"""Deterministic Git provenance primitives shared by the adapter and tests.

The adapter runs Git inside the isolated Builder workspace.  This module keeps
the representation and comparison rules independent from shell quoting and
from any particular remote execution mechanism.
"""

from __future__ import annotations

import hashlib
import json
from typing import Callable, Iterable


HARNESS_ARTIFACT_PATHS = frozenset({
    "build.jsonl",
    "build.stderr",
})
HARNESS_ARTIFACT_PREFIXES = (
    ".opencode/",
    "local_llm/",
    ".plan-canary-sentinel/",
)


def is_harness_artifact(path: str) -> bool:
    """Return true only for documented, harness-owned ephemeral paths."""

    return path in HARNESS_ARTIFACT_PATHS or path.startswith(HARNESS_ARTIFACT_PREFIXES)


def _status_change(xy: str, path: str) -> str:
    if xy == "??" or "A" in xy:
        return "add"
    if "D" in xy:
        return "delete"
    return "modify"


def parse_porcelain_v1_z(raw: str) -> list[dict[str, str]]:
    """Parse ``git status --porcelain=v1 -z`` without shell/path splitting.

    Git emits a second NUL-delimited path for renames/copies.  A rename is
    represented as a deterministic delete+add pair because the public build
    contract intentionally has only add/modify/delete change types.
    """

    fields = raw.split("\0")
    entries: list[dict[str, str]] = []
    index = 0
    while index < len(fields):
        token = fields[index]
        index += 1
        if not token:
            continue
        if len(token) < 4 or token[2] != " ":
            raise ValueError("malformed porcelain-v1-z status record")
        xy, path = token[:2], token[3:]
        if "R" in xy or "C" in xy:
            if index >= len(fields) or not fields[index]:
                raise ValueError("rename/copy status record missing source path")
            source = fields[index]
            index += 1
            entries.extend((
                {"path": source, "change": "delete"},
                {"path": path, "change": "add"},
            ))
        else:
            entries.append({"path": path, "change": _status_change(xy, path)})
    return entries


def filtered_entries(raw: str) -> list[dict[str, str]]:
    """Parse status and discard only explicitly documented harness artifacts."""

    return [entry for entry in parse_porcelain_v1_z(raw)
            if not is_harness_artifact(entry["path"])]


def manifest_fingerprint(manifest: Iterable[dict]) -> str:
    """Hash a canonical, metadata-only manifest."""

    normalized = sorted(
        (dict(item) for item in manifest),
        key=lambda item: (item.get("path", ""), item.get("change", "")),
    )
    encoded = json.dumps(
        normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def make_manifest(
    entries: Iterable[dict[str, str]],
    metadata: Callable[[str, str], tuple[int, str | None]],
) -> list[dict]:
    """Build a stable sanitized manifest from status entries.

    ``metadata(path, change)`` returns ``(size, content_sha256)``.  Deleted
    files may return a size of zero when the caller cannot recover their prior
    size, but must still provide the deterministic prior-content hash where
    available.
    """

    result = []
    for entry in entries:
        path, change = entry["path"], entry["change"]
        size, content_sha256 = metadata(path, change)
        item = {"path": path, "change": change, "size": int(size)}
        if content_sha256:
            item["content_sha256"] = content_sha256
        result.append(item)
    return sorted(result, key=lambda item: (item["path"], item["change"]))


def manifests_equal(left: Iterable[dict], right: Iterable[dict]) -> bool:
    """Compare paths, change types, sizes, and resulting content hashes."""

    def normalize(items):
        return sorted(
            [
                {
                    "path": item.get("path"),
                    "change": item.get("change"),
                    "size": item.get("size"),
                    "content_sha256": item.get("content_sha256"),
                }
                for item in items
            ],
            key=lambda item: (item["path"] or "", item["change"] or ""),
        )

    return normalize(left) == normalize(right)


def classify_build_delta(
    manifest: Iterable[dict],
    allowed_files: Iterable[str],
    *,
    changes_expected: bool,
    workspace_clean_before: bool,
    worker_returncode: int = 0,
    worker_summary: str = "",
) -> dict:
    """Apply the fail-closed Build delta gate."""

    files = list(manifest)
    allowed = set(allowed_files)
    out_of_scope = [item["path"] for item in files if item["path"] not in allowed]
    if not workspace_clean_before:
        return {"status": "failed", "failure_signature": "WORKSPACE_DIRTY_BEFORE_BUILD",
                "message": "workspace was dirty before Build"}
    if out_of_scope:
        return {"status": "failed", "failure_signature": "OUT_OF_SCOPE_MODIFICATION",
                "message": "files outside build_scope modified: %s" % ", ".join(out_of_scope)}
    if changes_expected and not files:
        return {"status": "failed", "failure_signature": "BUILD_NO_CHANGES",
                "message": "change-required Build completed without a repository delta"}
    if worker_returncode not in (0, -9) and not worker_summary:
        return {"status": "failed", "failure_signature": "BUILD_EXECUTION_FAILED",
                "message": "Builder exited without a usable result"}
    return {"status": "success", "failure_signature": None, "message": ""}


def no_change_completion_allowed(
    *,
    changes_expected: bool,
    independent_verify_passed: bool,
    head_unchanged: bool,
    workspace_clean: bool,
) -> bool:
    """Permit a zero-delta completion only after independent verification."""

    return (
        not changes_expected
        and independent_verify_passed
        and head_unchanged
        and workspace_clean
    )
