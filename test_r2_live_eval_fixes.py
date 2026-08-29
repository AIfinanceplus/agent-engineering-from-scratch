import json
import unittest

from context import ExecutionContext
from live_preflight import live_source_preflight
from r2_evals import EXPECTED_EVIDENCE_IDS, EXPECTED_TASK_IDS, run_r2_eval_suite
from r2_tooling import register_r2_tools


CONTEXT = ExecutionContext(
    tenant_id="demo-tenant",
    user_id="user-123",
    agent_id="macro-research-agent",
    task_id="r2-fix-test-root",
    trace_id="r2-fix-test-trace",
)


class LivePreflightTests(unittest.TestCase):
    def test_missing_live_keys_are_reported_before_runtime(self):
        result = live_source_preflight(env={})
        self.assertFalse(result["ready"])
        by_provider = {item["provider"]: item for item in result["sources"]}
        self.assertTrue(by_provider["BLS"]["ready"])
        self.assertFalse(by_provider["FRED"]["ready"])
        self.assertFalse(by_provider["EIA"]["ready"])
        self.assertEqual(result["missing_env"], ["FRED_API_KEY", "EIA_API_KEY"])
        self.assertEqual(
            result["setup"],
            ['export FRED_API_KEY="..."', 'export EIA_API_KEY="..."'],
        )

    def test_preflight_never_returns_secret_values(self):
        result = live_source_preflight(
            env={
                "FRED_API_KEY": "fred-secret-value",
                "EIA_API_KEY": "eia-secret-value",
            }
        )
        self.assertTrue(result["ready"])
        payload = json.dumps(result)
        self.assertNotIn("fred-secret-value", payload)
        self.assertNotIn("eia-secret-value", payload)
        self.assertNotIn("api_key=", payload.lower())
        self.assertEqual(result["missing_env"], [])


class R2EvalUpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        register_r2_tools()

    def test_visible_eval_suite_runs_r2_task_contract(self):
        suite = run_r2_eval_suite(execution_context=CONTEXT)
        self.assertEqual(suite["suite_id"], "r2-multi-source-macro")
        self.assertEqual(suite["passed"], 2)
        self.assertEqual(suite["total"], 2)
        self.assertEqual(suite["pass_rate"], 1.0)

        for entry in suite["cases"]:
            process = entry["process"]
            self.assertEqual(process[0]["type"], "eval_case_started")
            self.assertEqual(process[1]["type"], "eval_agent_run_completed")
            self.assertEqual(process[-1]["type"], "eval_case_verdict")
            self.assertTrue(process[-1]["passed"])
            self.assertEqual(
                process[0]["expectations"]["task_ids"],
                list(EXPECTED_TASK_IDS),
            )
            self.assertEqual(
                process[0]["expectations"]["evidence_ids"],
                list(EXPECTED_EVIDENCE_IDS),
            )
            self.assertNotIn("E1", json.dumps(process[0]["expectations"]))
            self.assertNotIn("E2", json.dumps(process[0]["expectations"]))

    def test_r2_eval_checks_lineage_freshness_and_causal_guardrail(self):
        suite = run_r2_eval_suite(execution_context=CONTEXT)
        required_checks = {
            "success",
            "task_contract",
            "evidence_contract",
            "provider_coverage",
            "citation_completeness",
            "citations_grounded",
            "freshness_complete",
            "all_nonstale",
            "tool_attempts",
            "causal_guardrail",
        }
        for entry in suite["cases"]:
            checks = entry["report"]["checks"]
            self.assertEqual({check["check_id"] for check in checks}, required_checks)
            self.assertTrue(all(check["passed"] for check in checks))
            self.assertEqual(entry["report"]["trace_metrics"]["tool_attempts"], 5)


if __name__ == "__main__":
    unittest.main()
