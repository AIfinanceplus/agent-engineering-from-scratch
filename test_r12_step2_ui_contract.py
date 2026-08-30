import unittest
from pathlib import Path


ROOT = Path(__file__).parent


class R12Step2UIContractTests(unittest.TestCase):
    def test_live_contract_inspector_uses_exact_identifiers_and_separate_identity_gate(self):
        source = (ROOT / "web" / "r12_step2.js").read_text(encoding="utf-8")
        self.assertIn("Live Contract Inspector", source)
        self.assertIn("exact market ticker", source)
        self.assertIn("exact Gamma market ID", source)
        self.assertIn("/api/r12/market-contract", source)
        self.assertIn("/api/r12/identity", source)
        self.assertIn("/api/r12/cross-market-rv", source)
        self.assertIn("/api/r12/execution-quote", source)
        self.assertIn("same_event_meaning", source)
        self.assertIn("same_yes_outcome", source)
        self.assertIn("same_measurement_definition", source)
        self.assertIn("compatible_resolution_source", source)
        self.assertIn("compatible_resolution_horizon", source)
        self.assertIn("edge_cases_reviewed", source)

    def test_cross_market_rv_is_disabled_until_identity_is_verified(self):
        source = (ROOT / "web" / "r12_step2.js").read_text(encoding="utf-8")
        self.assertIn("identity?.settlement_compatible_for_rv", source)
        self.assertIn("Settlement identity must be verified first", source)
        self.assertIn("PAPER_SIGNAL_ONLY_NO_AUTO_EXECUTION", source)
        self.assertIn("PRELIMINARY TOP-OF-BOOK", source)
        self.assertIn("Depth-aware Paper Execution Quote", source)
        self.assertIn("完整 depth、explicit fee 和 target-fill gate", source)
        self.assertIn("r12Step2FiniteNonNegative", source)
        self.assertNotIn("placeOrder", source)
        self.assertNotIn("create_order", source)

    def test_server_loads_step2_extension_and_routes_all_boundaries(self):
        source = (ROOT / "serve_r12.py").read_text(encoding="utf-8")
        self.assertIn('"r12_step2.js"', source)
        self.assertIn('"/api/r12/market-contract"', source)
        self.assertIn('"/api/r12/identity"', source)
        self.assertIn('"/api/r12/cross-market-rv"', source)
        self.assertIn('"/api/r12/execution-quote"', source)
        self.assertIn("title similarity NEVER auto-approves", source)
        self.assertIn("No order credentials, wallet, authenticated portfolio API, or order placement", source)


if __name__ == "__main__":
    unittest.main()
