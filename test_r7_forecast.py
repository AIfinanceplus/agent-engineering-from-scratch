import tempfile
import unittest
from dataclasses import replace

from context import ExecutionContext
from observability import TraceRecorder
from r7_evals import make_r7_eval_suite
from r7_forecast import JsonForecastStore, create_forecast_pack, evaluate_forecast_pack
from r7_planner import R7ResearchPlanner
from r7_tooling import register_r7_tools
from scheduler import DAGScheduler
from tools import TOOL_REGISTRY


CONTEXT = ExecutionContext(
    tenant_id="demo-tenant",
    user_id="user-r7",
    agent_id="macro-research-agent",
    task_id="r7-test-root",
    trace_id="r7-test-trace",
)


def evidence(provider, series_id, label, unit, as_of, values):
    history = []
    if provider == "BLS":
        for year, month, value in values:
            history.append(
                {
                    "year": year,
                    "month": month,
                    "period_key": f"{year:04d}-{month:02d}",
                    "value": value,
                }
            )
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
            "uri": "https://example.invalid/r7-test",
        },
    }


def bls(series_id, label):
    return evidence(
        "BLS",
        series_id,
        label,
        "index_level",
        "2026-08",
        [(2025, 7, 100.0), (2025, 8, 100.2), (2026, 7, 102.8), (2026, 8, 103.2)],
    )


def fred(series_id, label, unit):
    return evidence(
        "FRED",
        series_id,
        label,
        unit,
        "2026-08-28",
        [("2026-08-27", 2.35), ("2026-08-28", 2.40)],
    )


def eia(series_id, label, unit):
    return evidence(
        "EIA",
        series_id,
        label,
        unit,
        "2026-08-24",
        [("2026-08-17", 3.20), ("2026-08-24", 3.25)],
    )


def research_synthesis(*, contradiction=False):
    relations = []
    relation_summary = {"agreement": 0, "mixed_signal": 1, "contradiction": 0}
    if contradiction:
        relations = [
            {
                "relation": "CONTRADICTION",
                "claim_key": "breakeven_5y",
                "evidence_ids": ["FRED:T5YIE"],
            }
        ]
        relation_summary["contradiction"] = 1
    return {
        "kind": "synthesis",
        "answer": "grounded",
        "confidence": 0.82,
        "confidence_type": "heuristic_support_score_not_probability",
        "evidence_ids": ["FRED:T5YIE", "EIA:GAS"],
        "signals": [
            {
                "evidence_id": "FRED:T5YIE",
                "kind": "change",
                "latest_value": 2.40,
                "direction": "rising",
            },
            {
                "evidence_id": "EIA:GAS",
                "kind": "change",
                "latest_value": 3.25,
                "direction": "falling",
            },
        ],
        "freshness": {
            "FRED:T5YIE": {"as_of": "2026-08-28", "status": "fresh", "age_days": 1},
            "EIA:GAS": {"as_of": "2026-08-24", "status": "fresh", "age_days": 5},
        },
        "quality": {
            "evidence_quality": [
                {"evidence_id": "FRED:T5YIE", "quality_score": 0.95},
                {"evidence_id": "EIA:GAS", "quality_score": 0.90},
            ],
            "relations": relations,
            "relation_summary": relation_summary,
        },
    }


def domain_brief():
    return {
        "kind": "synthesis",
        "domain": "investment",
        "confidence": 0.82,
        "confidence_type": "heuristic_support_score_not_probability",
        "evidence_ids": ["FRED:T5YIE", "EIA:GAS"],
        "decision_status": "MONITOR_MIXED_SIGNAL",
    }


