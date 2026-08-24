import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
import control_tower


class ProjectionTests(unittest.TestCase):
    def test_unknown_source_does_not_become_green(self):
        self.assertEqual(control_tower.safe_status(False)["status"], "UNAVAILABLE")

    def test_failure_run_ids_are_stable(self):
        self.assertEqual(control_tower.GOLDEN_RUN, "run-mt6unuge-agsdu4")
        self.assertEqual(control_tower.FAILURE_RUN, "run-mt6uony8-jjp9hf")


if __name__ == "__main__":
    unittest.main()
