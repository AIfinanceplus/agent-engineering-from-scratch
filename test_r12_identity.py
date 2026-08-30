import unittest

from r12_event_sources import normalize_kalshi_contract, normalize_polymarket_contract
from r12_identity import compare_cross_market_locked_rv, validate_event_identity
from test_r12_event_sources import kalshi_event, kalshi_market, kalshi_series, poly_books, polymarket_market


def contracts(*, polymarket_books=True):
    kalshi = normalize_kalshi_contract(
        kalshi_market(),
        event=kalshi_event(),
        series=kalshi_series(),
    )
    polymarket = normalize_polymarket_contract(
        polymarket_market(),
        books=poly_books() if polymarket_books else {},
    )
    return kalshi, polymarket


def full_attestation():
    return {
        "same_event_meaning": True,
        "same_yes_outcome": True,
        "same_measurement_definition": True,
        "compatible_resolution_source": True,
        "compatible_resolution_horizon": True,
        "edge_cases_reviewed": True,
        "attestation_source": "human_rules_review",
    }


class R12IdentityTests(unittest.TestCase):
    def test_title_similarity_never_auto_approves_identity(self):
        kalshi, poly = contracts()
        identity = validate_event_identity(kalshi, poly)
        self.assertEqual(identity["status"], "IDENTITY_UNVERIFIED_MANUAL_REVIEW_REQUIRED")
        self.assertFalse(identity["settlement_compatible_for_rv"])
        self.assertFalse(identity["guardrails"]["title_similarity_used_as_identity"])
        self.assertFalse(identity["guardrails"]["llm_auto_approval_used"])

    def test_incomplete_attestation_fails_closed(self):
        kalshi, poly = contracts()
        attestation = full_attestation()
        attestation["edge_cases_reviewed"] = False
        identity = validate_event_identity(kalshi, poly, attestation=attestation)
        self.assertEqual(identity["status"], "IDENTITY_REJECTED_OR_ATTESTATION_INCOMPLETE")
        self.assertFalse(identity["settlement_compatible_for_rv"])

    def test_complete_attestation_allows_rv_comparison(self):
        kalshi, poly = contracts()
        identity = validate_event_identity(kalshi, poly, attestation=full_attestation())
        self.assertEqual(identity["status"], "SETTLEMENT_COMPATIBLE_FOR_RV")
        self.assertTrue(identity["settlement_compatible_for_rv"])
        self.assertTrue(identity["manual_attestation"]["complete"])

    def test_verified_identity_finds_locked_cross_market_basket_after_cost(self):
        kalshi, poly = contracts()
        identity = validate_event_identity(kalshi, poly, attestation=full_attestation())
        scan = compare_cross_market_locked_rv(
            identity,
            kalshi,
            poly,
            estimated_total_cost_per_basket=0.01,
        )
        # Kalshi YES ask .48 + Polymarket NO ask .49 = .97; gross edge .03; net .02.
        self.assertEqual(scan["opportunity_count"], 1)
        self.assertEqual(scan["paper_signal_count"], 1)
        row = scan["opportunities"][0]
        self.assertAlmostEqual(row["gross_edge"], 0.03)
        self.assertAlmostEqual(row["estimated_cost"], 0.01)
        self.assertAlmostEqual(row["net_edge"], 0.02)
        self.assertEqual(row["candidate_action"], "BUY_BOTH_COMPLEMENT_LEGS_AT_CURRENT_ASKS")
        self.assertEqual(row["execution_status"], "PAPER_SIGNAL_ONLY_NO_AUTO_EXECUTION")
        self.assertEqual(row["liquidity_status"], "TOP_OF_BOOK_ONLY_DEPTH_NOT_YET_MODELED")

    def test_unverified_identity_cannot_enter_cross_market_rv(self):
        kalshi, poly = contracts()
        identity = validate_event_identity(kalshi, poly)
        with self.assertRaisesRegex(ValueError, "SETTLEMENT_COMPATIBLE_FOR_RV"):
            compare_cross_market_locked_rv(identity, kalshi, poly)

    def test_indicative_polymarket_price_is_not_treated_as_executable(self):
        kalshi, poly = contracts(polymarket_books=False)
        identity = validate_event_identity(kalshi, poly, attestation=full_attestation())
        scan = compare_cross_market_locked_rv(identity, kalshi, poly, estimated_total_cost_per_basket=0.0)
        self.assertEqual(scan["quote_mode"], "PARTIAL_OR_INDICATIVE")
        self.assertEqual(scan["opportunity_count"], 0)
        self.assertTrue(all(row["status"] == "EXECUTABLE_QUOTES_REQUIRED" for row in scan["baskets_checked"]))

    def test_cost_can_remove_cross_market_locked_margin(self):
        kalshi, poly = contracts()
        identity = validate_event_identity(kalshi, poly, attestation=full_attestation())
        scan = compare_cross_market_locked_rv(identity, kalshi, poly, estimated_total_cost_per_basket=0.04)
        self.assertEqual(scan["opportunity_count"], 0)
        best = scan["baskets_checked"][0]
        self.assertAlmostEqual(best["gross_edge"], 0.03)
        self.assertAlmostEqual(best["net_edge"], -0.01)


if __name__ == "__main__":
    unittest.main()
