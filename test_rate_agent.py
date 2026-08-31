import unittest

from rate_agent import RateStrategyAgent
from test_rate_strategy import completed_steepener_history
from tools import TOOL_REGISTRY


class RateStrategyAgentTests(unittest.TestCase):
    def test_fixed_plan_crosses_registry_validation_and_completes_eval(self):
        calls = []

        def fetch(start_date):
            calls.append(start_date)
            return completed_steepener_history()

        agent = RateStrategyAgent({"fetch_public_rate_history": fetch})
        run = agent.run_once(start_date="2026-01-01")
        self.assertEqual(run["status"], "COMPLETED_ONE_PAPER_SIMULATION")
        self.assertEqual(calls, ["2026-01-01"])
        self.assertTrue(run["eval"]["passed"])
        self.assertEqual([task["task_id"] for task in run["plan"]["tasks"]], ["D1", "S1"])
        self.assertEqual(run["plan"]["status"], "completed")
        self.assertEqual(run["architecture"]["model"], "none_deterministic_v1")
        self.assertEqual(len(run["trace"]), 18)
        self.assertEqual(run["trace"][0]["event"], "goal_received")
        self.assertEqual(run["trace"][-1]["event"], "run_completed")
        self.assertEqual([row["evidence_id"] for row in run["evidence"]], ["FRED:DGS2", "FRED:DGS10"])
        self.assertEqual(run["checkpoints"], [])
        self.assertIn("fetch_public_rate_history", TOOL_REGISTRY)
        self.assertIn("simulate_one_curve_trade", TOOL_REGISTRY)
        self.assertFalse(run["guardrails"]["automatic_execution"])

    def test_tool_arguments_are_validated_before_execution(self):
        agent = RateStrategyAgent(
            {"fetch_public_rate_history": lambda start_date: completed_steepener_history()}
        )
        with self.assertRaisesRegex(ValueError, "lookback_days"):
            agent.run_once(lookback_days=10)


if __name__ == "__main__":
    unittest.main()
