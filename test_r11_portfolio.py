import unittest

from r10_instrument import compute_instrument_risk_ev
from r11_portfolio import compute_position_size
from test_r10_instrument import decision, probabilities


def eligible_i2():
    return compute_instrument_risk_ev(
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


class R11PositionSizingTests(unittest.TestCase):
    def test_trade_loss_limit_can_bind_max_admissible_scale(self):
        i2 = eligible_i2()
        result = compute_position_size(
            i2,
            portfolio_value=1_000_000.0,
            portfolio_value_unit="USD",
            portfolio_risk_budget=50_000.0,
            portfolio_current_risk_used=25_000.0,
            max_position_nav_fraction=0.10,
            capital_required_per_reference_position=50_000.0,
            capital_source="user_input",
            max_reference_scale=10.0,
        )
        expected_scale = 13_000.0 / 12_550.0
        self.assertEqual(result["status"], "SIZE_AVAILABLE_FOR_REVIEW_NOT_EXECUTION")
        self.assertEqual(result["sizing"]["binding_constraints"], ["trade_loss_limit"])
        self.assertAlmostEqual(result["sizing"]["max_admissible_scale"], expected_scale, places=8)
        self.assertAlmostEqual(result["economics"]["scaled_worst_scenario_loss"], 13_000.0, places=5)
        self.assertAlmostEqual(result["economics"]["scaled_net_ev"], 3_075.0 * expected_scale, places=5)
        self.assertLessEqual(result["portfolio"]["scaled_capital_fraction_of_nav"], 0.10)
        self.assertFalse(result["guardrails"]["kelly_or_optimal_size_claimed"])
        self.assertFalse(result["guardrails"]["automatic_trade_execution"])

    def test_portfolio_remaining_risk_can_be_binding_constraint(self):
        i2 = eligible_i2()
        result = compute_position_size(
            i2,
            1_000_000.0,
            "USD",
            50_000.0,
            49_000.0,
            0.10,
            50_000.0,
            "portfolio_system",
        )
        self.assertEqual(result["sizing"]["binding_constraints"], ["portfolio_remaining_risk"])
        self.assertAlmostEqual(result["economics"]["scaled_worst_scenario_loss"], 1_000.0, places=5)
        self.assertAlmostEqual(result["portfolio"]["post_trade_risk_used"], 50_000.0, places=5)

    def test_capital_allocation_can_be_binding_constraint(self):
        result = compute_position_size(
            eligible_i2(),
            1_000_000.0,
            "USD",
            50_000.0,
            10_000.0,
            0.01,
            50_000.0,
            "user_input",
        )
        self.assertEqual(result["sizing"]["binding_constraints"], ["capital_allocation"])
        self.assertAlmostEqual(result["sizing"]["max_admissible_scale"], 0.2, places=8)
        self.assertAlmostEqual(result["portfolio"]["scaled_capital_required"], 10_000.0, places=5)
        self.assertAlmostEqual(result["portfolio"]["scaled_capital_fraction_of_nav"], 0.01, places=8)

    def test_implementation_cap_can_bind(self):
        result = compute_position_size(
            eligible_i2(),
            1_000_000.0,
            "USD",
            50_000.0,
            10_000.0,
            0.10,
            50_000.0,
            "user_input",
            max_reference_scale=0.10,
        )
        self.assertEqual(result["sizing"]["binding_constraints"], ["implementation_scale_cap"])
        self.assertAlmostEqual(result["sizing"]["max_admissible_scale"], 0.10, places=8)

    def test_no_remaining_portfolio_risk_returns_zero_size(self):
        result = compute_position_size(
            eligible_i2(),
            1_000_000.0,
            "USD",
            50_000.0,
            50_000.0,
            0.10,
            50_000.0,
            "user_input",
        )
        self.assertEqual(result["status"], "NO_REMAINING_PORTFOLIO_RISK_BUDGET")
        self.assertEqual(result["sizing"]["max_admissible_scale"], 0.0)
        self.assertFalse(result["position_review_gate"]["eligible_for_size_review"])

    def test_units_must_match(self):
        with self.assertRaisesRegex(ValueError, "must match the I2 P&L unit"):
            compute_position_size(
                eligible_i2(),
                1_000_000.0,
                "EUR",
                50_000.0,
                10_000.0,
                0.10,
                50_000.0,
                "user_input",
            )

    def test_ineligible_i2_fails_closed(self):
        i2 = compute_instrument_risk_ev(
            decision(),
            "5Y breakeven package",
            "LONG",
            2500.0,
            "user_input",
            "USD",
            probabilities(),
            risk_budget=10_000.0,
            loss_limit=13_000.0,
        )
        self.assertFalse(i2["position_review_gate"]["eligible_for_review"])
        with self.assertRaisesRegex(ValueError, "eligible for position review"):
            compute_position_size(
                i2,
                1_000_000.0,
                "USD",
                50_000.0,
                10_000.0,
                0.10,
                50_000.0,
                "user_input",
            )


if __name__ == "__main__":
    unittest.main()
