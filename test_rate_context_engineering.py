import json
import unittest

from rate_context_engineering import (ContextBudgetExceeded, ContextBuilder,
                                      ContextItem, teaching_context_candidates)
from rate_parallel import RateParallelAgent


class ContextBuilderContractTests(unittest.TestCase):
    def test_relevance_policy_keeps_required_and_rate_context_only(self):
        pack = ContextBuilder(180).build(teaching_context_candidates("context_relevant"))
        self.assertEqual(pack["used_tokens"], 180)
        self.assertEqual([item["item_id"] for item in pack["selected_items"]],
                         ["policy", "current_goal", "tool_contracts", "latest_rate_result"])
        self.assertEqual(set(pack["excluded_item_ids"]), {"old_event_notes", "ui_preference"})
        reasons = {row["item_id"]: row.get("reason") for row in pack["decisions"]}
        self.assertEqual(reasons["old_event_notes"], "low_relevance")

    def test_long_history_is_compressed_to_fit_without_hiding_lossiness(self):
        candidates = teaching_context_candidates("context_compression")
        pack = ContextBuilder(150).build(candidates)
        history = next(item for item in pack["selected_items"] if item["item_id"] == "long_run_history")
        decision = next(row for row in pack["decisions"] if row["item_id"] == "long_run_history")
        self.assertEqual(history["mode"], "compressed")
        self.assertEqual((decision["full_tokens"], decision["used_tokens"]), (160, 40))
        self.assertEqual(pack["used_tokens"], pack["max_tokens"])
        self.assertNotIn("Long teaching history", json.dumps(pack["model_input"]))
        self.assertIn("Prior verified invariants", json.dumps(pack["model_input"]))

    def test_fresher_instruction_wins_before_token_selection(self):
        pack = ContextBuilder(180).build(teaching_context_candidates("context_conflict"))
        stale = next(row for row in pack["decisions"] if row["item_id"] == "stale_strategy_goal")
        self.assertEqual(stale["decision"], "dropped")
        self.assertEqual(stale["reason"], "superseded_by_fresher_authoritative_context")
        self.assertEqual(stale["winner"], "current_goal")
        model_input = json.dumps(pack["model_input"])
        self.assertIn("2s10s", model_input)
        self.assertNotIn("Kalshi", model_input)

    def test_mandatory_policy_never_silently_disappears(self):
        mandatory = ContextItem("policy", "system", "paper only", 30, 1, 1, 1, mandatory=True)
        with self.assertRaises(ContextBudgetExceeded):
            ContextBuilder(20).build([mandatory])

    def test_invalid_context_contracts_fail_closed(self):
        with self.assertRaises(ValueError):
            ContextBuilder(0)
        with self.assertRaises(ValueError):
            ContextItem("bad", "source", "text", 10, 1.1, 1, 1)
        with self.assertRaises(ValueError):
            ContextBuilder(20).build([])


class ContextEngineeringIntegrationTests(unittest.TestCase):
    def agent(self):
        return RateParallelAgent(sleeper=lambda _: None)

    def test_context_pack_is_created_before_the_only_model_request(self):
        run = self.agent().run_once(demo_scenario="context_compression")
        events = run["trace"]
        pack_event = next(event for event in events if event["event"] == "context_pack_created")
        request = next(event for event in events if event["event"] == "model_request_started")
        self.assertLess(pack_event["sequence"], request["sequence"])
        self.assertEqual(request["prompt"]["context_pack"], pack_event["context_pack"])
        self.assertEqual(sum(event["event"] == "model_request_started" for event in events), 1)
        self.assertTrue(run["eval"]["passed"])

    def test_all_context_scenarios_preserve_runtime_validation_and_paper_boundary(self):
        for scenario in ("context_relevant", "context_compression", "context_conflict"):
            with self.subTest(scenario=scenario):
                run = self.agent().run_once(demo_scenario=scenario)
                self.assertEqual(run["lesson"]["topic"], "context_engineering")
                self.assertIsNotNone(run["architecture"]["context_engineering"])
                self.assertTrue(any(event["event"] == "plan_validation_completed" and event["accepted"]
                                    for event in run["trace"]))
                self.assertTrue(run["guardrails"]["paper_only"])


if __name__ == "__main__":
    unittest.main()
