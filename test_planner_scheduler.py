import unittest

from context import ExecutionContext
from planner import DeterministicPlanner, ExecutionPlan, PlanTask, validate_plan
from scheduler import DAGScheduler
from tools import reset_teaching_tools


CONTEXT = ExecutionContext(
    tenant_id="demo-tenant",
    user_id="user-123",
    agent_id="general-agent",
    task_id="planner-test-root",
    trace_id="planner-test-trace",
)


class PlannerSchedulerTests(unittest.TestCase):
    def setUp(self):
        reset_teaching_tools()

    def test_planner_creates_expected_dag(self):
        plan = DeterministicPlanner().plan("combine two independent calculations")
        task_map = plan.task_map()

        self.assertEqual([task.task_id for task in plan.tasks], ["A", "B", "C"])
        self.assertEqual(task_map["A"].depends_on, [])
        self.assertEqual(task_map["B"].depends_on, [])
        self.assertEqual(task_map["C"].depends_on, ["A", "B"])
        self.assertEqual(task_map["C"].arguments["a"], {"from_task": "A"})
        self.assertEqual(task_map["C"].arguments["b"], {"from_task": "B"})

    def test_plan_validation_rejects_cycle(self):
        plan = ExecutionPlan(
            goal="cycle",
            tasks=[
                PlanTask("A", "A", "calculator", {}, depends_on=["B"]),
                PlanTask("B", "B", "calculator", {}, depends_on=["A"]),
            ],
        )
        with self.assertRaises(ValueError):
            validate_plan(plan)

    def test_scheduler_exposes_ready_blocked_transitions(self):
        events = []
        result = DAGScheduler().run(
            DeterministicPlanner().plan("test DAG"),
            execution_context=CONTEXT,
            on_event=events.append,
        )

        self.assertTrue(result["ok"])
        ticks = [event for event in events if event["type"] == "scheduler_tick"]
        self.assertEqual(ticks[0]["ready"], ["A", "B"])
        self.assertEqual(ticks[0]["blocked"], ["C"])
        self.assertEqual(ticks[1]["ready"], ["B"])
        self.assertEqual(ticks[1]["blocked"], ["C"])
        self.assertEqual(ticks[2]["ready"], ["C"])
        self.assertEqual(ticks[2]["blocked"], [])

    def test_scheduler_executes_dependency_results_and_finishes_at_72(self):
        events = []
        result = DAGScheduler().run(
            DeterministicPlanner().plan("test DAG"),
            execution_context=CONTEXT,
            on_event=events.append,
        )

        self.assertEqual(result["results"], {"A": 30, "B": 42, "C": 72})
        self.assertEqual(result["final_result"], 72)
        self.assertEqual(result["plan"]["status"], "completed")
        self.assertTrue(
            all(task["status"] == "completed" for task in result["plan"]["tasks"])
        )

        starts = [event for event in events if event["type"] == "task_started"]
        c_start = next(event for event in starts if event["task_id"] == "C")
        self.assertEqual(
            c_start["arguments"],
            {"a": 30, "b": 42, "operation": "add"},
        )

    def test_scheduler_keeps_existing_runtime_boundaries_inside_each_task(self):
        events = []
        DAGScheduler().run(
            DeterministicPlanner().plan("test DAG"),
            execution_context=CONTEXT,
            on_event=events.append,
        )

        nested = [
            event["event"]
            for event in events
            if event["type"] == "task_runtime_event"
        ]
        nested_types = [event["type"] for event in nested]
        self.assertIn("tool_validation", nested_types)
        self.assertIn("policy_decision", nested_types)
        self.assertIn("tool_attempt", nested_types)
        self.assertIn("state_saved", nested_types)


if __name__ == "__main__":
    unittest.main()
