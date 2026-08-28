"""The external verifier must not mask failed commands behind output filters."""

from pathlib import Path


ADAPTER = (Path(__file__).parents[2] / "adapter" / "harness_adapter_v2.py").read_text()


def test_verify_pipelines_preserve_upstream_failure_status():
    assert (
        "set -o pipefail; cd '%s' && PYTHONPATH=src python3 -m pytest -q tests 2>&1 | tail -20"
        in ADAPTER
    )
    assert "set -o pipefail; cd '%s' && node --test 2>&1 | tail -20" in ADAPTER
    assert "set -o pipefail; cd '%s' && python3 -m compileall -q src tests 2>&1 | head -5" in ADAPTER
