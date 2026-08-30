import unittest

from r10_investment import (
    build_numerical_research_target,
    build_r10_investment_decision,
    compute_scenario_expected_value,
)


RESEARCH_IDS = ["BLS:CPI", "FRED:T5YIE"]
MARKET_IDS = ["FRED:DFF", "FRED:DGS2", "FRED:DGS10", "FRED:DFII10", "FRED:T10YIE"]


def artifacts(direction="falling", *, include_signal=True):
    if direction == "falling":
        previous, latest, change = 2.45, 2.40, -0.05
    elif direction == "rising":
        previous, latest, change = 2.35, 2.40, 0.05
    else:
        previous, latest, change = 2.40, 2.40, 0.0

    s1 = {
        "kind": "synthesis",
        "evidence_ids": RESEARCH_IDS,
        "confidence": 0.82,
        "confidence_type": "heuristic_support_score_not_probability",
        "signals": (
            [
                {
                    "evidence_id": "FRED:T5YIE",
                    "kind": "change",
                    "previous_value": previous,
                    "latest_value": latest,
                    "change": change,
                    "direction": direction,
                }
            ]
            if include_signal
            else []
        ),
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


def target_and_decision(direction="falling", *, include_signal=True):
    s1, d1, f1, m6 = artifacts(direction, include_signal=include_signal)
    target = build_numerical_research_target(s1, f1, "2026-08-30")
    decision = build_r10_investment_decision(
        "Assess inflation pressure.",
        s1,
        d1,
        f1,
        target,
        m6,
        "2026-08-30",
    )
    return target, decision


class R10InvestmentDecisionTests(unittest.TestCase):
    def test_t1_builds_reproducible_one_step_numerical_target(self):
        target, _ = target_and_decision("falling")
        self.assertEqual(target["artifact_type"], "r10_numerical_research_target")
        self.assertEqual(target["status"], "NUMERICAL_TARGET_AVAILABLE")
        self.assertEqual(target["method"], "one_step_change_persistence_baseline")
        self.assertAlmostEqual(target["baseline_value"], 2.4)
        self.assertAlmostEqual(target["observed_change_pp"], -0.05)
        self.assertAlmostEqual(target["target_value"], 2.35)
        self.assertAlmostEqual(target["target_gap_from_baseline_bp"], -5.0)
        self.assertEqual(target["calibration_status"], "NOT_CALIBRATED_MECHANICAL_BASELINE")
        self.assertIsNone(target["probability"])

    def test_numerical_target_enables_numeric_gap_but_not_security_pnl(self):
        target, decision = target_and_decision("falling")
        self.assertEqual(decision["artifact_type"], "r10_investment_decision")
        self.assertEqual(decision["numerical_research_target"]["target_value"], target["target_value"])
        self.assertEqual(decision["mispricing"]["status"], "NUMERIC_GAP_AVAILABLE")
        self.assertAlmostEqual(decision["mispricing"]["market_baseline"], 2.4)
        self.assertAlmostEqual(decision["mispricing"]["research_target"], 2.35)
        self.assertAlmostEqual(decision["mispricing"]["gap_magnitude_pp"], -0.05)
        self.assertAlmostEqual(decision["mispricing"]["gap_magnitude_bp"], -5.0)
        template = decision["scenario_payoff_template"]
        self.assertEqual(template["status"], "STANDARDIZED_MARKET_MOVE_PAYOFF_TEMPLATE_AVAILABLE")
        self.assertEqual(template["exposure"], "SHORT_5Y_INFLATION_COMPENSATION")
        self.assertEqual(template["payoff_unit"], "bp_on_unit_directional_exposure")
        self.assertEqual([row["payoff"] for row in template["scenarios"]], [5.0, 0.0, -5.0])
        self.assertTrue(all(row["probability"] is None for row in template["scenarios"]))
        self.assertEqual(template["instrument_pnl_status"], "NOT_MODELED_REQUIRES_SENSITIVITY")
        self.assertEqual(decision["expected_value"]["status"], "EV_NOT_COMPUTABLE_MISSING_SCENARIO_PROBABILITIES")
        self.assertEqual(decision["position_gate"]["position"], "NONE")
        self.assertFalse(decision["guardrails"]["market_move_bp_called_security_pnl"])

    def test_missing_numeric_signal_abstains_and_falls_back_to_directional_gap(self):
        target, decision = target_and_decision("falling", include_signal=False)
        self.assertEqual(target["status"], "ABSTAINED_NUMERICAL_TARGET_UNAVAILABLE")
        self.assertEqual(target["abstain_reason"], "missing_comparable_s1_signal")
        self.assertEqual(decision["mispricing"]["status"], "DIRECTIONAL_GAP_ONLY")
        self.assertIsNone(decision["mispricing"]["gap_magnitude_pp"])
        self.assertEqual(
            decision["scenario_payoff_template"]["status"],
            "PAYOFF_TEMPLATE_UNAVAILABLE_NO_NUMERIC_GAP",
        )

    def test_zero_change_produces_no_numeric_edge(self):
        target, decision = target_and_decision("flat")
        self.assertEqual(target["status"], "NUMERICAL_TARGET_AVAILABLE")
        self.assertEqual(decision["mispricing"]["status"], "NO_NUMERIC_GAP")
        self.assertEqual(decision["mispricing"]["gap_magnitude_bp"], 0.0)
        self.assertEqual(decision["position_gate"]["status"], "NO_POSITION_NO_EDGE")

    def test_scenario_ev_uses_only_explicit_probabilities_and_payoffs(self):
        _, decision = target_and_decision("falling")
        ev = compute_scenario_expected_value(
            decision,
            [
                {"name":"target","probability":0.50,"payoff":5.0,"probability_source":"user_assumption"},
                {"name":"unchanged","probability":0.25,"payoff":0.0,"probability_source":"user_assumption"},
                {"name":"opposite","probability":0.25,"payoff":-5.0,"probability_source":"user_assumption"},
            ],
            transaction_cost=0.5,
            payoff_unit="bp_on_unit_directional_exposure",
        )
        self.assertEqual(ev["gross_expected_value"], 1.25)
        self.assertEqual(ev["net_expected_value"], 0.75)
        self.assertEqual(ev["status"], "POSITIVE_EV_UNDER_INPUT_ASSUMPTIONS")
        self.assertEqual(ev["position"], "NONE_UNTIL_RISK_BUDGET_AND_IMPLEMENTATION")

    def test_support_score_cannot_be_probability_source(self):
        _, decision = target_and_decision("falling")
        with self.assertRaisesRegex(ValueError, "support score"):
            compute_scenario_expected_value(
                decision,
                [
                    {"name":"down","probability":0.5,"payoff":-1,"probability_source":"R7 support_score"},
                    {"name":"up","probability":0.5,"payoff":1,"probability_source":"user_assumption"},
                ],
            )

    def test_probabilities_must_sum_to_one(self):
        _, decision = target_and_decision("falling")
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
