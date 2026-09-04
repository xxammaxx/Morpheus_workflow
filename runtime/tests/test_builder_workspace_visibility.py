import sys
from pathlib import Path
import os

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


def test_checkout_stage_is_descendant_and_old_sibling_bug_is_detected(tmp_path, monkeypatch):
    from adapter import harness_adapter_v2 as adapter

    root = tmp_path / "workspaces"
    ws = root / "autodev-v2-run-a"
    ws.mkdir(parents=True)
    monkeypatch.setattr(adapter, "BUILDER_WS_ROOT", str(root))

    old_tmp = str(ws) + ".checkout"
    new_tmp = adapter._checkout_stage_path(str(ws))
    assert os.path.commonpath((new_tmp, str(ws))) == str(ws)
    assert os.path.dirname(new_tmp) == str(ws)
    assert os.path.dirname(old_tmp) == str(root)
    assert old_tmp != new_tmp
    assert adapter._checkout_stage_path(str(ws)) != old_tmp


def test_checkout_stage_rejects_symlink_escape(tmp_path, monkeypatch):
    from adapter import harness_adapter_v2 as adapter

    root = tmp_path / "workspaces"
    ws = root / "autodev-v2-run-a"
    outside = tmp_path / "outside"
    ws.mkdir(parents=True)
    outside.mkdir()
    (ws / ".checkout-stage").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(adapter, "BUILDER_WS_ROOT", str(root))

    import pytest
    with pytest.raises(RuntimeError, match="BUILDER_CHECKOUT_STAGE_ESCAPE"):
        adapter._checkout_stage_path(str(ws))


def test_checkout_uses_prepared_boundary_and_cleans_stage_on_failure(tmp_path, monkeypatch):
    from adapter import harness_adapter_v2 as adapter

    root = tmp_path / "workspaces"
    ws = root / "autodev-v2-run-a"
    ws.mkdir(parents=True)
    monkeypatch.setattr(adapter, "BUILDER_WS_ROOT", str(root))
    monkeypatch.setattr(adapter, "_prepare_builder_workspace", lambda path: None)
    commands = []

    def fake_stdout(command, timeout=adapter.DEFAULT_TIMEOUT_S):
        commands.append(command)
        return ""

    def fake_exec(command, timeout=adapter.DEFAULT_TIMEOUT_S):
        commands.append(command)
        if "git clone" in command:
            return type("Result", (), {"returncode": 1, "stderr": "clone failed", "stdout": ""})()
        return type("Result", (), {"returncode": 0, "stderr": "", "stdout": ""})()

    monkeypatch.setattr(adapter, "pct_stdout", fake_stdout)
    monkeypatch.setattr(adapter, "pct_exec", fake_exec)
    import pytest
    with pytest.raises(RuntimeError, match="repository checkout failed"):
        adapter._ensure_workspace("run-a", "owner/repo")

    stage = str(ws / ".checkout-stage")
    assert any(stage in command for command in commands)
    assert not any(str(ws) + ".checkout" in command for command in commands)
    assert any(command.startswith("rm -rf --") and stage in command for command in commands)


def test_checkout_success_promotes_and_cleans_stage(tmp_path, monkeypatch):
    from adapter import harness_adapter_v2 as adapter

    root = tmp_path / "workspaces"
    ws = root / "autodev-v2-run-a"
    ws.mkdir(parents=True)
    monkeypatch.setattr(adapter, "BUILDER_WS_ROOT", str(root))
    monkeypatch.setattr(adapter, "_prepare_builder_workspace", lambda path: None)
    commands = []

    def fake_stdout(command, timeout=adapter.DEFAULT_TIMEOUT_S):
        commands.append(command)
        return ""

    def fake_exec(command, timeout=adapter.DEFAULT_TIMEOUT_S):
        commands.append(command)
        return type("Result", (), {"returncode": 0, "stderr": "", "stdout": ""})()

    monkeypatch.setattr(adapter, "pct_stdout", fake_stdout)
    monkeypatch.setattr(adapter, "pct_exec", fake_exec)
    assert adapter._ensure_workspace("run-a", "owner/repo") == str(ws)
    stage = str(ws / ".checkout-stage")
    assert any("git clone" in command and stage in command for command in commands)
    assert any("entries=(" in command and "mv --" in command for command in commands)
    assert any(command == "rm -rf -- %s" % stage for command in commands)


def test_matching_remote_does_not_reclone(tmp_path, monkeypatch):
    from adapter import harness_adapter_v2 as adapter

    root = tmp_path / "workspaces"
    ws = root / "autodev-v2-run-a"
    ws.mkdir(parents=True)
    monkeypatch.setattr(adapter, "BUILDER_WS_ROOT", str(root))
    monkeypatch.setattr(adapter, "_prepare_builder_workspace", lambda path: None)
    calls = []
    monkeypatch.setattr(adapter, "pct_stdout", lambda command, timeout=adapter.DEFAULT_TIMEOUT_S: "https://github.com/owner/repo.git")
    monkeypatch.setattr(adapter, "pct_exec", lambda command, timeout=adapter.DEFAULT_TIMEOUT_S: calls.append(command))
    assert adapter._ensure_workspace("run-a", "owner/repo") == str(ws)
    assert calls == []
