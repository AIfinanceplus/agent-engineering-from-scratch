"""Planner + DAG data model.

V9 introduced dependency-aware planning. V10 keeps the arithmetic plan for
regression tests and adds a research plan whose upstream Tasks collect evidence
and whose downstream Task synthesizes only those collected records.
"""

from copy import deepcopy
from dataclasses import asdict, dataclass, field


TERMINAL_STATUSES = {"completed", "failed"}


@dataclass
class PlanTask:
    task_id: str
    title: str
    tool_name: str
    arguments: dict
    depends_on: list[str] = field(default_factory=list)
    status: str = "pending"
    result: object | None = None
    error: dict | None = None
    evidence_ids: list[str] = field(default_factory=list)
    citation_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return deepcopy(asdict(self))


@dataclass
class ExecutionPlan:
    goal: str
    tasks: list[PlanTask]
    status: str = "planned"

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "status": self.status,
            "tasks": [task.to_dict() for task in self.tasks],
        }

    def task_map(self) -> dict[str, PlanTask]:
        return {task.task_id: task for task in self.tasks}


class DeterministicPlanner:
    """V9 arithmetic DAG retained as a regression / comparison scenario."""

    def plan(self, goal: str) -> ExecutionPlan:
        _validate_goal(goal)
        plan = ExecutionPlan(
            goal=goal,
            tasks=[
                PlanTask(
                    task_id="A",
                    title="Calculate 10 + 20",
                    tool_name="calculator",
                    arguments={"a": 10, "b": 20, "operation": "add"},
                ),
                PlanTask(
                    task_id="B",
                    title="Calculate 6 × 7",
                    tool_name="calculator",
                    arguments={"a": 6, "b": 7, "operation": "multiply"},
                ),
                PlanTask(
                    task_id="C",
                    title="Combine A + B",
                    tool_name="calculator",
                    arguments={
                        "a": {"from_task": "A"},
                        "b": {"from_task": "B"},
                        "operation": "add",
                    },
                    depends_on=["A", "B"],
                ),
            ],
        )
        validate_plan(plan)
        return plan


class ResearchPlanner:
    """V10 teaching research DAG: collect evidence, then synthesize it."""

    def plan(self, goal: str) -> ExecutionPlan:
        _validate_goal(goal)
        plan = ExecutionPlan(
            goal=goal,
            tasks=[
                PlanTask(
                    task_id="E1",
                    title="Collect synthetic energy evidence",
                    tool_name="lookup_evidence",
                    arguments={"topic": "energy"},
                ),
                PlanTask(
                    task_id="E2",
                    title="Collect synthetic shelter evidence",
                    tool_name="lookup_evidence",
                    arguments={"topic": "shelter"},
                ),
                PlanTask(
                    task_id="S1",
                    title="Synthesize only the collected evidence",
                    tool_name="synthesize_evidence",
                    arguments={
                        "evidence_a": {"from_task": "E1"},
                        "evidence_b": {"from_task": "E2"},
                    },
                    depends_on=["E1", "E2"],
                ),
            ],
        )
        validate_plan(plan)
        return plan


def _validate_goal(goal: str) -> None:
    if not isinstance(goal, str) or not goal.strip():
        raise ValueError("goal must be a non-empty string")


def validate_plan(plan: ExecutionPlan) -> None:
    """Fail closed on missing dependencies, duplicate IDs, or cycles."""
    if not isinstance(plan, ExecutionPlan):
        raise TypeError("plan must be an ExecutionPlan")

    task_ids = [task.task_id for task in plan.tasks]
    if len(task_ids) != len(set(task_ids)):
        raise ValueError("plan contains duplicate task IDs")

    known = set(task_ids)
    for task in plan.tasks:
        if task.task_id in task.depends_on:
            raise ValueError(f"task {task.task_id} cannot depend on itself")
        missing = [dep for dep in task.depends_on if dep not in known]
        if missing:
            raise ValueError(f"task {task.task_id} has missing dependencies: {missing}")

    indegree = {task.task_id: len(task.depends_on) for task in plan.tasks}
    children = {task.task_id: [] for task in plan.tasks}
    for task in plan.tasks:
        for dependency in task.depends_on:
            children[dependency].append(task.task_id)

    queue = [task_id for task_id, degree in indegree.items() if degree == 0]
    visited = 0
    while queue:
        task_id = queue.pop(0)
        visited += 1
        for child in children[task_id]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)

    if visited != len(plan.tasks):
        raise ValueError("plan contains a dependency cycle")
