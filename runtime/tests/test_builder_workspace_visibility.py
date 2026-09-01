import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def test_opencode_command_uses_builder_sandbox_and_workspace_only(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTODEV_V2_STATE", str(tmp_path / "state"))
    from adapter import harness_adapter_v2

    script = harness_adapter_v2._opencode_script(
        "/var/lib/ghiw/workspaces/autodev-v2-run-a",
        "worker",
        "worker instructions",
        "inspect fixture",
        60,
        "opencode",
        "big-pickle",
    )

    assert "bwrap --ro-bind / /" in script
    assert "--tmpfs /var/lib/ghiw/workspaces" in script
    assert "--bind /var/lib/ghiw/workspaces/autodev-v2-run-a" in script
    assert "--bind /var/lib/ghiw/workspaces/autodev-v2-run-a/.opencode/runtime-state /root/.local/share/opencode" in script
    assert "--ro-bind /root/.local/share/opencode/auth.json" in script