class R7ForecastUnitTests(unittest.TestCase):
    def test_forecast_pack_is_falsifiable_and_non_probabilistic(self):
        pack = create_forecast_pack(
            "Assess inflation pressure.",
            "investment",
            research_synthesis(),
            domain_brief(),
            "2026-08-29",
        )
        self.assertEqual(pack["artifact_type"], "forecast_pack")
        self.assertEqual(pack["scoreboard"]["open"], 2)
        self.assertEqual(pack["guardrails"]["forecast_probability"], "not_provided")
        self.assertTrue(pack["pack_id"].startswith("FP-"))
        for row in pack["forecasts"]:
            self.assertEqual(row["status"], "OPEN")
            self.assertGreater(row["horizon_days"], 0)
            self.assertIn(row["expected_direction"], {"rising", "falling", "flat"})
            self.assertEqual(row["support_score_type"], "heuristic_support_score_not_probability")

    def test_same_claim_contradiction_forces_abstention(self):
        pack = create_forecast_pack(
            "Assess inflation pressure.",
            "investment",
            research_synthesis(contradiction=True),
            domain_brief(),
            "2026-08-29",
        )
        fred_row = next(item for item in pack["forecasts"] if item["target_evidence_id"] == "FRED:T5YIE")
        self.assertEqual(fred_row["status"], "ABSTAINED")
        self.assertEqual(fred_row["abstain_reason"], "same_claim_contradiction")

    def test_pre_due_reversal_flags_invalidation_without_resolving(self):
        pack = create_forecast_pack(
            "Assess inflation pressure.", "investment", research_synthesis(), domain_brief(), "2026-08-29"
        )
        current = research_synthesis()
        current["signals"][0]["latest_value"] = 2.30
        current["signals"][0]["direction"] = "falling"
        current["freshness"]["FRED:T5YIE"]["as_of"] = "2026-08-31"
        updated = evaluate_forecast_pack(pack, current, "2026-09-01")
        fred_row = next(item for item in updated["forecasts"] if item["target_evidence_id"] == "FRED:T5YIE")
        self.assertEqual(fred_row["status"], "OPEN")
        self.assertEqual(fred_row["evaluation"]["status"], "PENDING_NOT_DUE")
        self.assertTrue(fred_row["evaluation"]["invalidation_triggered"])
        self.assertTrue(updated["revision"]["required"])

    def test_due_forecasts_resolve_only_with_new_observations(self):
        pack = create_forecast_pack(
            "Assess inflation pressure.", "investment", research_synthesis(), domain_brief(), "2026-08-29"
        )
        unchanged = evaluate_forecast_pack(pack, research_synthesis(), "2026-09-20")
        self.assertTrue(
            all(
                (item.get("evaluation") or {}).get("status") == "AWAITING_NEW_OBSERVATION"
                for item in unchanged["forecasts"]
            )
        )

        current = research_synthesis()
        current["signals"][0]["latest_value"] = 2.50
        current["signals"][0]["direction"] = "rising"
        current["signals"][1]["latest_value"] = 3.10
        current["signals"][1]["direction"] = "falling"
        current["freshness"]["FRED:T5YIE"]["as_of"] = "2026-09-18"
        current["freshness"]["EIA:GAS"]["as_of"] = "2026-09-14"
        resolved = evaluate_forecast_pack(pack, current, "2026-09-20")
        self.assertEqual(resolved["scoreboard"]["resolved"], 2)
        self.assertEqual(resolved["scoreboard"]["hits"], 2)
        self.assertEqual(resolved["scoreboard"]["directional_accuracy"], 1.0)
        self.assertEqual(
            resolved["scoreboard"]["accuracy_type"],
            "historical_direction_hit_rate_not_probability",
        )

    def test_forecast_store_round_trips_pack(self):
        pack = create_forecast_pack(
            "Assess inflation pressure.", "investment", research_synthesis(), domain_brief(), "2026-08-29"
        )
        with tempfile.TemporaryDirectory() as directory:
            store = JsonForecastStore(directory)
            path = store.save(pack)
            self.assertTrue(path.exists())
            self.assertEqual(store.list_ids(), [pack["pack_id"]])
            loaded = store.load(pack["pack_id"])
            self.assertEqual(loaded["pack_id"], pack["pack_id"])
            self.assertEqual(loaded["forecasts"], pack["forecasts"])


class R7IntegrationTests(unittest.TestCase):
    def setUp(self):
        register_r7_tools()
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
        blueprint, plan = R7ResearchPlanner().build(
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

    def test_investment_r7_dag_and_evals(self):
        blueprint, result = self._run("investment")
        self.assertTrue(result["ok"], result.get("error"))
        self.assertEqual(
            [item["task_id"] for item in result["plan"]["tasks"]],
            ["Q1", "Q2", "Q3", "Q4", "S1", "D1", "F1"],
        )
        self.assertEqual(result["final_artifact"]["artifact_type"], "forecast_pack")
        self.assertEqual(len(result["citations"]), 4)
        self.assertEqual(result["results"]["F1"]["evidence_ids"], result["results"]["S1"]["evidence_ids"])
        suite = make_r7_eval_suite(blueprint.to_dict(), result, "investment")
        self.assertEqual(suite["passed"], 4, suite)
        self.assertEqual(suite["total"], 4)

    def test_policy_uses_same_source_evidence_and_forecast_targets(self):
        investment_blueprint, investment_result = self._run("investment")
        policy_blueprint, policy_result = self._run("policy")
        self.assertEqual(investment_blueprint.to_dict()["queries"], policy_blueprint.to_dict()["queries"])
        self.assertEqual(
            investment_result["results"]["S1"]["evidence_ids"],
            policy_result["results"]["S1"]["evidence_ids"],
        )
        self.assertEqual(
            [item["target_evidence_id"] for item in investment_result["results"]["F1"]["forecasts"]],
            [item["target_evidence_id"] for item in policy_result["results"]["F1"]["forecasts"]],
        )
        suite = make_r7_eval_suite(policy_blueprint.to_dict(), policy_result, "policy")
        self.assertEqual(suite["passed"], 4, suite)


if __name__ == "__main__":
    unittest.main()
