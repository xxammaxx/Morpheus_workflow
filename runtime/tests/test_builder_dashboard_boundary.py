from pathlib import Path


ADAPTER = (Path(__file__).parents[2] / "adapter/harness_adapter_v2.py").read_text()


def test_runtime_builder_denies_control_tower_scope_before_worker_dispatch():
    assert "DASHBOARD_RUNTIME_DENY_TERMS" in ADAPTER
    assert "_runtime_dashboard_scope_denied" in ADAPTER
    assert "RUNTIME_DASHBOARD_SCOPE_DENIED" in ADAPTER
    assert 'failure_class="SECURITY_BLOCK"' in ADAPTER
    assert '"morpheus_builder_dashboard_access": False' in ADAPTER
    assert '"qwen_dashboard_modifications": 0' in ADAPTER
