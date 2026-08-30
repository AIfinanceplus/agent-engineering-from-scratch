import unittest
from dataclasses import replace

from observability import TraceRecorder
from r8_evals import make_r8_eval_suite
from r8_planner import R8ResearchPlanner
from r8_tooling import register_r8_tools
from scheduler import DAGScheduler
from test_r7_forecast import CONTEXT, bls, eia, fred
from tools import TOOL_REGISTRY


class R8IntegrationTests(unittest.TestCase):
    def setUp(self):
        register_r8_tools()
        self.originals = {
            name: TOOL_REGISTRY[name]
            for name in ("fetch_bls_api_series", "fetch_fred_api_series", "fetch_eia_api_series")
        }
        TOOL_REGISTRY["fetch_bls_api_series"] = replace(
            self.originals["fetch_bls_api_series"], function=bls
        )
        TOOL_REGISTRY["fetch_fred_api_series"] = replace(
            self.originals["fetch_fred_api_series"], function=fred
        )
        TOOL_REGISTRY["fetch_eia_api_series"] = replace(
            self.originals["fetch_eia_api_series"], function=eia
        )

    def tearDown(self):
        for name, tool in self.originals.items():
            TOOL_REGISTRY[name] = tool

    def _run(self, domain):
        blueprint, plan = R8ResearchPlanner().build(
            "Assess current inflation pressure.",
            domain=domain,
            reference_date="2026-08-29",
        )
        result = DAGScheduler().run(
            plan,
            execution_context=CONTEXT,
            trace_recorder=TraceRecorder(f"{CONTEXT.trace_id}:r8:{domain}"),
        )
        return blueprint, result

    def test_investment_professional_lens_is_grounded_and_forecast_compatible(self):
        blueprint, result = self._run("investment")
        self.assertTrue(result["ok"], result.get("error"))
        d1 = result["results"]["D1"]
        f1 = result["results"]["F1"]
        self.assertEqual(d1["decision_framework_version"], "R8")
        self.assertEqual(d1["sections"]["market_pricing"]["status"], "PRICING_NOT_MODELED")
        self.assertEqual(d1["sections"]["expected_value"]["status"], "EV_NOT_COMPUTABLE")
        self.assertEqual(d1["sections"]["position_framework"]["position"], "NONE")
        self.assertEqual(f1["evidence_ids"], result["results"]["S1"]["evidence_ids"])
        suite = make_r8_eval_suite(blueprint.to_dict(), result, "investment")
        self.assertEqual(suite["passed"], 5, suite)
        self.assertEqual(suite["total"], 5)

    def test_policy_uses_identical_world_state_but_different_decision_function(self):
        inv_blueprint, inv = self._run("investment")
        pol_blueprint, pol = self._run("policy")
        self.assertTrue(inv["ok"], inv.get("error"))
        self.assertTrue(pol["ok"], pol.get("error"))

        self.assertEqual(inv_blueprint.to_dict()["queries"], pol_blueprint.to_dict()["queries"])
        self.assertEqual(inv["results"]["S1"]["evidence_ids"], pol["results"]["S1"]["evidence_ids"])
        self.assertEqual(inv["evidence"], pol["evidence"])
        self.assertNotEqual(inv["results"]["D1"]["sections"]["brief_type"], pol["results"]["D1"]["sections"]["brief_type"])

        policy_sections = pol["results"]["D1"]["sections"]
        self.assertEqual(
            policy_sections["counterfactual_analysis"]["status"],
            "COUNTERFACTUAL_EFFECTS_NOT_ESTIMATED",
        )
        self.assertEqual(policy_sections["distributional_analysis"]["status"], "INCIDENCE_NOT_MODELED")
        self.assertEqual(policy_sections["implementation"]["status"], "NOT_READY_FOR_DIRECTIVE")

        self.assertEqual(
            [item["target_evidence_id"] for item in inv["results"]["F1"]["forecasts"]],
            [item["target_evidence_id"] for item in pol["results"]["F1"]["forecasts"]],
        )
        suite = make_r8_eval_suite(pol_blueprint.to_dict(), pol, "policy")
        self.assertEqual(suite["passed"], 5, suite)


if __name__ == "__main__":
    unittest.main()
