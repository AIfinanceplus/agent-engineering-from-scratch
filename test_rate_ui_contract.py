import unittest
from pathlib import Path


ROOT = Path(__file__).parent


class RateUIContractTests(unittest.TestCase):
    def test_ui_is_one_strategy_one_button_and_not_event_search(self):
        html = (ROOT / "web" / "rate_strategy.html").read_text(encoding="utf-8")
        self.assertIn("2s10s Rate Strategy", html)
        self.assertIn("Run One Paper Simulation", html)
        self.assertIn("D1", html)
        self.assertIn("S1", html)
        self.assertIn("E1", html)
        self.assertNotIn("Kalshi", html)
        self.assertNotIn("Polymarket", html)
        self.assertNotIn("Event Search", html)

    def test_client_calls_only_the_run_once_api_and_keeps_raw_details_collapsed(self):
        source = (ROOT / "web" / "rate_strategy.js").read_text(encoding="utf-8")
        html = (ROOT / "web" / "rate_strategy.html").read_text(encoding="utf-8")
        self.assertIn("/api/rates/run-once", source)
        self.assertNotIn("place_order", source)
        self.assertIn('<details class="card raw">', html)
        self.assertNotIn('<details class="card raw" open>', html)

    def test_server_makes_simple_rate_page_the_root(self):
        source = (ROOT / "serve_rates.py").read_text(encoding="utf-8")
        self.assertIn('self.path = "/rate_strategy.html"', source)
        self.assertIn('"/api/rates/run-once"', source)
        self.assertIn("No event search", source)


if __name__ == "__main__":
    unittest.main()
