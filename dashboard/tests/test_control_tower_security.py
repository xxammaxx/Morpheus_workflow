import ast
import unittest
from pathlib import Path


class ReadOnlySecurityTests(unittest.TestCase):
    def test_no_shell_or_mutating_upstream_client(self):
        tree = ast.parse((Path(__file__).parents[1] / "control_tower.py").read_text())
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        self.assertNotIn("subprocess", names)
        methods = {node.value.s for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in {"POST", "PUT", "PATCH", "DELETE"}}
        self.assertFalse(methods)

    def test_only_viewer_header(self):
        source = (Path(__file__).parents[1] / "control_tower.py").read_text()
        self.assertIn("X-Control-Tower-Token", source)
        self.assertNotIn("Access-Control-Allow-Origin", source)


if __name__ == "__main__":
    unittest.main()
