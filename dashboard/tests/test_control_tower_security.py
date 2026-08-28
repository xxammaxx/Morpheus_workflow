import ast
import unittest
from pathlib import Path


class ControlBoundarySecurityTests(unittest.TestCase):
    def test_no_shell_or_arbitrary_upstream_client(self):
        tree = ast.parse((Path(__file__).parents[1] / "control_tower.py").read_text())
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        self.assertNotIn("subprocess", names)
        source = (Path(__file__).parents[1] / "control_tower.py").read_text()
        self.assertIn("COMMAND_PATHS[command]", source)
        self.assertNotIn("execute arbitrary shell", source)

    def test_only_viewer_header(self):
        source = (Path(__file__).parents[1] / "control_tower.py").read_text()
        self.assertIn("X-Control-Tower-Token", source)
        self.assertNotIn("Access-Control-Allow-Origin", source)

    def test_runtime_write_boundary_is_explicit(self):
        source = (Path(__file__).parents[2] / "adapter/harness_adapter_v2.py").read_text()
        self.assertIn("dashboard", source)
        self.assertIn("cannot modify dashboard paths", source)

    def test_telemetry_has_no_browser_or_arbitrary_infrastructure_boundary(self):
        source = (Path(__file__).parents[1] / "telemetry.py").read_text()
        self.assertIn('method="GET"', source)
        self.assertIn('NVIDIA_QUERY', source)
        self.assertIn('"StrictHostKeyChecking=yes"', source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("verify=False", source)
        self.assertNotIn("curl -k", source)
        self.assertNotIn("self.path", source)

    def test_telemetry_secrets_and_reasoning_are_not_projected(self):
        source = (Path(__file__).parents[1] / "telemetry.py").read_text()
        self.assertIn("PROXMOX_API_TOKEN_SECRET", source)
        self.assertIn("LMSTUDIO_API_TOKEN", source)
        self.assertIn('"reasoning_content"', source)
        self.assertNotIn("reasoning_text", source)


if __name__ == "__main__":
    unittest.main()
