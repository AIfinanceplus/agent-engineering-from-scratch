import unittest

from r9_market import build_market_pricing_snapshot


def fred(series_id, value, as_of, history):
    return {
        "kind": "evidence",
        "evidence_id": f"FRED:{series_id}",
        "provider": "FRED",
        "series_id": series_id,
        "value": value,
        "unit": "percent",
        "as_of": as_of,
        "history": [{"period": period, "value": point} for period, point in history],
        "source": {"title": series_id, "publisher": "FRED", "uri": "https://example.invalid"},
    }


class R9MarketAlignmentTests(unittest.TestCase):
    def test_derived_spreads_use_latest_common_observation_date(self):
        snapshot = build_market_pricing_snapshot(
            fred("DFF", 5.33, "2026-08-29", [("2026-08-28", 5.33), ("2026-08-29", 5.33)]),
            # 2Y has a newer observation than 10Y. R9 must NOT mix 8/29 with 8/28.
            fred("DGS2", 4.15, "2026-08-29", [("2026-08-28", 4.10), ("2026-08-29", 4.15)]),
            fred("DGS10", 4.30, "2026-08-28", [("2026-08-27", 4.25), ("2026-08-28", 4.30)]),
            fred("DFII10", 1.90, "2026-08-28", [("2026-08-27", 1.88), ("2026-08-28", 1.90)]),
            fred("T10YIE", 2.40, "2026-08-28", [("2026-08-27", 2.37), ("2026-08-28", 2.40)]),
            "2026-08-29",
        )
        derived = snapshot["derived_observations"]
        self.assertEqual(derived["term_spread_as_of"], "2026-08-28")
        self.assertEqual(derived["term_spread_10y_minus_2y"], 0.20)
        self.assertEqual(derived["nominal_real_breakeven_as_of"], "2026-08-28")
        self.assertEqual(derived["nominal_minus_real_10y_spread"], 2.40)
        self.assertEqual(derived["breakeven_crosscheck_gap"], 0.0)
        self.assertTrue(snapshot["guardrails"]["derived_values_use_common_observation_date"])

    def test_missing_common_date_abstains_from_derived_spread(self):
        snapshot = build_market_pricing_snapshot(
            fred("DFF", 5.33, "2026-08-29", [("2026-08-29", 5.33)]),
            fred("DGS2", 4.15, "2026-08-29", [("2026-08-29", 4.15)]),
            fred("DGS10", 4.30, "2026-08-28", [("2026-08-28", 4.30)]),
            fred("DFII10", 1.90, "2026-08-28", [("2026-08-28", 1.90)]),
            fred("T10YIE", 2.40, "2026-08-28", [("2026-08-28", 2.40)]),
            "2026-08-29",
        )
        derived = snapshot["derived_observations"]
        self.assertIsNone(derived["term_spread_10y_minus_2y"])
        self.assertEqual(derived["term_spread_status"], "NO_COMMON_OBSERVATION")
        self.assertEqual(derived["curve_shape"], "UNRESOLVED")


if __name__ == "__main__":
    unittest.main()
