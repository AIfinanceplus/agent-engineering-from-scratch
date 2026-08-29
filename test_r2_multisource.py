import unittest

from context import ExecutionContext
from macro_multisource import EIAAdapter, FREDAdapter
from macro_multisource_analysis import synthesize_macro_signals
from macro_sources import BLSAdapter, BLS_SERIES
from observability import TraceRecorder
from r2_planner import MultiSourceMacroPlanner
from r2_tooling import register_r2_tools
from scheduler import DAGScheduler


CONTEXT = ExecutionContext(
    tenant_id="demo-tenant",
    user_id="user-123",
    agent_id="macro-research-agent",
    task_id="r2-test-root",
    trace_id="r2-test-trace",
)


class MultiSourceAdapterTests(unittest.TestCase):
    def test_fred_fixture_normalizes_to_evidence(self):
        result = FREDAdapter(env={}).fetch_series(
            "T5YIE", "5-Year Breakeven Inflation Rate", "percent", "fixture"
        )
        self.assertEqual(result["evidence_id"], "FRED:T5YIE")
        self.assertEqual(result["provider"], "FRED")
        self.assertEqual(result["as_of"], "2026-03-13")
        self.assertEqual(result["value"], 2.25)
        self.assertTrue(result["history"])

    def test_eia_fixture_normalizes_to_evidence(self):
        series_id = "PET.EMM_EPMR_PTE_NUS_DPG.W"
        result = EIAAdapter(env={}).fetch_series(
            series_id,
            "U.S. Regular All Formulations Retail Gasoline Prices",
            "dollars_per_gallon",
            "fixture",
        )
        self.assertEqual(result["evidence_id"], f"EIA:{series_id}")
        self.assertEqual(result["provider"], "EIA")
        self.assertEqual(result["as_of"], "2026-03-16")
        self.assertEqual(result["value"], 3.22)

    def test_live_fred_requires_runtime_owned_key(self):
        with self.assertRaisesRegex(RuntimeError, "FRED_API_KEY"):
            FREDAdapter(env={}).fetch_series("T5YIE", "test", "percent", "live")

    def test_live_eia_requires_runtime_owned_key(self):
        with self.assertRaisesRegex(RuntimeError, "EIA_API_KEY"):
            EIAAdapter(env={}).fetch_series("SERIES", "test", "unit", "live")

    def test_fred_key_is_used_for_transport_but_not_persisted_in_evidence(self):
        seen = []

        def transport(url):
            seen.append(url)
            return {"observations": [{"date": "2026-03-01", "value": "2.40"}]}

        result = FREDAdapter(transport=transport, env={"FRED_API_KEY": "secret-key"}).fetch_series(
            "T5YIE", "5-Year Breakeven Inflation Rate", "percent", "live"
        )
        self.assertIn("secret-key", seen[0])
        self.assertNotIn("secret-key", str(result))
        self.assertEqual(result["source"]["uri"], "https://fred.stlouisfed.org/series/T5YIE")


class MultiSourceAnalysisTests(unittest.TestCase):
    def setUp(self):
        headline_cfg = BLS_SERIES["headline_cpi"]
        core_cfg = BLS_SERIES["core_cpi"]
        self.headline = BLSAdapter().fetch_series(
            headline_cfg["series_id"], headline_cfg["label"], "fixture"
        )
        self.core = BLSAdapter().fetch_series(
            core_cfg["series_id"], core_cfg["label"], "fixture"
        )
        self.breakeven = FREDAdapter().fetch_series(
            "T5YIE", "5-Year Breakeven Inflation Rate", "percent", "fixture"
        )
        self.gasoline = EIAAdapter().fetch_series(
            "PET.EMM_EPMR_PTE_NUS_DPG.W",
            "U.S. Regular All Formulations Retail Gasoline Prices",
            "dollars_per_gallon",
            "fixture",
        )

    def test_cross_source_synthesis_tracks_freshness_and_limit(self):
        result = synthesize_macro_signals(
            self.headline,
            self.core,
            self.breakeven,
            self.gasoline,
            "2026-03-20",
        )
        self.assertEqual(result["kind"], "synthesis")
        self.assertEqual(len(result["evidence_ids"]), 4)
        self.assertEqual(result["signals"]["energy_price_pressure"], "rising")
        self.assertEqual(result["signals"]["market_inflation_expectations"], "roughly_flat")
        self.assertEqual(result["freshness"]["FRED:T5YIE"]["status"], "fresh")
        self.assertEqual(
            result["freshness"]["EIA:PET.EMM_EPMR_PTE_NUS_DPG.W"]["status"],
            "fresh",
        )
        self.assertTrue(any("not causal" in item for item in result["limitations"]))


class MultiSourcePlannerRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        register_r2_tools()

    def test_planner_requires_four_sources_before_analysis(self):
        plan = MultiSourceMacroPlanner().plan(
            "Assess inflation pressure",
            mode="fixture",
            reference_date="2026-03-20",
        )
        self.assertEqual([task.task_id for task in plan.tasks], ["H1", "C1", "F1", "G1", "A1"])
        self.assertEqual(plan.tasks[-1].depends_on, ["H1", "C1", "F1", "G1"])
        self.assertEqual(plan.tasks[-1].tool_name, "synthesize_macro_signals")

    def test_full_fixture_run_produces_four_grounded_citations(self):
        plan = MultiSourceMacroPlanner().plan(
            "Assess inflation pressure",
            mode="fixture",
            reference_date="2026-03-20",
        )
        trace = TraceRecorder(CONTEXT.trace_id)
        result = DAGScheduler().run(
            plan,
            execution_context=CONTEXT,
            trace_recorder=trace,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["plan"]["status"], "completed")
        self.assertEqual(len(result["evidence"]), 4)
        self.assertEqual(len(result["citations"]), 4)
        self.assertEqual(result["final_artifact"]["kind"], "synthesis")
        self.assertEqual(result["trace"]["span_count"], 6)
        self.assertEqual(result["trace"]["metrics"]["tool_attempts"], 5)
        citation_ids = {item["evidence_id"] for item in result["citations"]}
        self.assertEqual(citation_ids, set(result["final_artifact"]["evidence_ids"]))


if __name__ == "__main__":
    unittest.main()
