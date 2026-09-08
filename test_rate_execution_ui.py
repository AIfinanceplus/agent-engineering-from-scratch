import unittest
from pathlib import Path


ROOT = Path(__file__).parent


class PartialFillConsoleContractTests(unittest.TestCase):
    def test_partial_fill_race_is_exposed_end_to_end(self):
        html = (ROOT / "web" / "rate_console.html").read_text(encoding="utf-8")
        client = (ROOT / "web" / "rate_console.js").read_text(encoding="utf-8")
        server = (ROOT / "serve_rates.py").read_text(encoding="utf-8")
        self.assertIn('value="execution_race"', html)
        self.assertIn('value="paper_fill_accounting"', html)
        self.assertIn("/api/rates/execution-race", client)
        self.assertIn("/api/rates/paper-fill", client)
        self.assertIn("/api/rates/execution-race", server)
        self.assertIn("/api/rates/paper-fill", server)
        self.assertIn("partial_fill_cancel_race", server)
        self.assertIn("paper_fill_accounting", server)
        self.assertIn('row["passed"] = True', server)
        self.assertIn("fill_deduplicated", client + server)
        self.assertIn("FILLED ", client)
        self.assertIn("CANCELED ", client)
        self.assertIn("REALIZED P&L", client)


if __name__ == "__main__":
    unittest.main()
