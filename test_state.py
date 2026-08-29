import unittest

from agent import run_agent
from context import ExecutionContext
from model_adapters import FakeModel
from state import AgentState, InMemoryStateStore
from tools import reset_teaching_tools


CONTEXT = ExecutionContext(
    tenant_id="demo-tenant",
    user_id="user-123",
    agent_id="general-agent",
    task_id="state-test-task",
    trace_id="state-test-trace",
)


class StateStoreTests(unittest.TestCase):
    def setUp(self):
        reset_teaching_tools()

    def test_store_save_and_load_use_snapshots(self):
        store = InMemoryStateStore()
        state = AgentState(task_id="task-1", max_steps=5)
        state.phase = "model_thinking"
        store.save(state, reason="first")

        state.phase = "executing_tool"
        loaded = store.load("task-1")

        self.assertEqual(loaded.phase, "model_thinking")
        self.assertEqual(store.history("task-1")[0]["reason"], "first")

    def test_multi_step_run_accumulates_two_results_in_state(self):
        store = InMemoryStateStore()
        events = []

        answer = run_agent(
            "calculate twice",
            model=FakeModel("multi_step"),
            execution_context=CONTEXT,
            state_store=store,
            on_event=events.append,
            max_steps=4,
        )

        latest = store.load(CONTEXT.task_id)
        self.assertIn("10 + 20 = 30", answer)
        self.assertIn("6 × 7 = 42", answer)
        self.assertEqual(latest.status, "completed")
        self.assertEqual(latest.phase, "completed")
        self.assertEqual(latest.step, 2)
        self.assertEqual(len(latest.observations), 2)
        self.assertEqual(latest.observations[0]["observation"], 30)
        self.assertEqual(latest.observations[1]["observation"], 42)
        self.assertEqual(latest.final_answer, answer)

    def test_state_events_show_major_runtime_phases(self):
        store = InMemoryStateStore()
        events = []

        run_agent(
            "calculate twice",
            model=FakeModel("multi_step"),
            execution_context=CONTEXT,
            state_store=store,
            on_event=events.append,
        )

        phases = [
            event["state"]["phase"]
            for event in events
            if event["type"] == "state_saved"
        ]

        self.assertIn("received_input", phases)
        self.assertIn("model_thinking", phases)
        self.assertIn("tool_selected", phases)
        self.assertIn("validating_tool", phases)
        self.assertIn("checking_policy", phases)
        self.assertIn("executing_tool", phases)
        self.assertIn("observation_ready", phases)
        self.assertEqual(phases[-1], "completed")

    def test_observation_snapshot_is_saved_before_model_continues(self):
        store = InMemoryStateStore()
        events = []

        run_agent(
            "calculate twice",
            model=FakeModel("multi_step"),
            execution_context=CONTEXT,
            state_store=store,
            on_event=events.append,
        )

        observation_saves = [
            event
            for event in events
            if event["type"] == "state_saved"
            and event["reason"] == "observation_recorded"
        ]
        self.assertEqual(len(observation_saves), 2)
        self.assertEqual(
            observation_saves[0]["state"]["observations"][0]["observation"],
            30,
        )
        self.assertEqual(
            observation_saves[1]["state"]["observations"][1]["observation"],
            42,
        )

    def test_max_steps_stop_is_persisted_with_previous_results(self):
        store = InMemoryStateStore()

        answer = run_agent(
            "loop",
            model=FakeModel("infinite_loop"),
            execution_context=CONTEXT,
            state_store=store,
            max_steps=2,
        )

        latest = store.load(CONTEXT.task_id)
        self.assertIn("max_steps_exceeded", answer)
        self.assertEqual(latest.status, "stopped")
        self.assertEqual(latest.stop_reason, "max_steps")
        self.assertEqual(latest.step, 2)
        self.assertEqual(len(latest.observations), 2)


if __name__ == "__main__":
    unittest.main()
