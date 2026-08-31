import unittest
from unittest.mock import patch

from rate_agent import RateStrategyAgent, RateToolExecutionError
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

    def test_transient_data_tool_failure_is_retried_and_traced(self):
        attempts = 0

        def flaky_history(**_kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise ConnectionError("FRED DGS2 connection failed: RemoteDisconnected")
            return completed_steepener_history()

        with patch("rate_agent.time.sleep") as mocked_sleep:
            run = RateStrategyAgent(
                tool_overrides={"fetch_public_rate_history": flaky_history}
            ).run_once()

        self.assertEqual(attempts, 2)
        self.assertEqual(len(run["trace"]), 21)
        self.assertIn("tool_execution_failed", [row["event"] for row in run["trace"]])
        retry = next(row for row in run["trace"] if row["event"] == "tool_retry_scheduled")
        self.assertEqual(retry["task_id"], "D1")
        self.assertEqual(retry["next_attempt"], 2)
        self.assertEqual(retry["delay_ms"], 250)
        mocked_sleep.assert_called_once_with(0.25)
        self.assertIn("fetch_public_rate_history", TOOL_REGISTRY)
        self.assertIn("simulate_one_curve_trade", TOOL_REGISTRY)
        self.assertFalse(run["guardrails"]["automatic_execution"])

    def test_exhausted_retries_preserve_the_failure_trace(self):
        attempts = 0

        def disconnected(**_kwargs):
            nonlocal attempts
            attempts += 1
            raise ConnectionError("FRED DGS2 connection failed: RemoteDisconnected")

        with patch("rate_agent.time.sleep"), self.assertRaises(
            RateToolExecutionError
        ) as raised:
            RateStrategyAgent(
                tool_overrides={"fetch_public_rate_history": disconnected}
            ).run_once()

        self.assertEqual(attempts, 3)
        self.assertTrue(raised.exception.transient)
        self.assertEqual(raised.exception.task_id, "D1")
        self.assertEqual(raised.exception.attempts, 3)
        self.assertEqual(raised.exception.trace[-1]["event"], "tool_execution_failed")
        self.assertFalse(raised.exception.trace[-1]["retryable"])

    def test_tool_arguments_are_validated_before_execution(self):
        agent = RateStrategyAgent(
            {"fetch_public_rate_history": lambda start_date: completed_steepener_history()}
        )
        with self.assertRaisesRegex(ValueError, "lookback_days"):
            agent.run_once(lookback_days=10)


if __name__ == "__main__":
    unittest.main()
