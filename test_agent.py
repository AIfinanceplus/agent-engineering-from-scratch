import unittest

from agent import calculator, run_agent
from model_adapters import FakeModel
from model_validation import validate_model_response
from tools import reset_teaching_tools, resolve_tool, validate_tool_arguments


class AgentV3Tests(unittest.TestCase):
    def setUp(self):
        # Keep the stateful retry teaching tool deterministic across tests.
        reset_teaching_tools()

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

    def test_max_steps_stops_non_duplicate_loop_before_next_tool_execution(self):
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
        duplicate_checks = [event for event in events if event["type"] == "duplicate_check"]
        stops = [event for event in events if event["type"] == "runtime_stop"]

        self.assertEqual(len(tool_executes), 3)
        self.assertEqual([event["step"] for event in runtime_steps], [1, 2, 3])
        self.assertTrue(all(not event["duplicate"] for event in duplicate_checks))
        self.assertEqual(stops[-1]["reason"], "max_steps")
        self.assertEqual(stops[-1]["step"], 3)

    def test_transient_timeout_retries_inside_one_model_step(self):
        events = []
        answer = run_agent(
            "retry transient failure",
            model=FakeModel("retry_success"),
            on_event=events.append,
            max_retries=2,
        )

        self.assertEqual(answer, "The result is 42.")
        runtime_steps = [event for event in events if event["type"] == "runtime_step"]
        attempts = [event for event in events if event["type"] == "tool_attempt"]
        retries = [event for event in events if event["type"] == "tool_retry"]
        results = [event for event in events if event["type"] == "tool_result"]

        self.assertEqual(len(runtime_steps), 1)
        self.assertEqual([event["attempt"] for event in attempts], [1, 2])
        self.assertEqual(len(retries), 1)
        self.assertEqual(retries[0]["error_type"], "TimeoutError")
        self.assertEqual(results[-1]["result"], 42)
        self.assertEqual(results[-1]["attempts"], 2)

    def test_retry_exhaustion_becomes_observation(self):
        events = []
        answer = run_agent(
            "do not retry",
            model=FakeModel("retry_success"),
            on_event=events.append,
            max_retries=0,
        )

        self.assertIn("tool_retry_exhausted", answer)
        attempts = [event for event in events if event["type"] == "tool_attempt"]
        retries = [event for event in events if event["type"] == "tool_retry"]
        errors = [event for event in events if event["type"] == "tool_error"]

        self.assertEqual(len(attempts), 1)
        self.assertEqual(retries, [])
        self.assertTrue(errors[-1]["retryable"])

    def test_exact_duplicate_model_call_is_blocked_before_second_execution(self):
        events = []
        answer = run_agent(
            "repeat the same thing",
            model=FakeModel("duplicate_loop"),
            on_event=events.append,
            max_steps=5,
        )

        self.assertIn("duplicate_tool_call", answer)
        tool_executes = [event for event in events if event["type"] == "tool_execute"]
        duplicate_checks = [event for event in events if event["type"] == "duplicate_check"]
        duplicate_rejections = [
            event
            for event in events
            if event["type"] == "tool_rejected"
            and event.get("reason") == "duplicate_tool_call"
        ]

        self.assertEqual(len(tool_executes), 1)
        self.assertEqual([event["duplicate"] for event in duplicate_checks], [False, True])
        self.assertEqual(len(duplicate_rejections), 1)

    def test_max_steps_must_be_positive_integer(self):
        with self.assertRaises(ValueError):
            run_agent("test", model=FakeModel("success"), max_steps=0)

    def test_max_retries_must_be_non_negative_integer(self):
        with self.assertRaises(ValueError):
            run_agent("test", model=FakeModel("success"), max_retries=-1)


if __name__ == "__main__":
    unittest.main()
