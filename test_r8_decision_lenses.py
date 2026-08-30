import unittest

from r8_decision import synthesize_professional_decision_brief
from r8_planner import R8ResearchPlanner


S1 = {
    "kind": "synthesis",
    "answer": "Inflation signals are mixed.",
    "confidence": 0.88,
    "confidence_type": "heuristic_support_score_not_probability",
    "evidence_ids": ["BLS:CPI", "FRED:T5YIE"],
    "signals": [
        {"evidence_id": "BLS:CPI", "direction": "falling", "yoy": 2.7},
        {"evidence_id": "FRED:T5YIE", "direction": "rising", "value": 2.4},
    ],
    "quality": {
        "relation_summary": {"agreement": 0, "mixed_signal": 1, "contradiction": 0},
        "relations": [],
    },
    "limitations": [],
}


class R8DecisionLensTests(unittest.TestCase):
    def test_investment_requires_pricing_before_position(self):
        d1 = synthesize_professional_decision_brief(
            "Assess inflation pressure.", "investment", S1, "2026-08-29"
        )
        sections = d1["sections"]
        self.assertEqual(d1["decision_framework_version"], "R8")
        self.assertEqual(d1["evidence_ids"], S1["evidence_ids"])
        self.assertEqual(d1["confidence"], S1["confidence"])
        self.assertEqual(sections["market_pricing"]["status"], "PRICING_NOT_MODELED")
        self.assertEqual(sections["expected_value"]["status"], "EV_NOT_COMPUTABLE")
        self.assertEqual(sections["position_framework"]["position"], "NONE")
        self.assertEqual(
            sections["position_framework"]["status"],
            "NO_POSITION_MIXED_SIGNAL",
        )
        self.assertEqual(
            d1["guardrails"]["expected_value_without_probability_and_payoff"],
            "forbidden",
        )

    def test_policy_requires_causal_incidence_and_implementation_evidence(self):
        d1 = synthesize_professional_decision_brief(
            "Assess inflation pressure.", "policy", S1, "2026-08-29"
        )
        sections = d1["sections"]
        self.assertEqual(d1["evidence_ids"], S1["evidence_ids"])
        self.assertEqual(
            sections["counterfactual_analysis"]["status"],
            "COUNTERFACTUAL_EFFECTS_NOT_ESTIMATED",
        )
        self.assertEqual(
            sections["distributional_analysis"]["status"],
            "INCIDENCE_NOT_MODELED",
        )
        self.assertEqual(sections["implementation"]["status"], "NOT_READY_FOR_DIRECTIVE")
        self.assertEqual(
            sections["policy_actionability"]["current_action"],
            "MONITOR_AND_UPDATE_EVIDENCE",
        )
        self.assertEqual(
            d1["guardrails"]["causal_policy_effect_without_causal_evidence"],
            "forbidden",
        )

    def test_domain_choice_does_not_change_query_generation(self):
        planner = R8ResearchPlanner()
        inv_blueprint, inv_plan = planner.build(
            "Assess current inflation pressure.",
            domain="investment",
            reference_date="2026-08-29",
        )
        pol_blueprint, pol_plan = planner.build(
            "Assess current inflation pressure.",
            domain="policy",
            reference_date="2026-08-29",
        )
        inv_queries = [query.to_dict() for query in inv_blueprint.queries]
        pol_queries = [query.to_dict() for query in pol_blueprint.queries]
        self.assertEqual(inv_queries, pol_queries)

        inv_tasks = inv_plan.to_dict()["tasks"]
        pol_tasks = pol_plan.to_dict()["tasks"]
        inv_sources = [task for task in inv_tasks if task["task_id"].startswith("Q")]
        pol_sources = [task for task in pol_tasks if task["task_id"].startswith("Q")]
        self.assertEqual(inv_sources, pol_sources)
        self.assertEqual(inv_plan.task_map()["D1"].tool_name, "synthesize_professional_decision_brief")
        self.assertEqual(pol_plan.task_map()["D1"].tool_name, "synthesize_professional_decision_brief")
        self.assertEqual(inv_plan.task_map()["F1"].depends_on, ["S1", "D1"])


if __name__ == "__main__":
    unittest.main()
