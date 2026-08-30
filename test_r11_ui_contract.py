import unittest
from pathlib import Path


ROOT = Path(__file__).parent


class R11UIContractTests(unittest.TestCase):
    def test_r11_ui_exposes_p1_constraint_sizing_without_execution(self):
        source = (ROOT / "web" / "r11_ui.js").read_text(encoding="utf-8")
        for token in (
            "P1 Position Sizing",
            "Calculate Max Admissible Size",
            "/api/r11/size",
            "max_position_nav_fraction",
            "capital_required_per_reference_position",
            "Portfolio risk",
            "Kelly",
            "不授权执行",
        ):
            self.assertIn(token, source)

    def test_r11_server_extends_r10_and_keeps_sizing_post_research(self):
        source = (ROOT / "serve_r11.py").read_text(encoding="utf-8")
        self.assertIn("class R11VisualizerHandler(R10VisualizerHandler)", source)
        self.assertIn('if self.path == "/api/r11/size"', source)
        self.assertIn('run.get("r10_instrument_risk_ev")', source)
        self.assertIn('run["r11_position_size"] = artifact', source)
        self.assertNotIn("R11ResearchPlanner", source)

    def test_r11_css_is_loaded_as_extension(self):
        source = (ROOT / "web" / "r11_ui.js").read_text(encoding="utf-8")
        self.assertIn("r11.css?v=r11-v1", source)


if __name__ == "__main__":
    unittest.main()
