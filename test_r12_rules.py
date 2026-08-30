import copy
import unittest

from r12_rules import analyze_settlement_rules, settlement_contract_fingerprint, validate_rules_analysis_binding
from r12_tooling import R12_RULES_ANALYSIS_TOOL, register_r12_tools
from test_r12_identity import contracts


class R12SettlementRulesTests(unittest.TestCase):
    def setUp(self):
        self.kalshi, self.poly = contracts()

    def test_analysis_extracts_review_material_but_never_approves_identity(self):
        analysis = analyze_settlement_rules(self.kalshi, self.poly)
        self.assertEqual(analysis["artifact_type"], "r12_settlement_rules_analysis")
        self.assertEqual(analysis["status"], "RULES_ANALYSIS_READY_FOR_HUMAN_REVIEW")
        self.assertTrue(analysis["eligible_for_identity_review"])
        self.assertFalse(analysis["can_auto_approve_identity"])
        self.assertTrue(all(not row["can_approve_identity"] for row in analysis["comparison_checks"]))
        self.assertFalse(analysis["guardrails"]["parser_checks_attestation_boxes"])

    def test_analysis_binds_to_identity_relevant_contract_fingerprints(self):
        analysis = analyze_settlement_rules(self.kalshi, self.poly)
        binding = validate_rules_analysis_binding(analysis, self.kalshi, self.poly)
        self.assertTrue(binding["all_pass"])
        self.assertEqual(
            analysis["contracts"]["kalshi"]["fingerprint"],
            settlement_contract_fingerprint(self.kalshi),
        )

        changed = copy.deepcopy(self.kalshi)
        changed["resolution"]["rules_primary"] += " Amended after analysis."
        stale = validate_rules_analysis_binding(analysis, changed, self.poly)
        self.assertFalse(stale["fingerprints_current"])
        self.assertFalse(stale["all_pass"])

    def test_tampered_analysis_does_not_match_current_parser_output(self):
        analysis = analyze_settlement_rules(self.kalshi, self.poly)
        analysis["comparison_checks"][0]["status"] = "FORGED_READY"
        binding = validate_rules_analysis_binding(analysis, self.kalshi, self.poly)
        self.assertTrue(binding["fingerprints_current"])
        self.assertFalse(binding["matches_current_parser_output"])
        self.assertFalse(binding["all_pass"])

    def test_missing_rule_text_blocks_identity_review(self):
        incomplete = copy.deepcopy(self.poly)
        incomplete["description"] = None
        incomplete["resolution"]["description"] = None
        analysis = analyze_settlement_rules(self.kalshi, incomplete)
        self.assertEqual(analysis["status"], "RULES_ANALYSIS_BLOCKED_INCOMPLETE")
        self.assertFalse(analysis["eligible_for_identity_review"])
        self.assertIn("POLYMARKET_RULE_TEXT_REQUIRED", analysis["blocking_findings"])

    def test_source_and_edge_case_differences_are_review_flags_not_identity_verdicts(self):
        changed = copy.deepcopy(self.poly)
        changed["resolution"]["resolution_source"] = "https://another-authority.test/result"
        changed["description"] += " If the event is cancelled, the market may be voided."
        changed["resolution"]["description"] = changed["description"]
        analysis = analyze_settlement_rules(self.kalshi, changed)
        checks = {row["check"]: row for row in analysis["comparison_checks"]}
        self.assertEqual(checks["resolution_authority"]["status"], "DIFFERENCE_REVIEW_REQUIRED")
        self.assertEqual(checks["edge_case_clauses"]["status"], "DIFFERENCE_REVIEW_REQUIRED")
        self.assertTrue(analysis["eligible_for_identity_review"])
        self.assertFalse(analysis["can_auto_approve_identity"])

    def test_exact_canonical_measurement_conflict_blocks_identity_review(self):
        kalshi = copy.deepcopy(self.kalshi)
        poly = copy.deepcopy(self.poly)
        canonical = {
            "canonical_metric": "official_count",
            "canonical_operator": ">=",
            "canonical_threshold": "3",
            "canonical_unit": "events",
        }
        kalshi["measurement_contract"].update(canonical)
        poly["measurement_contract"].update({**canonical, "canonical_threshold": "4"})

        analysis = analyze_settlement_rules(kalshi, poly)
        checks = {row["check"]: row for row in analysis["comparison_checks"]}
        self.assertEqual(analysis["status"], "RULES_ANALYSIS_BLOCKED_DETERMINISTIC_CONFLICT")
        self.assertFalse(analysis["eligible_for_identity_review"])
        self.assertIn("CANONICAL_MEASUREMENT_CONFLICT", analysis["blocking_findings"])
        self.assertEqual(checks["canonical_measurement_contract"]["status"], "DETERMINISTIC_CONFLICT")
        self.assertEqual(analysis["recommended_next_step"], "REJECT_PAIR_OR_CORRECT_CANONICAL_CONTRACT")

    def test_analysis_id_changes_when_rules_change(self):
        first = analyze_settlement_rules(self.kalshi, self.poly)
        changed = copy.deepcopy(self.poly)
        changed["description"] += " Final release only."
        changed["resolution"]["description"] = changed["description"]
        second = analyze_settlement_rules(self.kalshi, changed)
        self.assertNotEqual(first["analysis_id"], second["analysis_id"])

    def test_parser_is_registered_as_low_risk_review_tool(self):
        names = register_r12_tools()
        self.assertIn("analyze_r12_settlement_rules", names)
        self.assertEqual(R12_RULES_ANALYSIS_TOOL.risk, "low")
        self.assertIn("can never approve event identity", R12_RULES_ANALYSIS_TOOL.description)


if __name__ == "__main__":
    unittest.main()
