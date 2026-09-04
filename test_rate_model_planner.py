from copy import deepcopy
import json
import unittest

from rate_model_planner import (SAFE_RATE_TASKS, ModelPlanParseError,
                                ModelPlanRejected, ScriptedRatePlanModel,
                                build_plan_prompt, parse_plan_proposal,
                                validate_plan_proposal)
from rate_parallel import ParallelRunError, RateParallelAgent


class ModelPlanContractTests(unittest.TestCase):
    def valid_proposal(self):
        return {
            "goal": "one auditable 2s10s paper simulation",
            "tasks": deepcopy(SAFE_RATE_TASKS),
            "claims": {"paper_only": True, "automatic_execution": False},
        }

    def test_prompt_discloses_proposal_only_authority_and_allowed_tools(self):
        prompt = build_plan_prompt("test goal", {"fetch", "simulate"})
        self.assertEqual(prompt["authority"], "proposal_only_runtime_must_validate")
        self.assertEqual(prompt["allowed_tools"], ["fetch", "simulate"])
        self.assertNotIn("credentials", json.dumps(prompt).lower())

    def test_parser_rejects_malformed_or_non_object_output(self):
        for raw in ('{"tasks":[', '[]', 'null'):
            with self.subTest(raw=raw), self.assertRaises(ModelPlanParseError):
                parse_plan_proposal(raw)

    def test_validator_accepts_only_the_registered_paper_template(self):
        allowed = {task["tool_name"] for task in SAFE_RATE_TASKS}
        result = validate_plan_proposal(self.valid_proposal(), allowed_tools=allowed)
        self.assertTrue(result["accepted"])
        self.assertTrue(all(result["checks"].values()))

    def test_unknown_real_order_tool_is_rejected_even_when_json_is_valid(self):
        proposal = self.valid_proposal()
        proposal["tasks"].append({"task_id": "X1", "tool_name": "place_real_order", "depends_on": ["S1"]})
        proposal["claims"]["automatic_execution"] = True
        with self.assertRaises(ModelPlanRejected) as caught:
            validate_plan_proposal(proposal, allowed_tools={task["tool_name"] for task in SAFE_RATE_TASKS})
        self.assertTrue(any("allowlist" in reason for reason in caught.exception.reasons))
        self.assertTrue(any("paper_only" in reason for reason in caught.exception.reasons))

    def test_cycle_and_unknown_dependency_are_runtime_validation_failures(self):
        proposal = self.valid_proposal()
        proposal["tasks"][0]["depends_on"] = ["S1"]
        proposal["tasks"][1]["depends_on"] = ["MISSING"]
        with self.assertRaises(ModelPlanRejected) as caught:
            validate_plan_proposal(proposal, allowed_tools={task["tool_name"] for task in SAFE_RATE_TASKS})
        self.assertTrue(any("unknown dependencies" in reason for reason in caught.exception.reasons))
        self.assertTrue(any("acyclic" in reason for reason in caught.exception.reasons))

    def test_scripted_adapter_is_explicitly_not_a_real_llm(self):
        model = ScriptedRatePlanModel("model_valid")
        self.assertFalse(model.is_real_llm)
        self.assertEqual(parse_plan_proposal(model.complete({}))["tasks"], SAFE_RATE_TASKS)


class ModelPlannerIntegrationTests(unittest.TestCase):
    def agent(self):
        return RateParallelAgent(sleeper=lambda _: None)

    def test_valid_model_proposal_is_validated_before_any_tool_call(self):
        run = self.agent().run_once(demo_scenario="model_valid")
        events = run["trace"]
        accepted = next(e["sequence"] for e in events if e["event"] == "model_plan_accepted")
        first_tool = next(e["sequence"] for e in events if e["event"] == "tool_execution_started")
        self.assertLess(accepted, first_tool)
        self.assertEqual(run["architecture"]["planner"], "validated_model_proposal")
        self.assertFalse(run["architecture"]["model_is_real_llm"])
        self.assertEqual(run["lesson"]["topic"], "model_planner_authority")
        self.assertTrue(run["eval"]["passed"])

    def test_malformed_output_gets_exactly_one_format_repair(self):
        run = self.agent().run_once(demo_scenario="model_repair")
        events = run["trace"]
        self.assertEqual(sum(e["event"] == "model_request_started" for e in events), 2)
        self.assertEqual(sum(e["event"] == "plan_parse_failed" for e in events), 1)
        self.assertEqual(sum(e["event"] == "model_repair_requested" for e in events), 1)
        self.assertEqual(sum(e["event"] == "model_plan_accepted" for e in events), 1)
        self.assertTrue(run["eval"]["passed"])

    def test_unsafe_model_plan_abstains_before_any_tool_execution(self):
        with self.assertRaises(ParallelRunError) as caught:
            self.agent().run_once(demo_scenario="model_unsafe")
        self.assertEqual(caught.exception.code, "MODEL_PLAN_REJECTED")
        events = caught.exception.trace
        rejected = next(e for e in events if e["event"] == "model_plan_rejected")
        self.assertEqual(rejected["decision"], "ABSTAIN")
        self.assertTrue(any("place_real_order" in reason for reason in rejected["reasons"]))
        self.assertFalse(any(e["event"] == "tool_execution_started" for e in events))


if __name__ == "__main__":
    unittest.main()
