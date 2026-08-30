import copy
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

from r12_agent import (
    JsonR12StrategyRunStore,
    R12SimulatedOrchestratorCrash,
    R12StrategyAgent,
    R12StrategyPlanner,
    evaluate_r12_strategy_agent_run,
)
from r12_tooling import R12_MARKET_CONTRACT_TOOL, register_r12_tools
from test_r12_execution import execution_contracts, explicit_zero_fee_model
from test_r12_identity import full_attestation
from tools import TOOL_REGISTRY


class R12StrategyAgentTests(unittest.TestCase):
    def setUp(self):
        register_r12_tools()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = JsonR12StrategyRunStore(self.temp.name)
        self.agent = R12StrategyAgent(self.store)
        self.kalshi, self.poly = execution_contracts()
        self.fetch_calls = []

    def fake_fetch(self, provider, identifier):
        self.fetch_calls.append((provider, identifier))
        if provider == "kalshi":
            return copy.deepcopy(self.kalshi)
        if provider == "polymarket":
            return copy.deepcopy(self.poly)
        raise ValueError("unexpected provider")

    def tool_patch(self):
        fake_tool = replace(R12_MARKET_CONTRACT_TOOL, function=self.fake_fetch)
        return patch.dict(TOOL_REGISTRY, {R12_MARKET_CONTRACT_TOOL.name: fake_tool})

    def start(self, **overrides):
        payload = {
            "kalshi_identifier": self.kalshi["provider_market_id"],
            "polymarket_identifier": self.poly["provider_market_id"],
            "target_contracts": 10,
            "fee_model": explicit_zero_fee_model(),
            "latency_buffer_bps": 0,
            "estimated_total_cost_per_basket": 0,
        }
        payload.update(overrides)
        return self.agent.start_exact_pair(**payload)

    def test_planner_has_explicit_human_gate_before_identity_and_quotes(self):
        plan = R12StrategyPlanner().plan_exact_pair(
            kalshi_identifier="K-1",
            polymarket_identifier="P-1",
            target_contracts=10,
            fee_model=explicit_zero_fee_model(),
        )
        rows = {row.task_id: row for row in plan.tasks}
        self.assertEqual(rows["H1"].tool_name, "human_identity_approval_boundary")
        self.assertEqual(rows["H1"].depends_on, ["R1"])
        self.assertIn("H1", rows["I1"].depends_on)
        self.assertEqual(rows["V1"].depends_on, ["I1"])
        self.assertEqual(rows["E1"].depends_on, ["I1"])

    def test_run_executes_tools_through_runtime_then_pauses_before_identity(self):
        with self.tool_patch():
            run = self.start(run_id="R12A-WAIT")

        self.assertEqual(run["status"], "WAITING_HUMAN_IDENTITY_APPROVAL")
        self.assertEqual(set(run["results"]), {"K1", "P1", "R1"})
        self.assertNotIn("H1", run["results"])
        self.assertNotIn("I1", run["results"])
        self.assertEqual(run["next_task_id"], "H1")
        self.assertEqual(len(self.fetch_calls), 2)
        self.assertEqual(set(run["task_traces"]), {"K1", "P1", "R1"})
        self.assertTrue(all(trace["metrics"]["tool_attempts"] == 1 for trace in run["task_traces"].values()))
        self.assertTrue(evaluate_r12_strategy_agent_run(run)["passed"])

    def test_human_approval_resumes_identity_rv_and_depth_quote(self):
        with self.tool_patch():
            waiting = self.start(run_id="R12A-COMPLETE")
            completed = self.agent.approve_and_resume(waiting["run_id"], full_attestation())

        self.assertEqual(completed["status"], "COMPLETED_PAPER_QUOTE")
        self.assertEqual(set(completed["results"]), {"K1", "P1", "R1", "H1", "I1", "V1", "E1"})
        self.assertTrue(completed["results"]["I1"]["settlement_compatible_for_rv"])
        self.assertEqual(completed["results"]["E1"]["paper_signal_count"], 1)
        self.assertFalse(completed["results"]["H1"]["parser_checked_boxes"])
        self.assertEqual(
            completed["results"]["H1"]["rules_analysis_id"],
            completed["results"]["R1"]["analysis_id"],
        )
        self.assertEqual(completed["final_artifact"]["artifact_type"], "r12_execution_quality_scan")
        self.assertTrue(evaluate_r12_strategy_agent_run(completed)["passed"])

    def test_incomplete_human_attestation_cannot_resume(self):
        with self.tool_patch():
            waiting = self.start(run_id="R12A-INCOMPLETE")
            incomplete = full_attestation()
            incomplete["edge_cases_reviewed"] = False
            with self.assertRaisesRegex(ValueError, "all six identity checks"):
                self.agent.approve_and_resume(waiting["run_id"], incomplete)

        persisted = self.store.load(waiting["run_id"])
        self.assertEqual(persisted["status"], "WAITING_HUMAN_IDENTITY_APPROVAL")
        self.assertNotIn("H1", persisted["results"])

    def test_rules_blocker_stops_before_human_or_identity(self):
        self.poly["description"] = None
        self.poly["resolution"]["description"] = None
        with self.tool_patch():
            run = self.start(run_id="R12A-RULES-BLOCK")

        self.assertEqual(run["status"], "BLOCKED_RULES_ANALYSIS")
        self.assertEqual(set(run["results"]), {"K1", "P1", "R1"})
        self.assertFalse(run["results"]["R1"]["eligible_for_identity_review"])
        self.assertNotIn("H1", run["results"])
        self.assertNotIn("I1", run["results"])

    def test_resume_skips_durably_completed_tool_after_crash(self):
        with self.tool_patch():
            with self.assertRaises(R12SimulatedOrchestratorCrash):
                self.start(run_id="R12A-CRASH", crash_after_completed_tasks=1)
            self.assertEqual(self.fetch_calls.count(("kalshi", self.kalshi["provider_market_id"])), 1)
            resumed = self.agent.resume("R12A-CRASH")

        self.assertEqual(resumed["status"], "WAITING_HUMAN_IDENTITY_APPROVAL")
        self.assertEqual(self.fetch_calls.count(("kalshi", self.kalshi["provider_market_id"])), 1)
        self.assertEqual(self.fetch_calls.count(("polymarket", self.poly["provider_market_id"])), 1)
        self.assertTrue(any(row["boundary"] == "after_K1" for row in resumed["checkpoints"]))

    def test_invalid_execution_inputs_fail_before_any_market_tool_runs(self):
        with self.tool_patch():
            with self.assertRaisesRegex(ValueError, "target_contracts must be > 0"):
                self.start(run_id="R12A-BAD-INPUT", target_contracts=0)
        self.assertEqual(self.fetch_calls, [])

    def test_completed_run_is_idempotent_on_resume_or_reapproval(self):
        with self.tool_patch():
            waiting = self.start(run_id="R12A-IDEMPOTENT")
            completed = self.agent.approve_and_resume(waiting["run_id"], full_attestation())
            event_count = len(completed["events"])
            resumed = self.agent.resume(waiting["run_id"])
            reapproved = self.agent.approve_and_resume(waiting["run_id"], full_attestation())

        self.assertEqual(len(resumed["events"]), event_count)
        self.assertEqual(len(reapproved["events"]), event_count)
        self.assertEqual(resumed["results"]["E1"], completed["results"]["E1"])


if __name__ == "__main__":
    unittest.main()
