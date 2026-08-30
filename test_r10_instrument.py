import unittest

from r10_instrument import compute_instrument_risk_ev


def decision(gap_status="NUMERIC_GAP_AVAILABLE"):
    return {
        "artifact_type": "r10_investment_decision",
        "mispricing": {
            "status": gap_status,
            "dimension": "5Y inflation compensation",
            "gap_magnitude_bp": 5.0 if gap_status == "NUMERIC_GAP_AVAILABLE" else None,
        },
        "scenario_payoff_template": {
            "status": "STANDARDIZED_MARKET_MOVE_PAYOFF_TEMPLATE_AVAILABLE" if gap_status == "NUMERIC_GAP_AVAILABLE" else "PAYOFF_TEMPLATE_UNAVAILABLE_NO_NUMERIC_GAP",
            "exposure": "LONG_5Y_INFLATION_COMPENSATION",
            "scenarios": [
                {"name": "research_target_realized", "market_move_bp": 5.0},
                {"name": "no_repricing", "market_move_bp": 0.0},
                {"name": "equal_opposite_move", "market_move_bp": -5.0},
            ] if gap_status == "NUMERIC_GAP_AVAILABLE" else [],
        },
    }


def probabilities():
    return [
        {"name": "research_target_realized", "probability": 0.50, "probability_source": "user_assumption"},
        {"name": "no_repricing", "probability": 0.25, "probability_source": "user_assumption"},
        {"name": "equal_opposite_move", "probability": 0.25, "probability_source": "user_assumption"},
    ]


class R10InstrumentRiskTests(unittest.TestCase):
    def test_explicit_sensitivity_translates_market_bp_to_real_pnl_unit(self):
        result = compute_instrument_risk_ev(
            decision(),
            "5Y breakeven package",
            "LONG",
            2500.0,
            "user_input",
            "USD",
            probabilities(),
            transaction_cost=100.0,
            carry=50.0,
            risk_budget=15000.0,
            loss_limit=13000.0,
        )
        rows = {row["name"]: row for row in result["scenarios"]}
        self.assertEqual(rows["research_target_realized"]["gross_instrument_pnl"], 12500.0)
        self.assertEqual(rows["equal_opposite_move"]["gross_instrument_pnl"], -12500.0)
        self.assertEqual(rows["research_target_realized"]["net_instrument_pnl"], 12450.0)
        self.assertEqual(rows["no_repricing"]["net_instrument_pnl"], -50.0)
        self.assertEqual(rows["equal_opposite_move"]["net_instrument_pnl"], -12550.0)
        self.assertEqual(result["net_expected_value"], 3075.0)
        self.assertEqual(result["worst_scenario_loss"], 12550.0)
        self.assertAlmostEqual(result["risk_efficiency_ratio"], 3075.0 / 12550.0, places=6)
        self.assertEqual(result["risk_efficiency_type"], "net_ev_divided_by_worst_scenario_loss_not_sharpe")
        self.assertTrue(result["position_review_gate"]["eligible_for_review"])
        self.assertEqual(result["position"], "NONE_AUTOMATICALLY")

    def test_risk_limit_rejects_positive_ev_candidate(self):
        result = compute_instrument_risk_ev(
            decision(),
            "5Y breakeven package",
            "LONG",
            2500.0,
            "user_input",
            "USD",
            probabilities(),
            risk_budget=10000.0,
            loss_limit=13000.0,
        )
        self.assertGreater(result["net_expected_value"], 0)
        self.assertEqual(result["position_review_gate"]["status"], "REJECT_RISK_LIMIT")
        self.assertFalse(result["position_review_gate"]["eligible_for_review"])

    def test_positive_ev_without_risk_limits_is_not_positionable(self):
        result = compute_instrument_risk_ev(
            decision(),
            "5Y breakeven package",
            "LONG",
            100.0,
            "instrument_adapter",
            "USD",
            probabilities(),
        )
        self.assertGreater(result["net_expected_value"], 0)
        self.assertEqual(result["position_review_gate"]["status"], "REVIEW_MISSING_RISK_LIMITS")
        self.assertFalse(result["position_review_gate"]["eligible_for_review"])

    def test_short_direction_flips_instrument_pnl(self):
        result = compute_instrument_risk_ev(
            decision(),
            "short test",
            "SHORT",
            100.0,
            "user_input",
            "USD",
            probabilities(),
        )
        rows = {row["name"]: row for row in result["scenarios"]}
        self.assertEqual(rows["research_target_realized"]["gross_instrument_pnl"], -500.0)
        self.assertEqual(rows["equal_opposite_move"]["gross_instrument_pnl"], 500.0)

    def test_probability_names_must_match_i1_template(self):
        bad = probabilities()
        bad[2] = {"name": "other", "probability": 0.25, "probability_source": "user_assumption"}
        with self.assertRaisesRegex(ValueError, "match the I1 scenario template"):
            compute_instrument_risk_ev(
                decision(), "x", "LONG", 100, "user_input", "USD", bad
            )

    def test_support_score_cannot_be_sensitivity_source(self):
        with self.assertRaisesRegex(ValueError, "support score"):
            compute_instrument_risk_ev(
                decision(), "x", "LONG", 100, "R7 support_score", "USD", probabilities()
            )

    def test_no_numeric_gap_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "NUMERIC_GAP_AVAILABLE"):
            compute_instrument_risk_ev(
                decision("DIRECTIONAL_GAP_ONLY"),
                "x", "LONG", 100, "user_input", "USD", probabilities()
            )


if __name__ == "__main__":
    unittest.main()
