import unittest

from agent import run_agent
from model_adapters import FakeModel
from tools import reset_teaching_tools


class VisualizerTraceTests(unittest.TestCase):
    def setUp(self):
        reset_teaching_tools()

    def test_success_trace_shows_guards_and_one_tool_attempt(self):
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
                "duplicate_check",
                "tool_lookup",
                "tool_validation",
                "tool_execute",
                "tool_attempt",
                "tool_result",
                "tool_observation",
                "model_request",
                "model_response",
                "model_validation",
                "final",
            ],
        )

        self.assertFalse(events[5]["duplicate"])
        self.assertEqual(events[9]["attempt"], 1)
        self.assertEqual(events[10]["result"], 30)

    def test_retry_trace_shows_two_attempts_inside_one_runtime_step(self):
        events = []

        answer = run_agent(
            "test retry",
            model=FakeModel("retry_success"),
            on_event=events.append,
            max_retries=2,
        )

        self.assertEqual(answer, "The result is 42.")
        steps = [event for event in events if event["type"] == "runtime_step"]
        attempts = [event for event in events if event["type"] == "tool_attempt"]
        retries = [event for event in events if event["type"] == "tool_retry"]

        self.assertEqual(len(steps), 1)
        self.assertEqual([event["attempt"] for event in attempts], [1, 2])
        self.assertEqual(len(retries), 1)

    def test_duplicate_trace_blocks_second_real_execution(self):
        events = []

        run_agent(
            "test duplicate",
            model=FakeModel("duplicate_loop"),
            on_event=events.append,
        )

        duplicate_checks = [event for event in events if event["type"] == "duplicate_check"]
        attempts = [event for event in events if event["type"] == "tool_attempt"]
        rejected = [
            event
            for event in events
            if event["type"] == "tool_rejected"
            and event.get("reason") == "duplicate_tool_call"
        ]

        self.assertEqual([event["duplicate"] for event in duplicate_checks], [False, True])
        self.assertEqual(len(attempts), 1)
        self.assertEqual(len(rejected), 1)

    def test_rejected_call_never_reaches_tool_attempt(self):
        events = []

        answer = run_agent(
            "test",
            model=FakeModel("missing_argument"),
            on_event=events.append,
        )

        event_types = [event["type"] for event in events]
        self.assertIn("tool_rejected", event_types)
        self.assertNotIn("tool_attempt", event_types)
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

    def test_non_duplicate_loop_trace_visibly_hits_runtime_limit(self):
        events = []
        run_agent(
            "test",
            model=FakeModel("infinite_loop"),
            on_event=events.append,
            max_steps=2,
        )

        steps = [event for event in events if event["type"] == "runtime_step"]
        duplicate_checks = [event for event in events if event["type"] == "duplicate_check"]
        stop = next(event for event in events if event["type"] == "runtime_stop")

        self.assertEqual(len(steps), 2)
        self.assertTrue(all(not event["duplicate"] for event in duplicate_checks))
        self.assertEqual(stop["reason"], "max_steps")


if __name__ == "__main__":
    unittest.main()
