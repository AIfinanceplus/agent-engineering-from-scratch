import unittest

from r12_strategy import scan_structural_opportunities, strategy_registry_snapshot


def demo_snapshot():
    return {
        "as_of": "2026-08-29T19:00:00-07:00",
        "source": "unit_test_snapshot",
        "binary_markets": [
            {
                "event_id": "same-binary-event",
                "yes_price": 0.48,
                "no_price": 0.47,
                "estimated_total_cost": 0.01,
                "settlement_compatibility_verified": True,
                "shortability_verified": False,
            }
        ],
        "threshold_groups": [
            {
                "group_id": "cpi-thresholds",
                "relation": "greater_than",
                "settlement_compatibility_verified": True,
                "pair_trade_capability_verified": True,
                "estimated_pair_cost": 0.005,
                "contracts": [
                    {"contract_id": "cpi-gt-3.0", "threshold": 3.0, "yes_price": 0.70},
                    {"contract_id": "cpi-gt-3.5", "threshold": 3.5, "yes_price": 0.55},
                    {"contract_id": "cpi-gt-4.0", "threshold": 4.0, "yes_price": 0.58},
                ],
            }
        ],
        "exclusive_groups": [
            {
                "group_id": "three-outcome",
                "mutually_exclusive_verified": True,
                "exhaustive_verified": True,
                "settlement_compatibility_verified": True,
                "shortability_verified": False,
                "estimated_total_cost": 0.01,
                "contracts": [
                    {"contract_id": "A", "yes_price": 0.45},
                    {"contract_id": "B", "yes_price": 0.35},
                    {"contract_id": "C", "yes_price": 0.15},
                ],
            }
        ],
    }


