import unittest

from agent import run_agent
from model_adapters import FakeModel


class VisualizerTraceTests(unittest.TestCase):
    def test_runtime_emits_teaching_trace_without_changing_result(self):
        events = []

        answer = run_agent(
            "Please calculate 10 + 20.",
            model=FakeModel(),
            on_event=events.append,
        )

        self.assertEqual(answer, "The result is 30.")
        self.assertEqual(
            [event["type"] for event in events],
            [
                "user_input",
                "model_request",
                "model_response",
                "tool_lookup",
                "tool_execute",
                "tool_result",
                "model_request",
                "model_response",
                "final",
            ],
        )

        self.assertEqual(events[4]["tool_name"], "calculator")
        self.assertEqual(events[4]["arguments"]["operation"], "add")
        self.assertEqual(events[5]["result"], 30)


if __name__ == "__main__":
    unittest.main()
