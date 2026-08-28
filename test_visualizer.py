import unittest

from agent import run_agent
from model_adapters import FakeModel


class VisualizerTraceTests(unittest.TestCase):
    def test_success_trace_shows_model_and_tool_validation(self):
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
                "model_validation",
                "runtime_step",
                "tool_lookup",
                "tool_validation",
                "tool_execute",
                "tool_result",
                "tool_observation",
                "model_request",
                "model_response",
                "model_validation",
                "final",
            ],
        )

        self.assertEqual(events[3]["validation"], {"ok": True})
        self.assertEqual(events[4]["step"], 1)
        self.assertTrue(events[5]["found"])
        self.assertEqual(events[6]["validation"], {"ok": True})
        self.assertEqual(events[8]["result"], 30)

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

    def test_malformed_response_trace_stops_at_model_guard(self):
        events = []
        run_agent(
            "test",
            model=FakeModel("malformed_response"),
            on_event=events.append,
        )

        event_types = [event["type"] for event in events]
        self.assertEqual(event_types[-2:], ["runtime_stop", "final"])
        self.assertNotIn("runtime_step", event_types)
        self.assertNotIn("tool_lookup", event_types)

    def test_loop_trace_visibly_hits_runtime_limit(self):
        events = []
        run_agent(
            "test",
            model=FakeModel("infinite_loop"),
            on_event=events.append,
            max_steps=2,
        )

        steps = [event for event in events if event["type"] == "runtime_step"]
        stop = next(event for event in events if event["type"] == "runtime_stop")

        self.assertEqual(len(steps), 2)
        self.assertEqual(stop["reason"], "max_steps")


if __name__ == "__main__":
    unittest.main()
