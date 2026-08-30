import unittest
from pathlib import Path


ROOT = Path(__file__).parent


class R9UIContractTests(unittest.TestCase):
    def test_eval_client_posts_only_run_id_to_current_run_endpoint(self):
        source = (ROOT / "web" / "r8_eval_current.js").read_text(encoding="utf-8")
        self.assertIn("fetch('/api/eval/current'", source)
        self.assertIn("JSON.stringify({run_id: appState.run.run_id})", source)
        self.assertNotIn("research_result: appState.run", source)
        self.assertIn("cache: 'no-store'", source)

    def test_r9_market_ui_exposes_observed_context_and_r10_boundary(self):
        source = (ROOT / "web" / "r9_ui.js").read_text(encoding="utf-8")
        for token in (
            "Observed Market Context",
            "EFFR",
            "10Y Real",
            "Breakeven cross-check gap",
            "Research Evidence ≠ Market Evidence",
            "R10",
        ):
            self.assertIn(token, source)


if __name__ == "__main__":
    unittest.main()
