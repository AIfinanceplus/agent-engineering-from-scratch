import tempfile
import unittest

from agent import SimulatedCrash, run_agent
from checkpoint import JsonCheckpointStore
from context import ExecutionContext
from model_adapters import FakeModel
from tools import reset_teaching_tools


GENERAL_CONTEXT = ExecutionContext(
    tenant_id="demo-tenant",
    user_id="user-123",
    agent_id="general-agent",
    task_id="visual-general",
    trace_id="trace-general",
)

READ_ONLY_CONTEXT = ExecutionContext(
    tenant_id="demo-tenant",
    user_id="user-123",
    agent_id="read-only-agent",
    task_id="visual-read-only",
    trace_id="trace-read-only",
)

DURABLE_CONTEXT = ExecutionContext(
    tenant_id="demo-tenant",
    user_id="user-123",
    agent_id="general-agent",
    task_id="visual-durable",
    trace_id="trace-visual-durable",
)


class VisualizerTraceTests(unittest.TestCase):
    def setUp(self):
        reset_teaching_tools()

    def test_trace_starts_with_runtime_execution_context(self):
        events = []
        run_agent(
            "test",
            model=FakeModel("policy_allow"),
            on_event=events.append,
            execution_context=GENERAL_CONTEXT,
        )
        self.assertEqual(events[0]["type"], "execution_context")
        self.assertEqual(events[0]["context"]["agent_id"], "general-agent")
        self.assertEqual(events[0]["source"], "Runtime injected")
        self.assertIn("state_saved", [event["type"] for event in events])

    def test_low_risk_read_only_context_can_still_execute(self):
        events = []
        answer = run_agent(
            "allow calculator",
            model=FakeModel("policy_allow"),
            on_event=events.append,
            execution_context=READ_ONLY_CONTEXT,
        )
        self.assertEqual(answer, "The result is 17.")
        decision = next(event for event in events if event["type"] == "policy_decision")
        self.assertEqual(decision["context"]["agent_id"], "read-only-agent")
        self.assertEqual(decision["policy"]["decision"], "allow")
        self.assertIn("tool_attempt", [event["type"] for event in events])

    def test_same_medium_risk_tool_changes_with_context(self):
        general_events = []
        read_only_events = []

        general_answer = run_agent(
            "send message",
            model=FakeModel("policy_approval"),
            on_event=general_events.append,
            execution_context=GENERAL_CONTEXT,
        )
        read_only_answer = run_agent(
            "send message",
            model=FakeModel("policy_approval"),
            on_event=read_only_events.append,
            execution_context=READ_ONLY_CONTEXT,
        )

        general_decision = next(
            event for event in general_events if event["type"] == "policy_decision"
        )
        read_only_decision = next(
            event for event in read_only_events if event["type"] == "policy_decision"
        )

        self.assertIn("approval_required", general_answer)
        self.assertEqual(
            general_decision["policy"]["decision"],
            "require_approval",
        )
        self.assertIn("policy_denied", read_only_answer)
        self.assertEqual(read_only_decision["policy"]["decision"], "deny")
        self.assertNotIn("tool_attempt", [event["type"] for event in general_events])
        self.assertNotIn("tool_attempt", [event["type"] for event in read_only_events])

    def test_retry_trace_still_uses_flaky_tool_owned_policy(self):
        events = []
        answer = run_agent(
            "test retry",
            model=FakeModel("retry_success"),
            on_event=events.append,
            execution_context=GENERAL_CONTEXT,
        )
        self.assertEqual(answer, "The result is 42.")
        attempts = [event for event in events if event["type"] == "tool_attempt"]
        self.assertEqual([event["attempt"] for event in attempts], [1, 2])

    def test_duplicate_trace_blocks_second_real_execution(self):
        events = []
        run_agent(
            "test duplicate",
            model=FakeModel("duplicate_loop"),
            on_event=events.append,
            execution_context=GENERAL_CONTEXT,
        )
        checks = [event for event in events if event["type"] == "duplicate_check"]
        attempts = [event for event in events if event["type"] == "tool_attempt"]
        self.assertEqual([event["duplicate"] for event in checks], [False, True])
        self.assertEqual(len(attempts), 1)

    def test_crash_trace_ends_after_durable_observation_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonCheckpointStore(directory)
            events = []

            with self.assertRaises(SimulatedCrash):
                run_agent(
                    "two steps",
                    model=FakeModel("multi_step"),
                    on_event=events.append,
                    max_steps=4,
                    execution_context=DURABLE_CONTEXT,
                    state_store=store,
                    crash_after_observations=1,
                )

            crash_index = next(
                index
                for index, event in enumerate(events)
                if event["type"] == "simulated_crash"
            )
            checkpoint_index = max(
                index
                for index, event in enumerate(events[:crash_index])
                if event["type"] == "state_saved"
                and event["state"]["phase"] == "observation_ready"
            )
            self.assertLess(checkpoint_index, crash_index)
            self.assertEqual(events[checkpoint_index]["state"]["last_observation"], 30)

    def test_resume_trace_marks_new_runtime_boundary_and_skips_first_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            first_store = JsonCheckpointStore(directory)
            with self.assertRaises(SimulatedCrash):
                run_agent(
                    "two steps",
                    model=FakeModel("multi_step"),
                    max_steps=4,
                    execution_context=DURABLE_CONTEXT,
                    state_store=first_store,
                    crash_after_observations=1,
                )

            resume_events = []
            second_store = JsonCheckpointStore(directory)
            answer = run_agent(
                "ignored",
                model=FakeModel("multi_step"),
                on_event=resume_events.append,
                execution_context=DURABLE_CONTEXT,
                state_store=second_store,
                resume=True,
            )

            event_types = [event["type"] for event in resume_events]
            self.assertEqual(answer, "Completed two calculations: 10 + 20 = 30, 6 × 7 = 42.")
            self.assertEqual(resume_events[0]["type"], "execution_context")
            self.assertEqual(resume_events[0]["source"], "Runtime re-injected")
            self.assertIn("checkpoint_loaded", event_types)
            self.assertIn("resume_boundary", event_types)

            attempts = [event for event in resume_events if event["type"] == "tool_attempt"]
            self.assertEqual(len(attempts), 1)
            self.assertEqual(
                attempts[0]["arguments"],
                {"a": 6, "b": 7, "operation": "multiply"},
            )


if __name__ == "__main__":
    unittest.main()
