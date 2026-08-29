import unittest
from dataclasses import replace

from context import ExecutionContext
from observability import TraceRecorder
from r6_domain import synthesize_domain_brief
from r6_evals import make_r6_eval_suite
from r6_planner import R6ResearchPlanner
from r6_tooling import register_r6_tools
from scheduler import DAGScheduler
from tools import TOOL_REGISTRY


CONTEXT = ExecutionContext(
    tenant_id="demo-tenant",
    user_id="user-r6",
    agent_id="macro-research-agent",
    task_id="r6-test-root",
    trace_id="r6-test-trace",
)


def evidence(provider, series_id, label, unit, as_of, values):
    history = []
    if provider == "BLS":
        for year, month, value in values:
            history.append({"year": year, "month": month, "period_key": f"{year:04d}-{month:02d}", "value": value})
    else:
        for period, value in values:
            history.append({"period": period, "value": value})
    return {
        "kind": "evidence",
        "evidence_id": f"{provider}:{series_id}",
        "claim": f"{label} latest",
        "value": history[-1]["value"],
        "unit": unit,
        "confidence": 1.0,
        "provider": provider,
        "series_id": series_id,
        "as_of": as_of,
        "history": history,
        "source": {
            "source_id": f"{provider}:{series_id}",
            "title": label,
            "publisher": provider,
            "uri": "https://example.invalid/r6-test",
        },
    }


def bls(series_id, label):
    return evidence(
        "BLS", series_id, label, "index_level", "2026-08",
        [(2025, 7, 100.0), (2025, 8, 100.2), (2026, 7, 102.8), (2026, 8, 103.2)],
    )


def fred(series_id, label, unit):
    return evidence(
        "FRED", series_id, label, unit, "2026-08-28",
        [("2026-08-27", 2.35), ("2026-08-28", 2.40)],
    )


def eia(series_id, label, unit):
    return evidence(
        "EIA", series_id, label, unit, "2026-08-24",
        [("2026-08-17", 3.20), ("2026-08-24", 3.25)],
    )


def upstream(*, contradiction=0, mixed=0, confidence=0.88):
    return {
        "kind": "synthesis",
        "answer": "grounded macro synthesis",
        "confidence": confidence,
        "confidence_type": "heuristic_support_score_not_probability",
        "evidence_ids": ["FRED:T5YIE", "EIA:GAS"],
        "signals": [
            {"evidence_id": "FRED:T5YIE", "direction": "rising"},
            {"evidence_id": "EIA:GAS", "direction": "falling" if mixed else "rising"},
        ],
        "quality": {
            "relation_summary": {
                "agreement": 0,
                "mixed_signal": mixed,
                "contradiction": contradiction,
            }
        },
        "limitations": ["test limitation"],
    }


class R6DomainUnitTests(unittest.TestCase):
    def test_investment_brief_inherits_evidence_and_confidence(self):
        result = synthesize_domain_brief(
            "Assess inflation pressure.", "investment", upstream(), "2026-08-29"
        )
        self.assertEqual(result["domain"], "investment")
        self.assertEqual(result["evidence_ids"], ["FRED:T5YIE", "EIA:GAS"])
        self.assertEqual(result["confidence"], 0.88)
        self.assertEqual(result["guardrails"]["new_data_fetches"], 0)
        self.assertEqual(result["guardrails"]["scenario_weighting"], "qualitative_not_probability")
        self.assertIn("thesis", result["sections"])
        self.assertIn("what_would_change_the_view", result["sections"])

    def test_policy_brief_has_options_tradeoffs_and_monitoring(self):
        result = synthesize_domain_brief(
            "Assess inflation pressure.", "policy", upstream(mixed=1), "2026-08-29"
        )
        self.assertEqual(result["decision_status"], "MONITOR_MIXED_SIGNAL")
        self.assertIn("options", result["sections"])
        self.assertIn("tradeoffs", result["sections"])
        self.assertEqual(len(result["monitoring"]), 2)

    def test_contradiction_blocks_research_ready_status(self):
        result = synthesize_domain_brief(
            "Assess inflation pressure.", "investment", upstream(contradiction=1, confidence=0.95), "2026-08-29"
        )
        self.assertEqual(result["decision_status"], "RECONCILE_BEFORE_ACTION")
        self.assertEqual(result["confidence"], 0.95)

    def test_domain_synthesis_rejects_unapproved_domain(self):
        with self.assertRaises(ValueError):
            synthesize_domain_brief("x", "trading_bot", upstream(), "2026-08-29")


class R6IntegrationTests(unittest.TestCase):
    def setUp(self):
        register_r6_tools()
        self.originals = {
            name: TOOL_REGISTRY[name]
            for name in ("fetch_bls_api_series", "fetch_fred_api_series", "fetch_eia_api_series")
        }
        TOOL_REGISTRY["fetch_bls_api_series"] = replace(self.originals["fetch_bls_api_series"], function=bls)
        TOOL_REGISTRY["fetch_fred_api_series"] = replace(self.originals["fetch_fred_api_series"], function=fred)
        TOOL_REGISTRY["fetch_eia_api_series"] = replace(self.originals["fetch_eia_api_series"], function=eia)

    def tearDown(self):
        for name, tool in self.originals.items():
            TOOL_REGISTRY[name] = tool

    def _run(self, domain):
        blueprint, plan = R6ResearchPlanner().build(
            "Assess current inflation pressure.",
            domain=domain,
            reference_date="2026-08-29",
        )
        result = DAGScheduler().run(
            plan,
            execution_context=CONTEXT,
            trace_recorder=TraceRecorder(f"{CONTEXT.trace_id}:{domain}"),
        )
        return blueprint, result

    def test_investment_dag_runs_q_to_s1_to_d1_and_passes_evals(self):
        blueprint, result = self._run("investment")
        self.assertTrue(result["ok"], result.get("error"))
        self.assertEqual(
            [item["task_id"] for item in result["plan"]["tasks"]],
            ["Q1", "Q2", "Q3", "Q4", "S1", "D1"],
        )
        self.assertEqual(result["final_artifact"]["domain"], "investment")
        self.assertEqual(len(result["citations"]), 4)
        self.assertEqual(result["results"]["D1"]["evidence_ids"], result["results"]["S1"]["evidence_ids"])
        suite = make_r6_eval_suite(blueprint.to_dict(), result, "investment")
        self.assertEqual(suite["passed"], 3, suite)
        self.assertEqual(suite["total"], 3)

    def test_policy_dag_uses_same_evidence_with_different_domain_lens(self):
        blueprint, result = self._run("policy")
        self.assertTrue(result["ok"], result.get("error"))
        self.assertEqual(result["final_artifact"]["domain"], "policy")
        self.assertEqual(result["results"]["D1"]["evidence_ids"], result["results"]["S1"]["evidence_ids"])
        suite = make_r6_eval_suite(blueprint.to_dict(), result, "policy")
        self.assertEqual(suite["passed"], 3, suite)


if __name__ == "__main__":
    unittest.main()
