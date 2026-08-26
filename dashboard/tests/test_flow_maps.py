import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
HTML = (ROOT / "static/index.html").read_text()
APP = (ROOT / "static/app.js").read_text()
CSS = (ROOT / "static/styles.css").read_text()


class FlowMapTests(unittest.TestCase):
    def test_navigation_order_and_views(self):
        labels = re.findall(r'<button data-view="[^"]+">([^<]+)</button>', HTML)
        self.assertEqual(labels[:8], ["Übersicht", "Projekte", "Läufe", "Anbieter", "Systemkarte", "Datenfluss", "Debugging", "Administration"])
        self.assertIn('id="system-map-view"', HTML)
        self.assertIn('id="data-flow-view"', HTML)

    def test_mermaid_is_local_and_strict(self):
        self.assertIn('src="/static/vendor/mermaid/mermaid.min.js"', HTML)
        self.assertNotRegex(HTML + APP, r"(?:jsdelivr|unpkg|cdnjs)")
        self.assertIn("securityLevel:'strict'", APP)
        self.assertIn("deterministicIds:true", APP)

    def test_architecture_and_data_contract_nodes_are_static(self):
        for node in ("SYS_START", "SYS_ORCH", "SYS_RUN", "SYS_BASE", "SYS_RESEARCH", "SYS_PLAN", "SYS_GATE", "SYS_BUILD", "SYS_VERIFY", "SYS_REVIEW", "SYS_DECIDE", "SYS_FIX", "SYS_SPLIT", "SYS_ADAPTER", "SYS_CT", "SYS_OC", "SYS_ROUTER", "SYS_OPENROUTER", "SYS_OLLAMA", "SYS_LMSTUDIO", "SYS_GITHUB", "SYS_PR", "SYS_MERGE", "SYS_POST", "SYS_DASH"):
            self.assertIn(node, APP)
        for node in ("DF_INTAKE", "DF_RUN", "DF_BASE", "DF_RESEARCH", "DF_PLAN", "DF_GATE", "DF_BUILD_INPUT", "DF_BUILD_RESULT", "DF_PROVENANCE", "DF_VERIFY", "DF_REVIEW", "DF_DECISION", "DF_DELTA", "DF_MANIFEST", "DF_PR", "DF_MERGE", "DF_POST", "DF_TERMINAL", "DF_PROJECTION"):
            self.assertIn(node, APP)

    def test_mapping_and_shared_selection_are_deterministic(self):
        for state, node in (("BUILDING", "SYS_BUILD"), ("VERIFYING", "SYS_VERIFY"), ("REVIEWING", "SYS_REVIEW"), ("DECIDING", "SYS_DECIDE"), ("DONE", "SYS_POST"), ("BUILDING", "DF_BUILD_RESULT"), ("VERIFYING", "DF_VERIFY"), ("REVIEWING", "DF_REVIEW"), ("DECIDING", "DF_DECISION"), ("DONE", "DF_TERMINAL")):
            self.assertRegex(APP, rf"{state}:'{node}'")
        self.assertIn("morpheus-control-tower-tracked-run", APP)
        self.assertIn("sessionStorage.setItem(trackedRunKey", APP)
        self.assertIn("activeStates", APP)
        self.assertIn("terminalStates", APP)

    def test_runtime_values_are_not_mermaid_source(self):
        self.assertIn("FLOW_TOPOLOGY[kind]", APP)
        self.assertIn("window.mermaid.render", APP)
        self.assertNotIn("run_id", APP.split("FLOW_TOPOLOGY", 1)[1].split("const SYSTEM_STAGE", 1)[0])
        self.assertIn("textContent =", APP)

    def test_read_only_and_accessible_position(self):
        for label in ("Lauf auswählen", "Verfolgter Lauf", "Aktuelle Position", "Blockiert"):
            self.assertIn(label, HTML + APP)
        self.assertIn('role="status"', HTML)
        self.assertIn("aria-label", APP)
        self.assertIn("prefers-reduced-motion", CSS)
        self.assertIn("X-Control-Tower-Request", APP)
        self.assertIn("/api/v1/commands", APP)
        self.assertNotIn("XMLHttpRequest", APP)


if __name__ == "__main__":
    unittest.main()
