#!/usr/bin/env python3
"""Compare a canonical Build manifest with one exact Git delivery commit."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

from contracts.provenance import manifest_fingerprint, manifests_equal


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args])


def status_entries(repo: Path, commit: str) -> list[dict[str, str]]:
    parent = f"{commit}^"
    raw = git(repo, "diff-tree", "--root", "-r", "--name-status", "-z",
              "--find-renames", parent, commit)
    fields = raw.split(b"\0")
    result = []
    index = 0
    while index < len(fields):
        token = fields[index]
        index += 1
        if not token:
            continue
        status = token.decode("ascii")
        if index >= len(fields):
            raise ValueError("diff-tree status record missing path")
        path = fields[index].decode("utf-8", "surrogateescape")
        index += 1
        kind = status[:1]
        if kind in ("R", "C"):
            destination = fields[index].decode("utf-8", "surrogateescape")
            index += 1
            result.extend((
                {"path": path, "change": "delete"},
                {"path": destination, "change": "add"},
            ))
        else:
            result.append({
                "path": path,
                "change": {"A": "add", "M": "modify", "D": "delete"}[kind],
            })
    return result


def metadata(repo: Path, commit: str, path: str, change: str) -> tuple[int, str]:
    source_commit = f"{commit}^" if change == "delete" else commit
    data = subprocess.check_output(
        ["git", "-C", str(repo), "show", f"{source_commit}:{path}"]
    )
    return len(data), hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-result", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()

    build_result = json.loads(args.build_result.read_text(encoding="utf-8"))
    metadata_block = (build_result.get("x-metadata") or {}).get("build_provenance") or {}
    build_manifest = metadata_block.get("manifest") or []
    entries = status_entries(args.repo, args.commit)
    delivery_manifest = []
    for entry in entries:
        size, digest = metadata(args.repo, args.commit, entry["path"], entry["change"])
        delivery_manifest.append({**entry, "size": size, "content_sha256": digest})
    delivery_manifest.sort(key=lambda item: (item["path"], item["change"]))
    output = {
        "build_delta_fingerprint": metadata_block.get("delta_fingerprint"),
        "delivery_delta_fingerprint": manifest_fingerprint(delivery_manifest),
        "build_manifest": build_manifest,
        "delivery_manifest": delivery_manifest,
        "build_delta_matches_delivery": manifests_equal(build_manifest, delivery_manifest),
        "delivery_commit": args.commit,
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if output["build_delta_matches_delivery"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
