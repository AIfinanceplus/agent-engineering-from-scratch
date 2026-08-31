from datetime import date, timedelta
import unittest

from rate_sources import FredCurveHistorySource, RateSourceError
from rate_strategy import evaluate_rate_simulation, simulate_one_curve_trade


def completed_steepener_history() -> dict:
    start = date(2026, 1, 1)
    rows = []
    for index in range(81):
        if index < 60:
            spread_bps = 0.0
        elif index < 80:
            spread_bps = -100.0
        else:
            spread_bps = 20.0
        dgs2 = 4.0
        dgs10 = dgs2 + spread_bps / 100
        rows.append(
            {
                "date": (start + timedelta(days=index)).isoformat(),
                "dgs2": dgs2,
                "dgs10": dgs10,
                "spread_bps": spread_bps,
            }
        )
    return {
        "artifact_type": "rate_curve_history",
        "provider": "FRED",
        "source_mode": "public_csv",
        "series": [],
        "start_date": rows[0]["date"],
        "as_of": rows[-1]["date"],
        "observation_count": len(rows),
        "observations": rows,
        "guardrails": {"values_fabricated": False},
    }


class FredCurveHistorySourceTests(unittest.TestCase):
    def test_aligns_common_dates_and_drops_missing_values(self):
        responses = {
            "DGS2": "DATE,DGS2\n2026-01-02,4.00\n2026-01-03,.\n2026-01-04,4.10\n",
            "DGS10": "observation_date,DGS10\n2026-01-02,4.30\n2026-01-03,4.40\n2026-01-04,4.35\n",
        }

        def transport(url):
            return responses["DGS2" if "id=DGS2&" in url else "DGS10"]

        result = FredCurveHistorySource(transport=transport).fetch("2026-01-01")
        self.assertEqual(result["observation_count"], 2)
        self.assertEqual(result["as_of"], "2026-01-04")
        self.assertAlmostEqual(result["observations"][0]["spread_bps"], 30)
        self.assertTrue(result["guardrails"]["common_dates_only"])
        self.assertFalse(result["guardrails"]["api_key_required"])

    def test_empty_series_fails_closed(self):
        with self.assertRaises(RateSourceError):
            FredCurveHistorySource(transport=lambda _url: "DATE,DGS2\n").fetch("2026-01-01")


class RateStrategyTests(unittest.TestCase):
    def test_runs_exactly_one_completed_steepener_and_reconciles_pnl(self):
        result = simulate_one_curve_trade(completed_steepener_history())
        trade = result["completed_trade"]
        self.assertEqual(trade["action"], "STEEPENER")
        self.assertEqual(trade["holding_observations"], 20)
        self.assertEqual(trade["spread_change_bps"], 120)
        self.assertEqual(trade["gross_pnl_usd"], 12_000)
        self.assertEqual(trade["cost_usd"], 100)
        self.assertEqual(trade["net_pnl_usd"], 11_900)
        self.assertTrue(evaluate_rate_simulation(result)["passed"])
        self.assertFalse(result["guardrails"]["lookahead_used_for_entry_signal"])
        self.assertFalse(result["guardrails"]["real_orders_created"])

    def test_tampered_spread_is_rejected(self):
        history = completed_steepener_history()
        history["observations"][10]["spread_bps"] = 999
        with self.assertRaisesRegex(ValueError, "spread_bps"):
            simulate_one_curve_trade(history)

    def test_insufficient_history_is_rejected(self):
        history = completed_steepener_history()
        history["observations"] = history["observations"][:40]
        with self.assertRaisesRegex(ValueError, "at least"):
            simulate_one_curve_trade(history)


if __name__ == "__main__":
    unittest.main()
