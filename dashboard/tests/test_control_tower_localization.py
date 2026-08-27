import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class LocalizationTests(unittest.TestCase):
    def test_document_is_german_and_has_no_standard_english_ui(self):
        html = (ROOT / "static/index.html").read_text()
        self.assertIn('<html lang="de">', html)
        self.assertIn("Morpheus Leitstand", html)
        denylist = ("Control Tower", "Awaiting authentication", "Viewer authentication", "Open dashboard", "Overview", "Providers", "Dashboard views", "Run summary", "Free provider pool", "Recent runs", "Active alerts", "Search run ID", "Provider runtime", "Authentication failed")
        for phrase in denylist:
            self.assertNotIn(phrase, html)

    def test_runtime_localization_maps_known_values_and_has_german_fallback(self):
        app = (ROOT / "static/app.js").read_text()
        for phrase in ("Angenommen", "Baseline wird erstellt", "Recherche läuft", "Build läuft", "Verifikation läuft", "Review läuft", "Entscheidung läuft", "Abgeschlossen", "Eingeschränkt", "Nicht verfügbar", "Versuch gestartet", "Ja", "Nein", "Nicht bekannt", "Technischer Grund", "de-DE", "hour12:false"):
            self.assertIn(phrase, app)
        self.assertRegex(app, re.compile(r"map\[raw\] \|\|.*prefix"))

    def test_dashboard_version_is_current(self):
        source = (ROOT / "control_tower.py").read_text()
        self.assertIn('VERSION = "1.2.0"', source)
        self.assertNotIn("1.1.0-rc1", source)
        self.assertNotIn("v1.1.0-candidate", source)


if __name__ == "__main__":
    unittest.main()
