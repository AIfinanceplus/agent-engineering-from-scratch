import unittest
from dataclasses import replace

from context import ExecutionContext
from observability import TraceRecorder
from r9_evals import make_r9_eval_suite
from r9_market import EXPECTED_IDS, build_market_pricing_snapshot
from r9_planner import R9ResearchPlanner
from r9_tooling import register_r9_tools
from scheduler import DAGScheduler
from tools import TOOL_REGISTRY


CONTEXT = ExecutionContext(
    tenant_id="demo-tenant",
    user_id="user-r9",
    agent_id="macro-research-agent",
    task_id="r9-test-root",
    trace_id="r9-test-trace",
)

MARKET_VALUES = {
    "DFF": 5.33,
    "DGS2": 4.10,
    "DGS10": 4.30,
    "DFII10": 1.90,
    "T10YIE": 2.40,
}


def _point_evidence(series_id, label, unit, value, previous=None):
    previous = value - 0.05 if previous is None else previous
    return {
        "kind": "evidence",
        "evidence_id": f"FRED:{series_id}",
        "claim": f"{label} latest",
        "value": value,
        "unit": unit,
        "confidence": 1.0,
        "provider": "FRED",
        "series_id": series_id,
        "as_of": "2026-08-28",
        "history": [
            {"period": "2026-08-27", "value": previous},
            {"period": "2026-08-28", "value": value},
        ],
        "source": {
            "source_id": f"FRED:{series_id}",
            "title": label,
            "publisher": "Federal Reserve Bank of St. Louis",
            "uri": f"https://fred.stlouisfed.org/series/{series_id}",
        },
    }


def fake_fred(series_id, label, unit):
    if series_id == "T5YIE":
        return _point_evidence(series_id, label, unit, 2.40, 2.35)
    return _point_evidence(series_id, label, unit, MARKET_VALUES[series_id])


def fake_bls(series_id, label):
    return {
        "kind": "evidence",
        "evidence_id": f"BLS:{series_id}",
        "claim": f"{label} latest",
        "value": 103.2,
        "unit": "index_level",
        "confidence": 1.0,
        "provider": "BLS",
        "series_id": series_id,
        "as_of": "2026-08",
        "history": [
            {"year": 2025, "month": 7, "period_key": "2025-07", "value": 100.0},
            {"year": 2025, "month": 8, "period_key": "2025-08", "value": 100.2},
            {"year": 2026, "month": 7, "period_key": "2026-07", "value": 102.8},
            {"year": 2026, "month": 8, "period_key": "2026-08", "value": 103.2},
        ],
        "source": {
            "source_id": f"BLS:{series_id}",
            "title": label,
            "publisher": "U.S. Bureau of Labor Statistics",
            "uri": "https://www.bls.gov/",
        },
    }


def fake_eia(series_id, label, unit):
    return {
        "kind": "evidence",
        "evidence_id": f"EIA:{series_id}",
        "claim": f"{label} latest",
        "value": 3.25,
        "unit": unit,
        "confidence": 1.0,
        "provider": "EIA",
        "series_id": series_id,
        "as_of": "2026-08-24",
        "history": [
            {"period": "2026-08-17", "value": 3.20},
            {"period": "2026-08-24", "value": 3.25},
        ],
        "source": {
            "source_id": f"EIA:{series_id}",
            "title": label,
            "publisher": "U.S. Energy Information Administration",
            "uri": "https://www.eia.gov/",
        },
    }


class R9MarketSnapshotTests(unittest.TestCase):
    def test_snapshot_is_observed_context_not_mispricing(self):
        snapshot = build_market_pricing_snapshot(
            fake_fred("DFF", "DFF", "percent"),
            fake_fred("DGS2", "DGS2", "percent"),
            fake_fred("DGS10", "DGS10", "percent"),
            fake_fred("DFII10", "DFII10", "percent"),
            fake_fred("T10YIE", "T10YIE", "percent"),
            "2026-08-29",
        )
        self.assertEqual(snapshot["artifact_type"], "market_pricing_snapshot")
        self.assertEqual(set(snapshot["evidence_ids"]), EXPECTED_IDS)
        self.assertEqual(snapshot["derived_observations"]["term_spread_10y_minus_2y"], 0.2)
        self.assertEqual(snapshot["derived_observations"]["curve_shape"], "POSITIVE")
        self.assertEqual(snapshot["semantics"]["fed_path"], "NOT_INFERRED_R9")
        self.assertEqual(snapshot["semantics"]["mispricing"], "NOT_COMPUTED_R9")
        self.assertEqual(snapshot["semantics"]["expected_value"], "NOT_COMPUTED_R9")
        self.assertEqual(snapshot["semantics"]["position"], "NONE_R9")


class R9IntegrationTests(unittest.TestCase):
    def setUp(self):
        register_r9_tools()
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
        blueprint, plan = R9ResearchPlanner().build(
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

    def test_investment_adds_separate_market_context_lane(self):
        blueprint, result = self._run("investment")
        self.assertTrue(result["ok"], result.get("error"))
        task_ids = [row["task_id"] for row in result["plan"]["tasks"]]
        self.assertEqual([x for x in task_ids if x.startswith("M")], ["M1", "M2", "M3", "M4", "M5", "M6"])
        s1_ids = set(result["results"]["S1"]["evidence_ids"])
        market_ids = set(result["results"]["M6"]["evidence_ids"])
        self.assertFalse(s1_ids & market_ids)
        self.assertEqual(market_ids, EXPECTED_IDS)
        self.assertEqual(set(result["results"]["D1"]["evidence_ids"]), s1_ids)
        self.assertEqual(set(result["results"]["F1"]["evidence_ids"]), s1_ids)
        suite = make_r9_eval_suite(blueprint.to_dict(), result, "investment")
        self.assertEqual(suite["passed"], 6, suite)
        self.assertEqual(suite["total"], 6)

    def test_policy_keeps_core_research_without_market_lane(self):
        inv_blueprint, inv_result = self._run("investment")
        pol_blueprint, pol_result = self._run("policy")
        self.assertTrue(pol_result["ok"], pol_result.get("error"))
        self.assertEqual(inv_blueprint.to_dict()["queries"], pol_blueprint.to_dict()["queries"])
        self.assertEqual(
            inv_result["results"]["S1"]["evidence_ids"],
            pol_result["results"]["S1"]["evidence_ids"],
        )
        self.assertEqual(
            [row["target_evidence_id"] for row in inv_result["results"]["F1"]["forecasts"]],
            [row["target_evidence_id"] for row in pol_result["results"]["F1"]["forecasts"]],
        )
        self.assertFalse(any(row["task_id"].startswith("M") for row in pol_result["plan"]["tasks"]))
        suite = make_r9_eval_suite(pol_blueprint.to_dict(), pol_result, "policy")
        self.assertEqual(suite["passed"], 6, suite)
        self.assertEqual(suite["total"], 6)


if __name__ == "__main__":
    unittest.main()
