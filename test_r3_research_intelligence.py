import unittest
from dataclasses import replace

from context import ExecutionContext
from observability import TraceRecorder
from r3_decomposition import QueryCompiler, ResearchDecomposer, build_blueprint
from r3_evals import make_r3_eval_suite
from r3_planner import R3ResearchPlanner
from r3_synthesis import synthesize_research_bundle
from r3_tooling import register_r3_tools
from scheduler import DAGScheduler
from tools import TOOL_REGISTRY


CONTEXT = ExecutionContext(
    tenant_id="demo-tenant",
    user_id="user-r3",
    agent_id="macro-research-agent",
    task_id="r3-test-root",
    trace_id="r3-test-trace",
)


def _bls(series_id, label):
    return {
        "kind": "evidence",
        "evidence_id": f"BLS:{series_id}",
        "claim": f"{label} latest 103.0",
        "value": 103.0,
        "unit": "index_level",
        "confidence": 1.0,
        "provider": "BLS",
        "series_id": series_id,
        "as_of": "2026-08",
        "history": [
            {"year": 2025, "month": 8, "period_key": "2025-08", "value": 100.0},
            {"year": 2026, "month": 8, "period_key": "2026-08", "value": 103.0},
        ],
        "source": {
            "source_id": f"BLS:{series_id}",
            "title": label,
            "publisher": "BLS",
            "uri": "https://api.bls.gov/teaching-test",
        },
        "note": "API-shaped test result",
    }


def _fred(series_id, label, unit):
    return {
        "kind": "evidence",
        "evidence_id": f"FRED:{series_id}",
        "claim": f"{label} latest 2.4",
        "value": 2.4,
        "unit": unit,
        "confidence": 1.0,
        "provider": "FRED",
        "series_id": series_id,
        "as_of": "2026-08-28",
        "history": [
            {"period": "2026-08-27", "value": 2.35},
            {"period": "2026-08-28", "value": 2.4},
        ],
        "source": {
            "source_id": f"FRED:{series_id}",
            "title": label,
            "publisher": "FRED",
            "uri": "https://fred.stlouisfed.org/teaching-test",
        },
        "note": "API-shaped test result",
    }


def _eia(series_id, label, unit):
    return {
        "kind": "evidence",
        "evidence_id": f"EIA:{series_id}",
        "claim": f"{label} latest 3.25",
        "value": 3.25,
        "unit": unit,
        "confidence": 1.0,
        "provider": "EIA",
        "series_id": series_id,
        "as_of": "2026-08-24",
        "history": [
            {"period": "2026-08-17", "value": 3.2},
            {"period": "2026-08-24", "value": 3.25},
        ],
        "source": {
            "source_id": f"EIA:{series_id}",
            "title": label,
            "publisher": "EIA",
            "uri": "https://api.eia.gov/teaching-test",
        },
        "note": "API-shaped test result",
    }


class R3DecompositionTests(unittest.TestCase):
    def test_broad_inflation_question_decomposes_to_four_capabilities(self):
        blueprint = build_blueprint("Assess current inflation pressure.")
        self.assertEqual(
            [item.capability for item in blueprint.subquestions],
            ["headline_cpi", "core_cpi", "breakeven_5y", "regular_gasoline"],
        )
        self.assertEqual([item.query_id for item in blueprint.queries], ["Q1", "Q2", "Q3", "Q4"])
        for query in blueprint.queries:
            self.assertNotIn("api_key", query.arguments)
            self.assertNotIn("url", query.arguments)
            self.assertNotIn("endpoint", query.arguments)

    def test_narrow_headline_core_question_prunes_other_sources_and_credentials(self):
        blueprint = build_blueprint("Compare headline and core CPI.")
        self.assertEqual(
            [item.capability for item in blueprint.queries],
            ["headline_cpi", "core_cpi"],
        )
        self.assertEqual([item.provider for item in blueprint.queries], ["BLS", "BLS"])
        self.assertEqual(
            sorted({env for item in blueprint.queries for env in item.requires_env}),
            [],
        )
        _, plan = R3ResearchPlanner().build(
            "Compare headline and core CPI.",
            reference_date="2026-08-29",
        )
        self.assertEqual([task.task_id for task in plan.tasks], ["Q1", "Q2", "S1"])

    def test_unsupported_question_fails_before_query_execution(self):
        with self.assertRaises(ValueError):
            ResearchDecomposer().decompose("What is the weather in Tokyo?")

    def test_query_compiler_rejects_unapproved_capability(self):
        subquestions = list(ResearchDecomposer().decompose("Compare headline and core CPI."))
        bad = replace(subquestions[0], capability="arbitrary_private_database")
        with self.assertRaises(ValueError):
            QueryCompiler().compile((bad,))


class R3SynthesisTests(unittest.TestCase):
    def test_synthesis_accepts_variable_evidence_bundle(self):
        result = synthesize_research_bundle(
            "Compare headline and core CPI.",
            [_bls("HEAD", "Headline"), _bls("CORE", "Core")],
            "2026-08-29",
        )
        self.assertEqual(result["kind"], "synthesis")
        self.assertEqual(result["evidence_ids"], ["BLS:HEAD", "BLS:CORE"])
        self.assertEqual(len(result["signals"]), 2)
        self.assertIn("not causal attribution", result["answer"])


class R3IntegrationTests(unittest.TestCase):
    def setUp(self):
        register_r3_tools()
        self.originals = {
            name: TOOL_REGISTRY[name]
            for name in (
                "fetch_bls_api_series",
                "fetch_fred_api_series",
                "fetch_eia_api_series",
            )
        }
        TOOL_REGISTRY["fetch_bls_api_series"] = replace(
            self.originals["fetch_bls_api_series"], function=_bls
        )
        TOOL_REGISTRY["fetch_fred_api_series"] = replace(
            self.originals["fetch_fred_api_series"], function=_fred
        )
        TOOL_REGISTRY["fetch_eia_api_series"] = replace(
            self.originals["fetch_eia_api_series"], function=_eia
        )

    def tearDown(self):
        for name, tool in self.originals.items():
            TOOL_REGISTRY[name] = tool

    def test_broad_question_builds_and_executes_dynamic_four_query_dag(self):
        blueprint, plan = R3ResearchPlanner().build(
            "Assess current inflation pressure.",
            reference_date="2026-08-29",
        )
        trace = TraceRecorder(CONTEXT.trace_id)
        result = DAGScheduler().run(
            plan,
            execution_context=CONTEXT,
            trace_recorder=trace,
        )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertEqual([task["task_id"] for task in result["plan"]["tasks"]], ["Q1", "Q2", "Q3", "Q4", "S1"])
        self.assertEqual(len(result["evidence"]), 4)
        self.assertEqual(len(result["citations"]), 4)
        self.assertEqual(len(result["final_artifact"]["evidence_ids"]), 4)
        self.assertGreaterEqual(result["trace"]["metrics"]["tool_attempts"], 5)

        suite = make_r3_eval_suite(blueprint.to_dict(), result)
        self.assertEqual(suite["passed"], 2, suite)
        self.assertEqual(suite["total"], 2)


if __name__ == "__main__":
    unittest.main()