class R12StrategyTests(unittest.TestCase):
    def test_demo_snapshot_detects_three_structural_opportunities(self):
        scan = scan_structural_opportunities(demo_snapshot())
        self.assertEqual(scan["artifact_type"], "r12_structural_scan")
        self.assertEqual(scan["opportunity_count"], 3)
        self.assertEqual(scan["paper_signal_count"], 3)
        self.assertEqual(scan["execution_policy"], "PAPER_SIGNAL_ONLY_NO_AUTO_EXECUTION")
        subtypes = {row["subtype"] for row in scan["opportunities"]}
        self.assertEqual(
            subtypes,
            {"binary_complement", "threshold_monotonicity", "mutually_exclusive_exhaustive_sum"},
        )
        for row in scan["opportunities"]:
            self.assertEqual(row["artifact_type"], "r12_strategy_opportunity")
            self.assertFalse(row["guardrails"]["automatic_execution"])
            self.assertEqual(row["execution_status"], "PAPER_SIGNAL_ONLY_NO_AUTO_EXECUTION")

    def test_binary_underrround_subtracts_cost_before_signal(self):
        scan = scan_structural_opportunities(demo_snapshot())
        row = next(x for x in scan["opportunities"] if x["subtype"] == "binary_complement")
        self.assertAlmostEqual(row["gross_edge"], 0.05)
        self.assertAlmostEqual(row["estimated_cost"], 0.01)
        self.assertAlmostEqual(row["net_edge"], 0.04)
        self.assertEqual(row["candidate_action"], "BUY_YES_AND_NO_BASKET")
        self.assertTrue(row["eligible_for_paper_signal"])

    def test_threshold_monotonicity_detects_nested_probability_violation(self):
        scan = scan_structural_opportunities(demo_snapshot())
        row = next(x for x in scan["opportunities"] if x["subtype"] == "threshold_monotonicity")
        self.assertAlmostEqual(row["gross_edge"], 0.03)
        self.assertAlmostEqual(row["net_edge"], 0.025)
        self.assertEqual(row["market_view"]["lower_contract_id"], "cpi-gt-3.5")
        self.assertEqual(row["market_view"]["higher_contract_id"], "cpi-gt-4.0")
        self.assertTrue(row["implementation_verified"])

    def test_monotone_thresholds_emit_no_violation(self):
        snapshot = {
            "as_of": "x",
            "source": "test",
            "threshold_groups": [
                {
                    "group_id": "ok",
                    "relation": "greater_than",
                    "settlement_compatibility_verified": True,
                    "pair_trade_capability_verified": True,
                    "contracts": [
                        {"contract_id": "a", "threshold": 3, "yes_price": 0.7},
                        {"contract_id": "b", "threshold": 4, "yes_price": 0.4},
                    ],
                }
            ],
        }
        scan = scan_structural_opportunities(snapshot)
        self.assertEqual(scan["opportunity_count"], 0)

    def test_exhaustive_basket_underrround_has_locked_margin_contract(self):
        scan = scan_structural_opportunities(demo_snapshot())
        row = next(x for x in scan["opportunities"] if x["subtype"] == "mutually_exclusive_exhaustive_sum")
        self.assertAlmostEqual(row["market_view"]["sum"], 0.95)
        self.assertAlmostEqual(row["gross_edge"], 0.05)
        self.assertAlmostEqual(row["net_edge"], 0.04)
        self.assertEqual(row["candidate_action"], "BUY_ALL_EXHAUSTIVE_OUTCOMES")
        self.assertTrue(row["eligible_for_paper_signal"])

    def test_overround_without_shortability_is_not_actionable(self):
        snapshot = {
            "as_of": "x",
            "source": "test",
            "binary_markets": [
                {
                    "event_id": "overround",
                    "yes_price": 0.56,
                    "no_price": 0.49,
                    "settlement_compatibility_verified": True,
                    "shortability_verified": False,
                }
            ],
        }
        row = scan_structural_opportunities(snapshot)["opportunities"][0]
        self.assertEqual(row["status"], "OBSERVED_EDGE_IMPLEMENTATION_NOT_VERIFIED")
        self.assertFalse(row["eligible_for_paper_signal"])
        self.assertFalse(row["guardrails"]["shortability_assumed"])

    def test_unverified_settlement_blocks_signal(self):
        snapshot = {
            "as_of": "x",
            "source": "test",
            "binary_markets": [
                {
                    "event_id": "unverified",
                    "yes_price": 0.45,
                    "no_price": 0.45,
                    "settlement_compatibility_verified": False,
                }
            ],
        }
        row = scan_structural_opportunities(snapshot)["opportunities"][0]
        self.assertEqual(row["status"], "BLOCKED_SETTLEMENT_NOT_VERIFIED")
        self.assertFalse(row["eligible_for_paper_signal"])

    def test_cost_can_remove_apparent_edge(self):
        snapshot = {
            "as_of": "x",
            "source": "test",
            "binary_markets": [
                {
                    "event_id": "costly",
                    "yes_price": 0.48,
                    "no_price": 0.49,
                    "estimated_total_cost": 0.04,
                    "settlement_compatibility_verified": True,
                }
            ],
        }
        row = scan_structural_opportunities(snapshot)["opportunities"][0]
        self.assertAlmostEqual(row["gross_edge"], 0.03)
        self.assertAlmostEqual(row["net_edge"], -0.01)
        self.assertEqual(row["status"], "NO_EDGE_AFTER_COST")
        self.assertFalse(row["eligible_for_paper_signal"])

    def test_registry_tracks_all_five_strategy_families(self):
        registry = strategy_registry_snapshot()
        rows = registry["strategies"]
        self.assertEqual(len(rows), 5)
        ids = {row["strategy_id"] for row in rows}
        self.assertEqual(
            ids,
            {
                "structural_logic_rv",
                "cross_market_event_rv",
                "fomc_probability_rv",
                "cpi_macro_rv",
                "options_event_rv",
            },
        )
        structural = next(row for row in rows if row["strategy_id"] == "structural_logic_rv")
        self.assertEqual(structural["status"], "ACTIVE_DETERMINISTIC")
        self.assertEqual(registry["execution_policy"], "PAPER_SIGNAL_ONLY_NO_AUTO_EXECUTION")


if __name__ == "__main__":
    unittest.main()
