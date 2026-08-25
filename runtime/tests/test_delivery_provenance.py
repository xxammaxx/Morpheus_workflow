"""Regression tests for exact Builder-to-delivery manifest comparison."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contracts.provenance import manifests_equal  # noqa: E402


def test_delivery_mismatch_is_fail_closed():
    build = [{"path": "dashboard/app.js", "change": "modify", "size": 1,
              "content_sha256": "a" * 64}]
    delivery = [{"path": "dashboard/app.js", "change": "modify", "size": 1,
                 "content_sha256": "b" * 64}]
    assert not manifests_equal(build, delivery)


def test_delivery_exact_match_passes():
    manifest = [{"path": "dashboard/app.js", "change": "modify", "size": 1,
                 "content_sha256": "a" * 64}]
    assert manifests_equal(manifest, list(manifest))
