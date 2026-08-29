import tempfile
import unittest

from agent import SimulatedCrash, run_agent
from checkpoint import JsonCheckpointStore
from context import ExecutionContext
from model_adapters import FakeModel
from state import AgentState
from tools import reset_teaching_tools


DURABLE_CONTEXT = ExecutionContext(
    tenant_id="demo-tenant",
    user_id="user-123",
    agent_id="general-agent",
    task_id="durable-two-step-task",
    trace_id="trace-durable-v8",
)


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        reset_teaching_tools()

    def test_json_checkpoint_survives_new_store_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            first_store = JsonCheckpointStore(directory)
            state = AgentState(
                task_id="task-1",
                max_steps=4,
                phase="observation_ready",
                step=1,
                current_tool="calculator",
                current_arguments={"a": 10, "b": 20, "operation": "add"},
                last_observation=30,
                observations=[
                    {"step": 1, "tool_name": "calculator", "observation": 30}
                ],
                pending_response_id="response-1",
                pending_call_id="call-1",
                seen_calls=['calculator:{"a":10,"b":20,"operation":"add"}'],
            )
            first_store.save(state, reason="observation_recorded")

            second_store = JsonCheckpointStore(directory)
            loaded = second_store.load("task-1")

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.phase, "observation_ready")
            self.assertEqual(loaded.last_observation, 30)
            self.assertEqual(loaded.pending_call_id, "call-1")
            self.assertEqual(len(second_store.history("task-1")), 1)

    def test_crash_after_first_observation_leaves_safe_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonCheckpointStore(directory)
            events = []

            with self.assertRaises(SimulatedCrash):
                run_agent(
                    "do two calculations",
                    model=FakeModel("multi_step"),
                    on_event=events.append,
                    max_steps=4,
                    execution_context=DURABLE_CONTEXT,
                    state_store=store,
                    crash_after_observations=1,
                )

            saved = store.load(DURABLE_CONTEXT.task_id)
            self.assertIsNotNone(saved)
            self.assertEqual(saved.status, "running")
            self.assertEqual(saved.phase, "observation_ready")
            self.assertEqual(saved.step, 1)
            self.assertEqual(saved.last_observation, 30)
            self.assertEqual(len(saved.observations), 1)
            self.assertTrue(saved.pending_response_id)
            self.assertTrue(saved.pending_call_id)
            self.assertIn("simulated_crash", [event["type"] for event in events])

    def test_fresh_runtime_resumes_without_reexecuting_completed_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            first_store = JsonCheckpointStore(directory)

            with self.assertRaises(SimulatedCrash):
                run_agent(
                    "do two calculations",
                    model=FakeModel("multi_step"),
                    max_steps=4,
                    execution_context=DURABLE_CONTEXT,
                    state_store=first_store,
                    crash_after_observations=1,
                )

            # New store + new model simulate a fresh process reading disk.
            second_store = JsonCheckpointStore(directory)
            resume_events = []
            answer = run_agent(
                "ignored on resume",
                model=FakeModel("multi_step"),
                on_event=resume_events.append,
                execution_context=DURABLE_CONTEXT,
                state_store=second_store,
                resume=True,
            )

            self.assertEqual(
                answer,
                "Completed two calculations: 10 + 20 = 30, 6 × 7 = 42.",
            )

            attempts = [
                event for event in resume_events if event["type"] == "tool_attempt"
            ]
            self.assertEqual(len(attempts), 1)
            self.assertEqual(
                attempts[0]["arguments"],
                {"a": 6, "b": 7, "operation": "multiply"},
            )
            self.assertIn("checkpoint_loaded", [event["type"] for event in resume_events])
            self.assertIn("resume_boundary", [event["type"] for event in resume_events])

            final_state = second_store.load(DURABLE_CONTEXT.task_id)
            self.assertEqual(final_state.status, "completed")
            self.assertEqual(final_state.phase, "completed")
            self.assertEqual(
                [item["observation"] for item in final_state.observations],
                [30, 42],
            )

    def test_resume_without_checkpoint_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonCheckpointStore(directory)
            with self.assertRaises(RuntimeError):
                run_agent(
                    "resume missing task",
                    model=FakeModel("multi_step"),
                    execution_context=DURABLE_CONTEXT,
                    state_store=store,
                    resume=True,
                )


if __name__ == "__main__":
    unittest.main()
