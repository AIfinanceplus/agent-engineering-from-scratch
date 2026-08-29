import unittest

from context import ExecutionContext
from macro_analysis import compare_cpi_series
from macro_sources import BLSAdapter, BLS_SERIES, fetch_bls_series
from observability import TraceRecorder
from planner import CPIResearchPlanner
from scheduler import DAGScheduler
from tools import reset_teaching_tools


CONTEXT = ExecutionContext(
    tenant_id="demo-tenant",
    user_id="user-123",
    agent_id="macro-research-agent",
    task_id="r1-cpi-root",
    trace_id="r1-cpi-trace",
)


class BLSSourceAdapterTests(unittest.TestCase):
    def test_fixture_uses_same_normalized_evidence_contract(self):
        payload = fetch_bls_series(
            BLS_SERIES["headline_cpi"]["series_id"],
            BLS_SERIES["headline_cpi"]["label"],
            "fixture",
        )
        self.assertEqual(payload["kind"], "evidence")
        self.assertEqual(payload["source_mode"], "fixture")
        self.assertEqual(payload["series_id"], "CUSR0000SA0")
        self.assertEqual(payload["history"][-1]["period_key"], "2026-02")
        self.assertTrue(payload["source"]["uri"].startswith("fixture://bls/"))

    def test_live_adapter_parses_bls_api_shape_without_network(self):
        observed_urls = []

        def fake_transport(url):
            observed_urls.append(url)
            return {
                "status": "REQUEST_SUCCEEDED",
                "message": [],
                "Results": {
                    "series": [
                        {
                            "seriesID": "CUSR0000SA0",
                            "data": [
                                {"year": "2025", "period": "M02", "periodName": "February", "value": "100.0", "footnotes": []},
                                {"year": "2026", "period": "M02", "periodName": "February", "value": "103.0", "footnotes": []},
                            ],
                        }
                    ]
                },
            }

        adapter = BLSAdapter(transport=fake_transport)
        payload = adapter.fetch_series("CUSR0000SA0", "Headline CPI", "live")
        self.assertEqual(payload["source_mode"], "live")
        self.assertEqual(payload["value"], 103.0)
        self.assertEqual(len(payload["history"]), 2)
        self.assertEqual(
            observed_urls,
            ["https://api.bls.gov/publicAPI/v1/timeseries/data/CUSR0000SA0"],
        )


class CPIAnalysisTests(unittest.TestCase):
    def test_compare_cpi_series_computes_latest_yoy_from_history(self):
        headline = fetch_bls_series("CUSR0000SA0", "Headline CPI", "fixture")
        core = fetch_bls_series("CUSR0000SA0L1E", "Core CPI", "fixture")
        result = compare_cpi_series(headline, core)

        self.assertEqual(result["kind"], "synthesis")
        self.assertEqual(result["metrics"]["period"], "2026-02")
        self.assertAlmostEqual(result["metrics"]["headline_yoy_pct"], 2.616, places=3)
        self.assertAlmostEqual(result["metrics"]["core_yoy_pct"], 3.095, places=3)
        self.assertAlmostEqual(result["metrics"]["core_minus_headline_pp"], 0.479, places=3)
        self.assertEqual(
            result["evidence_ids"],
            ["BLS:CUSR0000SA0", "BLS:CUSR0000SA0L1E"],
        )


class CPIResearchPlanTests(unittest.TestCase):
    def setUp(self):
        reset_teaching_tools()

    def test_planner_separates_source_tasks_from_analysis(self):
        plan = CPIResearchPlanner().plan("Compare headline and core CPI", data_mode="fixture")
        task_map = plan.task_map()
        self.assertEqual([task.task_id for task in plan.tasks], ["H1", "C1", "A1"])
        self.assertEqual(task_map["A1"].depends_on, ["H1", "C1"])
        self.assertEqual(task_map["A1"].arguments["headline"], {"from_task": "H1"})
        self.assertEqual(task_map["A1"].arguments["core"], {"from_task": "C1"})
        self.assertEqual(task_map["H1"].arguments["mode"], "fixture")

    def test_fixture_plan_runs_through_existing_runtime_and_provenance(self):
        trace = TraceRecorder(CONTEXT.trace_id)
        result = DAGScheduler().run(
            CPIResearchPlanner().plan(
                "Compare headline and core CPI",
                data_mode="fixture",
            ),
            execution_context=CONTEXT,
            trace_recorder=trace,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["plan"]["status"], "completed")
        self.assertEqual(len(result["evidence"]), 2)
        self.assertEqual(
            [item["evidence_id"] for item in result["evidence"]],
            ["BLS:CUSR0000SA0", "BLS:CUSR0000SA0L1E"],
        )
        self.assertEqual(len(result["citations"]), 2)
        self.assertIn("headline CPI YoY", result["final_result"])
        self.assertEqual(result["trace"]["metrics"]["tool_attempts"], 3)


if __name__ == "__main__":
    unittest.main()
