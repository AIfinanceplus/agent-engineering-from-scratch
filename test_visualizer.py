import unittest

from agent import run_agent
from model_adapters import FakeModel
from tools import reset_teaching_tools


class VisualizerTraceTests(unittest.TestCase):
    def setUp(self):
        reset_teaching_tools()

    def test_low_risk_trace_reaches_policy_and_execution(self):
        events = []
        answer = run_agent(
            "allow calculator",
            model=FakeModel("policy_allow"),
            on_event=events.append,
        )
        self.assertEqual(answer, "The result is 17.")
        lookup = next(event for event in events if event["type"] == "tool_lookup")
        decision = next(event for event in events if event["type"] == "policy_decision")
        self.assertEqual(lookup["tool_metadata"]["risk"], "low")
        self.assertEqual(decision["policy"]["decision"], "allow")
        self.assertIn("tool_attempt", [event["type"] for event in events])

    def test_medium_risk_trace_stops_before_tool_attempt(self):
        events = []
        answer = run_agent(
            "send message",
            model=FakeModel("policy_approval"),
            on_event=events.append,
        )
        self.assertIn("approval_required", answer)
        decision = next(event for event in events if event["type"] == "policy_decision")
        self.assertEqual(decision["policy"]["decision"], "require_approval")
        self.assertNotIn("tool_attempt", [event["type"] for event in events])

    def test_high_risk_trace_stops_before_tool_attempt(self):
        events = []
        answer = run_agent(
            "delete record",
            model=FakeModel("policy_deny"),
            on_event=events.append,
        )
        self.assertIn("policy_denied", answer)
        decision = next(event for event in events if event["type"] == "policy_decision")
        self.assertEqual(decision["policy"]["decision"], "deny")
        self.assertNotIn("tool_attempt", [event["type"] for event in events])

    def test_retry_trace_still_uses_flaky_tool_owned_policy(self):
        events = []
        answer = run_agent(
            "test retry",
            model=FakeModel("retry_success"),
            on_event=events.append,
        )
        self.assertEqual(answer, "The result is 42.")
        attempts = [event for event in events if event["type"] == "tool_attempt"]
        retries = [event for event in events if event["type"] == "tool_retry"]
        self.assertEqual([event["attempt"] for event in attempts], [1, 2])
        self.assertEqual(len(retries), 1)

    def test_duplicate_trace_blocks_second_real_execution(self):
        events = []
        run_agent("test duplicate", model=FakeModel("duplicate_loop"), on_event=events.append)
        checks = [event for event in events if event["type"] == "duplicate_check"]
        attempts = [event for event in events if event["type"] == "tool_attempt"]
        self.assertEqual([event["duplicate"] for event in checks], [False, True])
        self.assertEqual(len(attempts), 1)

    def test_invalid_arguments_never_reach_policy(self):
        events = []
        run_agent("bad args", model=FakeModel("missing_argument"), on_event=events.append)
        self.assertNotIn("policy_decision", [event["type"] for event in events])

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
