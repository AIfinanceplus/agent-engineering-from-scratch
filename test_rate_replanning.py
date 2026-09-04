import unittest

from rate_parallel import ParallelRunError, RateParallelAgent
from rate_replanning import (PlanRevisionGuard, ReplanBudgetExhausted,
                             ReplanLoopDetected, validate_rate_history_observation)


class PlanRevisionGuardTests(unittest.TestCase):
    def test_fingerprint_is_canonical_and_duplicate_plan_is_blocked(self):
        first = {"tool_name": "fetch", "arguments": {"start_date": "2024-01-01", "limit": 20}}
        reordered = {"arguments": {"limit": 20, "start_date": "2024-01-01"}, "tool_name": "fetch"}
        guard = PlanRevisionGuard(max_revisions=2)
        seeded = guard.seed(first)
        self.assertEqual(seeded["revision"], 0)
        self.assertEqual(seeded["remaining_revisions"], 2)
        self.assertEqual(guard.fingerprint(first), guard.fingerprint(reordered))
        with self.assertRaises(ReplanLoopDetected):
            guard.register(reordered)
        self.assertEqual(guard.snapshot()["used_revisions"], 0)

    def test_only_new_plans_spend_the_bounded_revision_budget(self):
        guard = PlanRevisionGuard(max_revisions=1)
        guard.seed({"arguments": {"start_date": "2025-01-01"}})
        accepted = guard.register({"arguments": {"start_date": "2023-01-01"}})
        self.assertEqual(accepted["revision"], 1)
        self.assertEqual(accepted["remaining_revisions"], 0)
        with self.assertRaises(ReplanBudgetExhausted):
            guard.register({"arguments": {"start_date": "2021-01-01"}})

    def test_observation_gate_requires_enough_history_for_strategy_and_holding_window(self):
        history = {"artifact_type": "rate_curve_history", "observations": [{}] * 80}
        rejected = validate_rate_history_observation(history, lookback_days=60, holding_days=20)
        self.assertFalse(rejected["passed"])
        self.assertEqual(rejected["minimum_required"], 81)
        history["observations"].append({})
        self.assertTrue(validate_rate_history_observation(history, lookback_days=60, holding_days=20)["passed"])


class ReplanningIntegrationTests(unittest.TestCase):
    def agent(self):
        return RateParallelAgent(sleeper=lambda _: None)

    def test_replan_success_invalidates_first_output_before_any_branch_and_completes(self):
        run = self.agent().run_once(demo_scenario="replan_success")
        events = run["trace"]
        calls = [e for e in events if e["event"] == "tool_execution_started" and e["task_id"] == "D1"]
        self.assertEqual(len(calls), 2)
        self.assertNotEqual(calls[0]["arguments"], calls[1]["arguments"])
        invalidated = next(e["sequence"] for e in events if e["event"] == "task_invalidated")
        revised = next(e["sequence"] for e in events if e["event"] == "plan_revised")
        second_call = calls[1]["sequence"]
        first_branch = min(e["sequence"] for e in events if e["event"] == "tool_execution_started" and e["task_id"] in {"A2", "A10"})
        self.assertLess(invalidated, revised)
        self.assertLess(revised, second_call)
        self.assertLess(second_call, first_branch)
        self.assertEqual([e["passed"] for e in events if e["event"] == "observation_validation_completed"], [False, True])
        self.assertTrue(run["eval"]["passed"])
        self.assertEqual(run["lesson"]["topic"], "bounded_replanning")
        self.assertEqual(run["architecture"]["replanning_guard"]["used_revisions"], 1)

    def test_repeated_plan_is_stopped_without_a_second_tool_call(self):
        with self.assertRaises(ParallelRunError) as caught:
            self.agent().run_once(demo_scenario="replan_loop")
        self.assertEqual(caught.exception.code, "REPLAN_LOOP_DETECTED")
        events = caught.exception.trace
        self.assertEqual(sum(e["event"] == "tool_execution_started" and e["task_id"] == "D1" for e in events), 1)
        self.assertTrue(any(e["event"] == "replan_loop_detected" and e["decision"] == "ABSTAIN" for e in events))
        self.assertFalse(any(e.get("task_id") in {"A2", "A10", "J1", "S1", "E1"} for e in events))

    def test_second_rejection_exhausts_budget_and_blocks_downstream(self):
        with self.assertRaises(ParallelRunError) as caught:
            self.agent().run_once(demo_scenario="replan_budget")
        self.assertEqual(caught.exception.code, "REPLAN_BUDGET_EXHAUSTED")
        events = caught.exception.trace
        self.assertEqual(sum(e["event"] == "tool_execution_started" and e["task_id"] == "D1" for e in events), 2)
        self.assertEqual(sum(e["event"] == "plan_revised" for e in events), 1)
        self.assertTrue(any(e["event"] == "replan_budget_exhausted" and e["decision"] == "ABSTAIN" for e in events))
        self.assertFalse(any(e.get("task_id") in {"A2", "A10", "J1", "S1", "E1"} for e in events))


if __name__ == "__main__":
    unittest.main()
