import unittest
from pathlib import Path


ROOT = Path(__file__).parent


class R12Step4UIContractTests(unittest.TestCase):
    def test_server_loads_step6_agent_ui_and_routes(self):
        source = (ROOT / "serve_r12.py").read_text(encoding="utf-8")
        self.assertIn('"r12_step4.js"', source)
        self.assertIn('"/api/r12/agent/start"', source)
        self.assertIn('"/api/r12/agent/status"', source)
        self.assertIn('"/api/r12/agent/approve"', source)
        self.assertIn('"/api/r12/agent/resume"', source)
        self.assertIn("Tool DAG -> durable pause -> human approval", source)

    def test_ui_exposes_durable_human_gate_without_auto_checking_boxes(self):
        source = (ROOT / "web" / "r12_step4.js").read_text(encoding="utf-8")
        self.assertIn("HUMAN-IN-THE-LOOP STRATEGY AGENT", source)
        self.assertIn("WAITING_HUMAN_IDENTITY_APPROVAL", source)
        self.assertIn("Approve H1 and Resume", source)
        self.assertIn("run.results", source)
        self.assertIn("run.checkpoints", source)
        self.assertIn("data-r12-identity", source)
        self.assertIn("NO_AUTO_EXECUTION", source)
        self.assertNotIn("input.checked = true", source)
        self.assertNotIn(".checked=true", source)

    def test_step6_css_is_loaded_as_extension(self):
        source = (ROOT / "web" / "r12_step4.js").read_text(encoding="utf-8")
        self.assertIn("r12_step4.css?v=r12-step6-v1", source)


if __name__ == "__main__":
    unittest.main()
