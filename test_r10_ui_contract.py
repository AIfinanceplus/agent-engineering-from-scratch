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

    def test_r10_step2_ui_exposes_t1_numeric_gap_and_payoff_bridge(self):
        base = (ROOT / "web" / "r10_ui.js").read_text(encoding="utf-8")
        step2 = (ROOT / "web" / "r10_step2.js").read_text(encoding="utf-8")
        for token in (
            "I1 Market vs Research",
            "EV LAB",
            "/api/r10/ev",
            "support score",
        ):
            self.assertIn(token, base)
        for token in (
            "T1 Numerical Research Target",
            "Numerical Mispricing / Research-Market Gap",
            "Scenario Payoff Bridge",
            "Probability 仍故意留空",
            "Instrument P&amp;L",
        ):
            self.assertIn(token, step2)

    def test_r10_step3_ui_exposes_instrument_sensitivity_risk_ev_and_no_auto_execution(self):
        step3 = (ROOT / "web" / "r10_step3.js").read_text(encoding="utf-8")
        for token in (
            "I2 Instrument Bridge",
            "P&amp;L per 1bp",
            "Sensitivity source",
            "Risk budget",
            "Loss limit",
            "EV / Worst Loss",
            "不是 Sharpe",
            "/api/r10/instrument-risk",
            "eligible for review",
        ):
            self.assertIn(token, step3)
        self.assertNotIn("execute trade", step3.lower())

    def test_r10_server_embeds_eval_and_loads_step2_step3_extensions(self):
        source = (ROOT / "serve_r10.py").read_text(encoding="utf-8")
        self.assertIn('result["embedded_eval_suite"] = suite', source)
        self.assertIn('result["numerical_research_target"] = results.get("T1")', source)
        self.assertIn('"embedded_in_run_v3"', source)
        self.assertIn('"r10_step2.js"', source)
        self.assertIn('"r10_step3.js"', source)
        self.assertIn('"/api/r10/instrument-risk"', source)
        self.assertNotIn('extra_scripts = ("r8_ui.js", "r8_eval_current.js"', source)


if __name__ == "__main__":
    unittest.main()
