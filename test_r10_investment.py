import unittest

from r10_investment import build_r10_investment_decision, compute_scenario_expected_value


RESEARCH_IDS = ["BLS:CPI", "FRED:T5YIE"]
MARKET_IDS = ["FRED:DFF", "FRED:DGS2", "FRED:DGS10", "FRED:DFII10", "FRED:T10YIE"]


def artifacts(direction="falling"):
    s1 = {
        "kind": "synthesis",
        "evidence_ids": RESEARCH_IDS,
        "confidence": 0.82,
        "confidence_type": "heuristic_support_score_not_probability",
    }
    d1 = {
        "kind": "synthesis",
        "domain": "investment",
        "evidence_ids": RESEARCH_IDS,
        "confidence": 0.82,
        "pressure_state": "disinflation_pressure",
    }
    f1 = {
        "kind": "synthesis",
        "artifact_type": "forecast_pack",
        "evidence_ids": RESEARCH_IDS,
        "forecasts": [
            {
                "forecast_id": "FC-02",
                "status": "OPEN",
                "target_evidence_id": "FRED:T5YIE",
                "target_metric": "level",
                "baseline_metric_value": 2.4,
                "baseline_as_of": "2026-08-28",
                "expected_direction": direction,
                "due_date": "2026-09-05",
                "support_score": 0.8,
                "support_score_type": "heuristic_support_score_not_probability",
            }
        ],
    }
    m6 = {
        "kind": "synthesis",
        "artifact_type": "market_pricing_snapshot",
        "evidence_ids": MARKET_IDS,
        "market_levels": {
            "effective_fed_funds_rate": {"evidence_id":"FRED:DFF","value":5.33,"as_of":"2026-08-28"},
            "treasury_2y": {"evidence_id":"FRED:DGS2","value":4.1,"as_of":"2026-08-28"},
            "treasury_10y": {"evidence_id":"FRED:DGS10","value":4.3,"as_of":"2026-08-28"},
            "real_yield_10y": {"evidence_id":"FRED:DFII10","value":1.9,"as_of":"2026-08-28"},
            "breakeven_10y": {"evidence_id":"FRED:T10YIE","value":2.4,"as_of":"2026-08-28"},
        },
        "derived_observations": {
            "term_spread_10y_minus_2y": 0.2,
            "term_spread_as_of": "2026-08-28",
            "curve_shape": "POSITIVE",
        },
    }
    return s1, d1, f1, m6


class R10InvestmentDecisionTests(unittest.TestCase):
    def test_directional_disagreement_is_not_numeric_mispricing(self):
        decision = build_r10_investment_decision(
            "Assess inflation pressure.",
            *artifacts("falling"),
            "2026-08-30",
        )
        self.assertEqual(decision["artifact_type"], "r10_investment_decision")
        self.assertEqual(decision["mispricing"]["status"], "DIRECTIONAL_GAP_ONLY")
        self.assertIsNone(decision["mispricing"]["gap_magnitude_pp"])
        self.assertEqual(decision["expected_value"]["status"], "EV_NOT_COMPUTABLE_MISSING_SCENARIO_BOOK")
        self.assertEqual(decision["position_gate"]["position"], "NONE")
        self.assertFalse(decision["guardrails"]["support_score_used_as_probability"])
        self.assertFalse(decision["market_implied_view"]["semantics"]["treasury_2y_is_fed_futures_path"])

    def test_scenario_ev_uses_only_explicit_probabilities_and_payoffs(self):
        decision = build_r10_investment_decision(
            "Assess inflation pressure.",
            *artifacts("falling"),
            "2026-08-30",
        )
        ev = compute_scenario_expected_value(
            decision,
            [
                {"name":"down","probability":0.25,"payoff":-2.0,"probability_source":"user_assumption"},
                {"name":"base","probability":0.50,"payoff":0.5,"probability_source":"user_assumption"},
                {"name":"up","probability":0.25,"payoff":2.0,"probability_source":"user_assumption"},
            ],
            transaction_cost=0.05,
            payoff_unit="return_pct",
        )
        self.assertEqual(ev["gross_expected_value"], 0.25)
        self.assertEqual(ev["net_expected_value"], 0.2)
        self.assertEqual(ev["status"], "POSITIVE_EV_UNDER_INPUT_ASSUMPTIONS")
        self.assertEqual(ev["position"], "NONE_UNTIL_RISK_BUDGET_AND_IMPLEMENTATION")

    def test_support_score_cannot_be_probability_source(self):
        decision = build_r10_investment_decision(
            "Assess inflation pressure.",
            *artifacts("falling"),
            "2026-08-30",
        )
        with self.assertRaisesRegex(ValueError, "support score"):
            compute_scenario_expected_value(
                decision,
                [
                    {"name":"down","probability":0.5,"payoff":-1,"probability_source":"R7 support_score"},
                    {"name":"up","probability":0.5,"payoff":1,"probability_source":"user_assumption"},
                ],
            )

    def test_probabilities_must_sum_to_one(self):
        decision = build_r10_investment_decision(
            "Assess inflation pressure.",
            *artifacts("falling"),
            "2026-08-30",
        )
        with self.assertRaisesRegex(ValueError, "sum to 1.0"):
            compute_scenario_expected_value(
                decision,
                [
                    {"name":"down","probability":0.4,"payoff":-1,"probability_source":"user_assumption"},
                    {"name":"up","probability":0.4,"payoff":1,"probability_source":"user_assumption"},
                ],
            )


if __name__ == "__main__":
    unittest.main()
