import unittest
from pathlib import Path


ROOT = Path(__file__).parent


class R12UIContractTests(unittest.TestCase):
    def test_strategy_center_is_standalone_and_scans_without_research_run(self):
        source = (ROOT / "web" / "r12_ui.js").read_text(encoding="utf-8")
        self.assertIn("Strategy Opportunity Center", source)
        self.assertIn("data-nav=\"strategy\"", source)
        self.assertIn("/api/r12/structural-scan", source)
        self.assertIn("/api/r12/registry", source)
        self.assertNotIn("run_id:", source)
        self.assertIn("PAPER SIGNAL ONLY", source)
        self.assertIn("Binary complement", source)
        self.assertIn("Threshold monotonicity", source)
        self.assertIn("Exhaustive partition", source)

    def test_strategy_center_does_not_hide_execution_guardrails(self):
        source = (ROOT / "web" / "r12_ui.js").read_text(encoding="utf-8")
        # The exact enum is owned by the backend opportunity contract and rendered
        # from row.execution_status, avoiding a duplicated hard-coded UI value.
        self.assertIn("row.execution_status", source)
        self.assertIn("PAPER SIGNAL ONLY", source)
        self.assertIn("Structural edge ≠ calibrated macro alpha", source)
        self.assertIn("Settlement", source)
        self.assertIn("Implementation", source)
        self.assertIn("Liquidity", source)

    def test_r12_server_extends_r11_and_loads_strategy_ui(self):
        source = (ROOT / "serve_r12.py").read_text(encoding="utf-8")
        self.assertIn("class R12VisualizerHandler(R11VisualizerHandler)", source)
        self.assertIn('"r12_ui.js"', source)
        self.assertIn('"/api/r12/structural-scan"', source)
        self.assertIn('"/api/r12/registry"', source)
        self.assertIn("PAPER_SIGNAL_ONLY_NO_AUTO_EXECUTION", source)


if __name__ == "__main__":
    unittest.main()
