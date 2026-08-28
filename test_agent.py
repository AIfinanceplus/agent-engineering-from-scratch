import unittest

from agent import calculator, run_agent
from model_adapters import FakeModel
from model_validation import validate_model_response
from tools import resolve_tool, validate_tool_arguments


class AgentV2Tests(unittest.TestCase):
    def test_calculator_add(self):
        self.assertEqual(calculator(10, 20, "add"), 30)

    def test_calculator_multiply(self):
        self.assertEqual(calculator(6, 7, "multiply"), 42)

    def test_agent_completes_valid_tool_loop(self):
        self.assertEqual(
            run_agent("Please calculate 10 + 20.", model=FakeModel("success")),
            "The result is 30.",
        )

    def test_registry_resolves_known_tool(self):
        self.assertIs(resolve_tool("calculator"), calculator)

    def test_registry_returns_none_for_unknown_tool(self):
        self.assertIsNone(resolve_tool("weather_machine"))

    def test_unknown_tool_becomes_observation_instead_of_crash(self):
        answer = run_agent("test", model=FakeModel("unknown_tool"))
        self.assertIn("unknown_tool", answer)
        self.assertIn("Unknown tool", answer)

    def test_missing_argument_is_rejected_before_execution(self):
        answer = run_agent("test", model=FakeModel("missing_argument"))
        self.assertIn("missing_arguments", answer)
        self.assertIn("b", answer)

    def test_invalid_operation_is_rejected_before_execution(self):
        answer = run_agent("test", model=FakeModel("invalid_operation"))
        self.assertIn("invalid_argument_value", answer)
        self.assertIn("add", answer)

    def test_tool_validator_accepts_valid_arguments(self):
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
        event_types = [event["type"] for event in events]
        self.assertIn("model_validation", event_types)
        self.assertIn("runtime_stop", event_types)
        self.assertNotIn("tool_lookup", event_types)
        self.assertNotIn("tool_execute", event_types)

    def test_max_steps_stops_loop_before_next_tool_execution(self):
        events = []
        answer = run_agent(
            "loop forever",
            model=FakeModel("infinite_loop"),
            on_event=events.append,
            max_steps=3,
        )

        self.assertIn("max_steps_exceeded", answer)
        tool_executes = [event for event in events if event["type"] == "tool_execute"]
        runtime_steps = [event for event in events if event["type"] == "runtime_step"]
        stops = [event for event in events if event["type"] == "runtime_stop"]

        self.assertEqual(len(tool_executes), 3)
        self.assertEqual([event["step"] for event in runtime_steps], [1, 2, 3])
        self.assertEqual(stops[-1]["reason"], "max_steps")
        self.assertEqual(stops[-1]["step"], 3)

    def test_max_steps_must_be_positive_integer(self):
        with self.assertRaises(ValueError):
            run_agent("test", model=FakeModel("success"), max_steps=0)


if __name__ == "__main__":
    unittest.main()
