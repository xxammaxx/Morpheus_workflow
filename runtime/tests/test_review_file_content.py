import os
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "adapter"))
os.environ.setdefault("AUTODEV_V2_STATE", tempfile.mkdtemp(prefix="morpheus-review-test-"))
import harness_adapter_v2 as adapter  # noqa: E402


def test_review_content_preserves_trailing_newline(monkeypatch):
    class Result:
        returncode = 0
        stdout = "MORPHEUS_BUILD_PROVENANCE_OK\n"

    monkeypatch.setattr(adapter, "pct_exec", lambda command: Result())

    content = adapter._changed_file_contents(
        "/var/lib/ghiw/workspaces/example",
        ["docs/acceptance/provenance_canary.txt"],
    )

    assert content["docs/acceptance/provenance_canary.txt"].endswith("\n")
