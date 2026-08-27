import unittest
from pathlib import Path


APP = (Path(__file__).parents[1] / "static/app.js").read_text()


class CommandLifecycleTests(unittest.TestCase):
    def test_rendering_does_not_bind_command_handlers(self):
        self.assertNotIn("querySelectorAll('.test-command,.admin-action')", APP)
        self.assertIn("const commandButtonSelector = '.test-command,.admin-action,.project-command'", APP)
        self.assertIn("document.addEventListener('click', eventObject => { const button = eventObject.target?.closest?.(commandButtonSelector)", APP)

    def test_command_dispatch_is_bind_once_and_in_flight_guarded(self):
        self.assertEqual(APP.count("const commandButtonSelector ="), 1)
        self.assertIn("if (button.dataset.commandInFlight === 'true') return;", APP)
        self.assertIn("button.dataset.commandInFlight = 'true';", APP)
        self.assertIn("delete button.dataset.commandInFlight;", APP)
        self.assertIn("if (rendering) return; await baseRender();", APP)

    def test_navigation_uses_one_delegated_owner(self):
        self.assertNotIn("document.querySelectorAll('.tabs button').forEach(button => button.addEventListener", APP)
        self.assertEqual(APP.count("document.addEventListener('click', eventObject => { const button = eventObject.target?.closest?.('[data-view]')"), 1)


if __name__ == "__main__":
    unittest.main()
