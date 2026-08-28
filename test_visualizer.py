import unittest

from agent import run_agent
from model_adapters import FakeModel
from tools import reset_teaching_tools


class VisualizerTraceTests(unittest.TestCase):
    def setUp(self):
        reset_teaching_tools()

    def test_success_trace_exposes_calculator_tool_metadata(self):
        events = []
        answer = run_agent(
            "Please calculate 10 + 20.",
            model=FakeModel("success"),
            on_event=events.append,
        )
        self.assertEqual(answer, "The result is 30.")
        lookup = next(event for event in events if event["type"] == "tool_lookup")
        execute = next(event for event in events if event["type"] == "tool_execute")
        self.assertEqual(lookup["tool_metadata"]["name"], "calculator")
        self.assertEqual(lookup["tool_metadata"]["max_retries"], 0)
        self.assertEqual(execute["retry_policy_source"], "Tool.max_retries")
        self.assertEqual(execute["effective_max_retries"], 0)

    def test_retry_trace_uses_flaky_tool_owned_policy(self):
        events = []
        answer = run_agent(
            "test retry",
            model=FakeModel("retry_success"),
            on_event=events.append,
        )
        self.assertEqual(answer, "The result is 42.")
        lookup = next(event for event in events if event["type"] == "tool_lookup")
        attempts = [event for event in events if event["type"] == "tool_attempt"]
        retries = [event for event in events if event["type"] == "tool_retry"]
        self.assertEqual(lookup["tool_metadata"]["name"], "flaky_calculator")
        self.assertEqual(lookup["tool_metadata"]["max_retries"], 2)
        self.assertEqual([event["attempt"] for event in attempts], [1, 2])
        self.assertEqual(retries[0]["policy_source"], "Tool.max_retries")

    def test_duplicate_trace_blocks_second_real_execution(self):
        events = []
        run_agent("test duplicate", model=FakeModel("duplicate_loop"), on_event=events.append)
        checks = [event for event in events if event["type"] == "duplicate_check"]
        attempts = [event for event in events if event["type"] == "tool_attempt"]
        self.assertEqual([event["duplicate"] for event in checks], [False, True])
        self.assertEqual(len(attempts), 1)

    def test_rejected_call_never_reaches_tool_attempt(self):
        events = []
        answer = run_agent("test", model=FakeModel("missing_argument"), on_event=events.append)
        self.assertIn("missing_arguments", answer)
        self.assertNotIn("tool_attempt", [event["type"] for event in events])

    def test_non_duplicate_loop_still_hits_max_steps(self):
        events = []
        run_agent(
            "test",
            model=FakeModel("infinite_loop"),
            on_event=events.append,
            max_steps=2,
        )
        stop = next(event for event in events if event["type"] == "runtime_stop")
        self.assertEqual(stop["reason"], "max_steps")


if __name__ == "__main__":
    unittest.main()
