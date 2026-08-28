import unittest

from agent import calculator, run_agent
from model_adapters import FakeModel
from model_validation import validate_model_response
from policy import PolicyDecision, PolicyEngine
from tools import (
    CALCULATOR_TOOL,
    DELETE_RECORD_TOOL,
    FLAKY_CALCULATOR_TOOL,
    SEND_MESSAGE_TOOL,
    Tool,
    model_tool_schemas,
    reset_teaching_tools,
    resolve_tool,
    validate_tool_arguments,
)


class AgentV5Tests(unittest.TestCase):
    def setUp(self):
        reset_teaching_tools()

    def test_calculator_add(self):
        self.assertEqual(calculator(10, 20, "add"), 30)

    def test_agent_completes_valid_tool_loop(self):
        self.assertEqual(
            run_agent("Please calculate 10 + 20.", model=FakeModel("success")),
            "The result is 30.",
        )

    def test_registry_resolves_complete_tool_object(self):
        tool = resolve_tool("calculator")
        self.assertIsInstance(tool, Tool)
        self.assertIs(tool.function, calculator)
        self.assertEqual(tool.name, "calculator")
        self.assertEqual(tool.max_retries, 0)
        self.assertEqual(tool.risk, "low")

    def test_model_schema_is_generated_from_same_tool_object(self):
        schemas = model_tool_schemas()
        calculator_schema = next(item for item in schemas if item["name"] == "calculator")
        self.assertEqual(calculator_schema, CALCULATOR_TOOL.to_model_schema())
        self.assertIs(calculator_schema["parameters"], CALCULATOR_TOOL.parameters)

    def test_flaky_tool_owns_retry_policy(self):
        self.assertEqual(FLAKY_CALCULATOR_TOOL.max_retries, 2)
        self.assertIn(TimeoutError, FLAKY_CALCULATOR_TOOL.retryable_errors)

    def test_policy_engine_interprets_tool_risk(self):
        policy = PolicyEngine()
        self.assertIs(
            policy.evaluate(CALCULATOR_TOOL, {}).decision,
            PolicyDecision.ALLOW,
        )
        self.assertIs(
            policy.evaluate(SEND_MESSAGE_TOOL, {}).decision,
            PolicyDecision.REQUIRE_APPROVAL,
        )
        self.assertIs(
            policy.evaluate(DELETE_RECORD_TOOL, {}).decision,
            PolicyDecision.DENY,
        )

    def test_low_risk_tool_is_allowed_and_executes(self):
        events = []
        answer = run_agent(
            "allow low-risk tool",
            model=FakeModel("policy_allow"),
            on_event=events.append,
        )

        self.assertEqual(answer, "The result is 17.")
        decision = next(event for event in events if event["type"] == "policy_decision")
        self.assertEqual(decision["tool_risk"], "low")
        self.assertEqual(decision["policy"]["decision"], "allow")
        self.assertIn("tool_attempt", [event["type"] for event in events])

    def test_medium_risk_tool_requires_approval_and_does_not_execute(self):
        events = []
        answer = run_agent(
            "send a message",
            model=FakeModel("policy_approval"),
            on_event=events.append,
        )

        self.assertIn("approval_required", answer)
        decision = next(event for event in events if event["type"] == "policy_decision")
        self.assertEqual(decision["tool_risk"], "medium")
        self.assertEqual(decision["policy"]["decision"], "require_approval")
        self.assertNotIn("tool_attempt", [event["type"] for event in events])
        rejection = next(
            event
            for event in events
            if event["type"] == "tool_rejected"
            and event.get("reason") == "require_approval"
        )
        self.assertEqual(rejection["error"]["code"], "approval_required")

    def test_high_risk_tool_is_denied_and_does_not_execute(self):
        events = []
        answer = run_agent(
            "delete record",
            model=FakeModel("policy_deny"),
            on_event=events.append,
        )

        self.assertIn("policy_denied", answer)
        decision = next(event for event in events if event["type"] == "policy_decision")
        self.assertEqual(decision["tool_risk"], "high")
        self.assertEqual(decision["policy"]["decision"], "deny")
        self.assertNotIn("tool_attempt", [event["type"] for event in events])

    def test_unknown_tool_becomes_observation_instead_of_crash(self):
        answer = run_agent("test", model=FakeModel("unknown_tool"))
        self.assertIn("unknown_tool", answer)

    def test_missing_argument_is_rejected_before_policy(self):
        events = []
        answer = run_agent(
            "test",
            model=FakeModel("missing_argument"),
            on_event=events.append,
        )
        self.assertIn("missing_arguments", answer)
        self.assertNotIn("policy_decision", [event["type"] for event in events])

    def test_invalid_operation_is_rejected_from_tool_schema(self):
        answer = run_agent("test", model=FakeModel("invalid_operation"))
        self.assertIn("invalid_argument_value", answer)

    def test_compatibility_validator_reads_tool_object(self):
        result = validate_tool_arguments(
            "calculator",
            {"a": 1, "b": 2, "operation": "add"},
        )
        self.assertEqual(result, {"ok": True})

    def test_model_response_validator_accepts_final(self):
        self.assertEqual(
            validate_model_response({"type": "final", "content": "done"}),
            {"ok": True},
        )

    def test_malformed_model_response_stops_before_tool_boundary(self):
        events = []
        answer = run_agent(
            "test",
            model=FakeModel("malformed_response"),
            on_event=events.append,
        )
        self.assertIn("invalid_tool_call", answer)
        self.assertNotIn("tool_lookup", [event["type"] for event in events])

    def test_max_steps_stops_non_duplicate_loop(self):
        events = []
        answer = run_agent(
            "loop forever",
            model=FakeModel("infinite_loop"),
            on_event=events.append,
            max_steps=3,
        )
        self.assertIn("max_steps_exceeded", answer)
        self.assertEqual(
            len([event for event in events if event["type"] == "tool_attempt"]),
            3,
        )

    def test_transient_timeout_uses_tool_owned_retry_policy(self):
        events = []
        answer = run_agent(
            "retry transient failure",
            model=FakeModel("retry_success"),
            on_event=events.append,
        )
        self.assertEqual(answer, "The result is 42.")
        attempts = [event for event in events if event["type"] == "tool_attempt"]
        execute = next(event for event in events if event["type"] == "tool_execute")
        self.assertEqual([event["attempt"] for event in attempts], [1, 2])
        self.assertEqual(execute["retry_policy_source"], "Tool.max_retries")
        self.assertEqual(execute["effective_max_retries"], 2)

    def test_exact_duplicate_model_call_is_blocked_before_second_execution(self):
        events = []
        answer = run_agent(
            "repeat the same thing",
            model=FakeModel("duplicate_loop"),
            on_event=events.append,
        )
        self.assertIn("duplicate_tool_call", answer)
        attempts = [event for event in events if event["type"] == "tool_attempt"]
        self.assertEqual(len(attempts), 1)


if __name__ == "__main__":
    unittest.main()
