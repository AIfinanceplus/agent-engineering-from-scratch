import unittest

from agent import run_agent
from model_adapters import FakeModel


class VisualizerTraceTests(unittest.TestCase):
    def test_success_trace_includes_validation_before_execution(self):
        events = []

        answer = run_agent(
            "Please calculate 10 + 20.",
            model=FakeModel("success"),
            on_event=events.append,
        )

        self.assertEqual(answer, "The result is 30.")
        event_types = [event["type"] for event in events]

        self.assertEqual(
            event_types,
            [
                "user_input",
                "model_request",
                "model_response",
                "tool_lookup",
                "tool_validation",
                "tool_execute",
                "tool_result",
                "tool_observation",
                "model_request",
                "model_response",
                "final",
            ],
        )

        self.assertTrue(events[3]["found"])
        self.assertEqual(events[4]["validation"], {"ok": True})
        self.assertEqual(events[6]["result"], 30)
        self.assertEqual(events[7]["observation"], 30)

    def test_rejected_call_never_reaches_tool_execute(self):
        events = []

        answer = run_agent(
            "test",
            model=FakeModel("missing_argument"),
            on_event=events.append,
        )

        event_types = [event["type"] for event in events]
        self.assertIn("tool_rejected", event_types)
        self.assertNotIn("tool_execute", event_types)
        self.assertIn("missing_arguments", answer)

    def test_unknown_tool_is_visible_as_lookup_miss_and_rejection(self):
        events = []

        run_agent(
            "test",
            model=FakeModel("unknown_tool"),
            on_event=events.append,
        )

        lookup = next(event for event in events if event["type"] == "tool_lookup")
        rejected = next(event for event in events if event["type"] == "tool_rejected")

        self.assertFalse(lookup["found"])
        self.assertEqual(rejected["error"]["code"], "unknown_tool")


if __name__ == "__main__":
    unittest.main()
