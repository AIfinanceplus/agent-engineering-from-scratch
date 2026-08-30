import json
import unittest
from dataclasses import replace

from context import ExecutionContext
from observability import TraceRecorder
from r10_evals import make_r10_eval_suite
from r10_planner import R10ResearchPlanner
from r10_tooling import register_r10_tools
from scheduler import DAGScheduler
from test_r9_market_pricing import fake_bls, fake_eia, fake_fred
from tools import TOOL_REGISTRY


CONTEXT = ExecutionContext(
    tenant_id="demo-tenant",
    user_id="user-r10",
    agent_id="macro-research-agent",
    task_id="r10-test-root",
    trace_id="r10-test-trace",
)


class R10IntegrationTests(unittest.TestCase):
    def setUp(self):
        register_r10_tools()
        self.originals = {
            name: TOOL_REGISTRY[name]
            for name in ("fetch_bls_api_series", "fetch_fred_api_series", "fetch_eia_api_series")
        }
        TOOL_REGISTRY["fetch_bls_api_series"] = replace(
            self.originals["fetch_bls_api_series"], function=fake_bls
        )
        TOOL_REGISTRY["fetch_fred_api_series"] = replace(
            self.originals["fetch_fred_api_series"], function=fake_fred
        )
        TOOL_REGISTRY["fetch_eia_api_series"] = replace(
            self.originals["fetch_eia_api_series"], function=fake_eia
        )

    def tearDown(self):
        for name, tool in self.originals.items():
            TOOL_REGISTRY[name] = tool

    def _run(self, domain):
        blueprint, plan = R10ResearchPlanner().build(
            "Assess current inflation pressure.",
            domain=domain,
            reference_date="2026-08-30",
        )
        result = DAGScheduler().run(
            plan,
            execution_context=CONTEXT,
            trace_recorder=TraceRecorder(f"{CONTEXT.trace_id}:{domain}"),
        )
        return blueprint, result

    def test_investment_adds_t1_and_i1_without_mutating_s1_lineage(self):
        blueprint, result = self._run("investment")
        self.assertTrue(result["ok"], result.get("error"))
        task_ids = [row["task_id"] for row in result["plan"]["tasks"]]
        self.assertIn("T1", task_ids)
        self.assertIn("I1", task_ids)
        self.assertLess(task_ids.index("F1"), task_ids.index("T1"))
        self.assertLess(task_ids.index("T1"), task_ids.index("I1"))
        self.assertLess(task_ids.index("M6"), task_ids.index("I1"))

        s1_ids = set(result["results"]["S1"]["evidence_ids"])
        m6_ids = set(result["results"]["M6"]["evidence_ids"])
        t1 = result["results"]["T1"]
        i1 = result["results"]["I1"]
        self.assertEqual(t1["artifact_type"], "r10_numerical_research_target")
        self.assertEqual(t1["status"], "NUMERICAL_TARGET_AVAILABLE")
        self.assertEqual(t1["method"], "one_step_change_persistence_baseline")
        self.assertEqual(set(t1["evidence_ids"]), {"FRED:T5YIE"})
        self.assertEqual(set(i1["research_evidence_ids"]), s1_ids)
        self.assertEqual(set(i1["market_evidence_ids"]), m6_ids)
        self.assertEqual(set(i1["evidence_ids"]), s1_ids | m6_ids)
        self.assertFalse(s1_ids & m6_ids)
        self.assertEqual(result["results"]["D1"]["evidence_ids"], result["results"]["S1"]["evidence_ids"])
        self.assertEqual(result["results"]["F1"]["evidence_ids"], result["results"]["S1"]["evidence_ids"])

        # fake_fred T5YIE is 2.35 -> 2.40, so the one-step target is 2.45.
        self.assertAlmostEqual(t1["target_value"], 2.45)
        self.assertEqual(i1["mispricing"]["status"], "NUMERIC_GAP_AVAILABLE")
        self.assertAlmostEqual(i1["mispricing"]["gap_magnitude_pp"], 0.05)
        self.assertAlmostEqual(i1["mispricing"]["gap_magnitude_bp"], 5.0)
        self.assertEqual(
            i1["scenario_payoff_template"]["status"],
            "STANDARDIZED_MARKET_MOVE_PAYOFF_TEMPLATE_AVAILABLE",
        )
        self.assertTrue(
            all(row["probability"] is None for row in i1["scenario_payoff_template"]["scenarios"])
        )
        self.assertEqual(
            i1["expected_value"]["status"],
            "EV_NOT_COMPUTABLE_MISSING_SCENARIO_PROBABILITIES",
        )

        suite = make_r10_eval_suite(blueprint.to_dict(), result, "investment")
        self.assertEqual(suite["passed"], 7, suite)
        self.assertEqual(suite["total"], 7)
        self.assertEqual(suite["serialization_contract"], "json_safe")
        json.dumps(suite)

    def test_policy_preserves_same_research_world_without_t1_or_i1(self):
        inv_blueprint, inv_result = self._run("investment")
        pol_blueprint, pol_result = self._run("policy")
        self.assertTrue(pol_result["ok"], pol_result.get("error"))
        self.assertEqual(inv_blueprint.to_dict()["queries"], pol_blueprint.to_dict()["queries"])
        self.assertEqual(
            inv_result["results"]["S1"]["evidence_ids"],
            pol_result["results"]["S1"]["evidence_ids"],
        )
        self.assertNotIn("T1", pol_result["results"])
        self.assertNotIn("I1", pol_result["results"])
        self.assertFalse(any(row["task_id"] == "T1" for row in pol_result["plan"]["tasks"]))
        self.assertFalse(any(row["task_id"] == "I1" for row in pol_result["plan"]["tasks"]))
        suite = make_r10_eval_suite(pol_blueprint.to_dict(), pol_result, "policy")
        self.assertEqual(suite["passed"], 7, suite)
        self.assertEqual(suite["total"], 7)
        json.dumps(suite)


if __name__ == "__main__":
    unittest.main()
