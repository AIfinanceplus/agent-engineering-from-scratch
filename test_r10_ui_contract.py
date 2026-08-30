import unittest
from pathlib import Path


ROOT = Path(__file__).parent


class R10UIContractTests(unittest.TestCase):
    def test_evaluation_center_is_embedded_and_does_not_fetch_eval_endpoint(self):
        source = (ROOT / "web" / "r10_ui.js").read_text(encoding="utf-8")
        self.assertIn("embedded_eval_suite", source)
        self.assertIn("openR10EvalCenter", source)
        self.assertIn("EVALUATION CENTER", source)
        self.assertIn("HTTP Eval fetch = NONE", source)
        self.assertNotIn("fetch('/api/eval/current'", source)
        self.assertNotIn("fetch('/api/r8/eval'", source)
        self.assertIn("r10InspectorEvalTab.style.display = 'none'", source)

    def test_r10_ui_exposes_i1_market_comparison_and_ev_lab(self):
        source = (ROOT / "web" / "r10_ui.js").read_text(encoding="utf-8")
        for token in (
            "I1 Market vs Research",
            "Research View",
            "Observed Market View",
            "Pricing Hypothesis / Mispricing Gate",
            "EV LAB",
            "/api/r10/ev",
            "support score",
        ):
            self.assertIn(token, source)

    def test_r10_server_embeds_eval_in_same_run_result(self):
        source = (ROOT / "serve_r10.py").read_text(encoding="utf-8")
        self.assertIn('result["embedded_eval_suite"] = suite', source)
        self.assertIn('"embedded_in_run_v3"', source)
        self.assertNotIn('extra_scripts = ("r8_ui.js", "r8_eval_current.js"', source)


if __name__ == "__main__":
    unittest.main()
