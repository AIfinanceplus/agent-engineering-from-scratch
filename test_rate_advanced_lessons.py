import json
import tempfile
import unittest

from rate_advanced_lessons import (ADVANCED_SCENARIOS, GOLDEN_BEHAVIOR,
                                   JsonlRateMemoryStore, ROLE_CONTRACTS,
                                   RateAdvancedLessons, evaluate_golden_trace,
                                   validate_handoff, _handoff)


class AdvancedRateLessonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.lessons = RateAdvancedLessons(JsonlRateMemoryStore(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def run_lesson(self, scenario):
        events = []
        result = self.lessons.run(scenario, f"TEST-{scenario}", events.append)
        self.assertEqual(events, result["trace"])
        self.assertEqual(result["trace"][-1]["event"], "run_completed")
        self.assertTrue(result["guardrails"]["paper_only"])
        self.assertFalse(result["guardrails"]["automatic_execution"])
        return result

    def test_all_teaching_scenarios_are_runnable(self):
        self.assertEqual(len(ADVANCED_SCENARIOS), 11)
        for scenario in sorted(ADVANCED_SCENARIOS):
            result = self.run_lesson(scenario)
            if scenario == "eval_regression_fail":
                self.assertFalse(result["eval"]["passed"])
            else:
                self.assertTrue(result["eval"]["passed"], scenario)

    def test_supervisor_keeps_orchestration_authority_separate_from_runtime(self):
        contract = ROLE_CONTRACTS["orchestration_supervisor"]
        self.assertIn("assign_task", contract["authority"])
        self.assertIn("execute_tool", contract["forbidden_actions"])
        result = self.run_lesson("orchestration_normal")
        actions = [row["action"] for row in result["trace"]
                   if row["event"] == "orchestration_decision_recorded"]
        self.assertEqual(actions, ["ASSIGN", "ASSIGN", "ASSIGN", "COMPLETE"])
        self.assertTrue(result["eval"]["checks"]["single_owner_preserved"])

    def test_supervisor_revision_is_bounded_and_revalidated(self):
        result = self.run_lesson("orchestration_revision")
        returns = [row for row in result["trace"]
                   if row["event"] == "task_returned_for_revision"]
        self.assertEqual(len(returns), 1)
        reviews = [row for row in result["trace"] if row["event"] == "risk_review_completed"]
        self.assertEqual([row["approved"] for row in reviews], [False, True])
        self.assertTrue(result["eval"]["checks"]["revision_then_approved"])

    def test_supervisor_revokes_timed_out_owner_before_reassignment(self):
        result = self.run_lesson("orchestration_timeout_reassign")
        names = [row["event"] for row in result["trace"]]
        self.assertLess(names.index("task_ownership_revoked"),
                        names.index("task_ownership_changed", names.index("task_ownership_revoked")))
        owners = [row["to_owner"] for row in result["trace"]
                  if row["event"] == "task_ownership_changed"]
        self.assertIn("analyst-worker-b", owners)

    def test_supervisor_stops_loop_and_authority_escalation_without_runtime(self):
        for scenario, guard_event in (("orchestration_loop_block", "orchestration_loop_detected"),
                                      ("orchestration_authority_block", "orchestration_authority_violation_detected")):
            result = self.run_lesson(scenario)
            self.assertIn(guard_event, [row["event"] for row in result["trace"]])
            self.assertFalse(any(row["event"] == "paper_runtime_mapped" for row in result["trace"]))
            stopped = next(row for row in result["trace"] if row["event"] == "orchestration_stopped")
            self.assertTrue(stopped["safe_stop"])
            self.assertEqual(stopped["effect_count"], 0)

    def test_golden_eval_compares_behavior_not_wording(self):
        candidate = {
            "events": [{"event": name} for name in GOLDEN_BEHAVIOR["required_order"]],
            "guardrails": dict(GOLDEN_BEHAVIOR["required_guardrails"]),
            "result_type": "paper_proposal",
            "arbitrary_model_wording": "Any prose is allowed",
        }
        self.assertTrue(evaluate_golden_trace(candidate)["passed"])
        candidate["events"].append({"event": "tool_call", "tool_name": "place_order"})
        failed = evaluate_golden_trace(candidate)
        self.assertFalse(failed["passed"])
        self.assertIn("forbidden_tool_absent", failed["regressions"])

    def test_memory_trace_and_disk_never_contain_raw_secrets(self):
        result = self.run_lesson("memory_redaction_pass")
        rendered = json.dumps(result, ensure_ascii=False)
        disk = (self.lessons.memory_store.path).read_text(encoding="utf-8")
        for secret in ("teaching-secret-token", "student@example.invalid"):
            self.assertNotIn(secret, rendered)
            self.assertNotIn(secret, disk)
        self.assertIn("[REDACTED]", disk)

    def test_privacy_block_has_zero_persistent_effect(self):
        result = self.run_lesson("memory_privacy_block")
        self.assertFalse(self.lessons.memory_store.path.exists())
        blocked = next(row for row in result["trace"] if row["event"] == "memory_write_blocked")
        self.assertEqual(blocked["effect_count"], 0)

    def test_role_contracts_define_authority_and_forbidden_actions(self):
        required = {"role_id", "mission", "inputs", "tools", "tasks", "outputs", "acceptance",
                    "kpi", "authority", "forbidden_actions", "handoff_rules", "budget_policy"}
        for contract in ROLE_CONTRACTS.values():
            self.assertEqual(set(contract), required)

    def test_handoff_rejects_tamper_and_authority_escalation(self):
        payload = {"evidence_ids": ["DGS2", "DGS10"],
                   "guardrails": {"paper_only": True, "automatic_execution": False}}
        envelope = _handoff("strategy_analyst", "risk_controller", payload)
        self.assertTrue(validate_handoff(envelope)["passed"])
        envelope["payload"]["guardrails"]["automatic_execution"] = True
        rejected = validate_handoff(envelope)
        self.assertFalse(rejected["passed"])
        self.assertIn("contract hash mismatch", rejected["reasons"])

    def test_handoff_trace_activates_all_roles_only_after_acceptance(self):
        passed = self.run_lesson("handoff_contract_pass")
        activations = [row["actor_role"] for row in passed["trace"]
                       if row["event"] == "agent_role_activated"]
        self.assertEqual(activations, ["strategy_analyst", "risk_controller", "runtime_supervisor"])

        rejected = self.run_lesson("handoff_contract_reject")
        activations = [row["actor_role"] for row in rejected["trace"]
                       if row["event"] == "agent_role_activated"]
        self.assertEqual(activations, ["strategy_analyst"])
        self.assertEqual(next(row for row in rejected["trace"]
                              if row["event"] == "handoff_rejected")["effect_count"], 0)


if __name__ == "__main__":
    unittest.main()
