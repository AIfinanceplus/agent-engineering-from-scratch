import unittest

from r3_synthesis import synthesize_research_bundle
from r5_evals import _quality_case
from r5_quality import assess_evidence_quality


def evidence(evidence_id, as_of, values, *, claim_key=None, role=None, direction=None):
    provider = evidence_id.split(":", 1)[0]
    history = [{"period": f"2026-08-{20 + i:02d}", "value": value} for i, value in enumerate(values)]
    item = {
        "kind": "evidence",
        "evidence_id": evidence_id,
        "claim": "test",
        "value": values[-1],
        "unit": "test",
        "confidence": 1.0,
        "provider": provider,
        "as_of": as_of,
        "history": history,
        "source": {"publisher": provider, "uri": "https://example.invalid"},
    }
    if claim_key:
        item["claim_key"] = claim_key
    if role:
        item["role"] = role
    if direction:
        item["direction_override"] = direction
    return item


class R5QualityTests(unittest.TestCase):
    def test_fresh_official_evidence_scores_higher_than_stale_equivalent(self):
        fresh = evidence("FRED:T5YIE", "2026-08-28", [2.3, 2.4])
        stale = evidence("FRED:T5YIE", "2026-01-01", [2.3, 2.4])
        signal = [{"evidence_id": "FRED:T5YIE", "direction": "rising"}]
        fresh_score = assess_evidence_quality([fresh], signal, "2026-08-29")
        stale_score = assess_evidence_quality([stale], signal, "2026-08-29")
        self.assertGreater(fresh_score["support_score"], stale_score["support_score"])
        self.assertEqual(fresh_score["evidence_quality"][0]["freshness"]["status"], "fresh")
        self.assertEqual(stale_score["evidence_quality"][0]["freshness"]["status"], "stale")

    def test_cross_indicator_divergence_is_mixed_signal_not_contradiction(self):
        expectations = evidence("FRED:T5YIE", "2026-08-28", [2.3, 2.4], direction="rising")
        gasoline = evidence(
            "EIA:EMM_EPMR_PTE_NUS_DPG", "2026-08-24", [3.4, 3.2], direction="falling"
        )
        quality = assess_evidence_quality(
            [expectations, gasoline],
            [
                {"evidence_id": expectations["evidence_id"], "direction": "rising"},
                {"evidence_id": gasoline["evidence_id"], "direction": "falling"},
            ],
            "2026-08-29",
        )
        self.assertEqual(quality["relation_summary"]["mixed_signal"], 1)
        self.assertEqual(quality["relation_summary"]["contradiction"], 0)

    def test_same_claim_opposite_sources_are_a_contradiction(self):
        first = evidence(
            "SRC1:X", "2026-08-28", [1.0, 1.1],
            claim_key="same_macro_claim", role="same_role", direction="rising",
        )
        second = evidence(
            "SRC2:Y", "2026-08-28", [1.0, 0.9],
            claim_key="same_macro_claim", role="same_role", direction="falling",
        )
        quality = assess_evidence_quality(
            [first, second],
            [
                {"evidence_id": first["evidence_id"], "direction": "rising"},
                {"evidence_id": second["evidence_id"], "direction": "falling"},
            ],
            "2026-08-29",
        )
        self.assertEqual(quality["relation_summary"]["contradiction"], 1)
        self.assertGreater(quality["penalties"]["contradiction"], quality["penalties"]["mixed_signal"])
        self.assertLess(quality["support_score"], quality["base_quality_score"])

    def test_synthesis_exposes_non_probability_quality_contract(self):
        items = [
            evidence("FRED:T5YIE", "2026-08-28", [2.3, 2.4]),
            evidence("EIA:EMM_EPMR_PTE_NUS_DPG", "2026-08-24", [3.3, 3.2]),
        ]
        result = synthesize_research_bundle("Assess inflation pressure.", items, "2026-08-29")
        self.assertEqual(result["kind"], "synthesis")
        self.assertEqual(result["confidence_type"], "heuristic_support_score_not_probability")
        self.assertEqual(result["confidence"], result["quality"]["support_score"])
        self.assertIn("heuristic, not probability", result["answer"])
        self.assertIn("not causal attribution", result["answer"])

    def test_mixed_only_run_does_not_require_nonzero_contradiction_penalty(self):
        items = [
            evidence("FRED:T5YIE", "2026-08-28", [2.3, 2.4]),
            evidence("EIA:EMM_EPMR_PTE_NUS_DPG", "2026-08-24", [3.3, 3.2]),
        ]
        artifact = synthesize_research_bundle("Assess inflation pressure.", items, "2026-08-29")
        self.assertEqual(artifact["quality"]["relation_summary"]["contradiction"], 0)
        case = _quality_case({"final_artifact": artifact, "evidence": items})
        guard = next(
            check for check in case["report"]["checks"] if check["check_id"] == "contradiction_guardrail"
        )
        self.assertTrue(guard["passed"], guard)


if __name__ == "__main__":
    unittest.main()
