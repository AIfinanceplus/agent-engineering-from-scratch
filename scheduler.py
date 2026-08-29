"""V9 dependency-aware DAG Scheduler.

The Scheduler never invents new tasks. It reads a validated ExecutionPlan,
computes READY/BLOCKED tasks from dependencies, and hands one READY task to the
existing Agent Runtime. This keeps planning, scheduling, and execution as three
separate responsibilities.
"""

from dataclasses import replace
from typing import Any

from agent import run_agent
from context import ExecutionContext
from planner import ExecutionPlan, PlanTask, validate_plan
from state import InMemoryStateStore


class PlannedTaskModel:
    """Tiny deterministic model that proposes exactly one planned Tool Call."""

    def __init__(self, task: PlanTask, arguments: dict):
        self.task = task
        self.arguments = arguments
        self.started = False

    def start(self, user_message: str) -> dict:
        self.started = True
        return {
            "type": "tool_call",
            "response_id": f"planned-response-{self.task.task_id}",
            "call_id": f"planned-call-{self.task.task_id}",
            "tool_name": self.task.tool_name,
            "arguments": dict(self.arguments),
        }

    def continue_with_tool_result(
        self,
        *,
        previous_response_id,
        call_id,
        tool_name,
        result,
    ) -> dict:
        if isinstance(result, dict) and "error" in result:
            error = result["error"]
            return {
                "type": "final",
                "content": f"Task {self.task.task_id} failed [{error['code']}]: {error['message']}",
            }
        return {
            "type": "final",
            "content": f"Task {self.task.task_id} completed with result {result}.",
        }


class DAGScheduler:
    """Sequential teaching scheduler with explicit READY/BLOCKED transitions.

    A and B may both become READY in the same scheduler tick. V9 deliberately
    executes one READY task at a time so dependency semantics stay visible.
    Parallel execution can be layered on later without changing the DAG model.
    """

    def run(
        self,
        plan: ExecutionPlan,
        *,
        execution_context: ExecutionContext,
        on_event=None,
    ) -> dict:
        validate_plan(plan)
        plan.status = "running"
        results: dict[str, Any] = {}

        self._emit(on_event, "plan_created", plan=plan.to_dict())

        while True:
            unfinished = [
                task for task in plan.tasks if task.status not in {"completed", "failed"}
            ]
            if not unfinished:
                break

            self._refresh_statuses(plan)
            ready = [task for task in plan.tasks if task.status == "ready"]
            blocked = [task for task in plan.tasks if task.status == "blocked"]

            self._emit(
                on_event,
                "scheduler_tick",
                ready=[task.task_id for task in ready],
                blocked=[task.task_id for task in blocked],
                plan=plan.to_dict(),
            )

            if not ready:
                plan.status = "failed"
                error = {
                    "code": "scheduler_deadlock",
                    "message": "No READY task exists while unfinished tasks remain.",
                }
                self._emit(on_event, "plan_failed", error=error, plan=plan.to_dict())
                return {"ok": False, "plan": plan.to_dict(), "error": error, "results": results}

            task = ready[0]
            task.status = "running"
            resolved_arguments = self._resolve_arguments(task.arguments, results)
            self._emit(
                on_event,
                "task_started",
                task_id=task.task_id,
                title=task.title,
                depends_on=list(task.depends_on),
                arguments=resolved_arguments,
                plan=plan.to_dict(),
            )

            task_context = replace(
                execution_context,
                task_id=f"{execution_context.task_id}:{task.task_id}",
                trace_id=f"{execution_context.trace_id}:{task.task_id}",
            )
            task_store = InMemoryStateStore()

            def task_event(event: dict) -> None:
                self._emit(
                    on_event,
                    "task_runtime_event",
                    task_id=task.task_id,
                    event=event,
                )

            answer = run_agent(
                task.title,
                model=PlannedTaskModel(task, resolved_arguments),
                on_event=task_event,
                max_steps=2,
                execution_context=task_context,
                state_store=task_store,
            )
            task_state = task_store.load(task_context.task_id)

            if task_state is None:
                task.status = "failed"
                task.error = {
                    "code": "missing_task_state",
                    "message": "Task Runtime finished without a StateStore snapshot.",
                }
                plan.status = "failed"
                self._emit(
                    on_event,
                    "task_failed",
                    task_id=task.task_id,
                    error=task.error,
                    answer=answer,
                    plan=plan.to_dict(),
                )
                return {
                    "ok": False,
                    "plan": plan.to_dict(),
                    "error": task.error,
                    "results": results,
                }

            result = task_state.last_observation
            if task_state.status != "completed" or (
                isinstance(result, dict) and "error" in result
            ):
                task.status = "failed"
                task.error = (
                    result.get("error")
                    if isinstance(result, dict) and "error" in result
                    else {
                        "code": "task_runtime_failed",
                        "message": answer,
                    }
                )
                plan.status = "failed"
                self._emit(
                    on_event,
                    "task_failed",
                    task_id=task.task_id,
                    error=task.error,
                    answer=answer,
                    plan=plan.to_dict(),
                )
                return {
                    "ok": False,
                    "plan": plan.to_dict(),
                    "error": task.error,
                    "results": results,
                }

            task.result = result
            task.status = "completed"
            results[task.task_id] = result
            self._emit(
                on_event,
                "task_completed",
                task_id=task.task_id,
                result=result,
                answer=answer,
                plan=plan.to_dict(),
            )

        plan.status = "completed"
        final_task = plan.tasks[-1] if plan.tasks else None
        final_result = results.get(final_task.task_id) if final_task else None
        self._emit(
            on_event,
            "plan_completed",
            final_result=final_result,
            results=dict(results),
            plan=plan.to_dict(),
        )
        return {
            "ok": True,
            "plan": plan.to_dict(),
            "results": results,
            "final_result": final_result,
        }

    @staticmethod
    def _emit(on_event, event_type: str, **payload) -> None:
        if on_event is not None:
            on_event({"type": event_type, **payload})

    @staticmethod
    def _refresh_statuses(plan: ExecutionPlan) -> None:
        task_map = plan.task_map()
        for task in plan.tasks:
            if task.status in {"completed", "failed", "running"}:
                continue
            dependencies_done = all(
                task_map[dependency].status == "completed"
                for dependency in task.depends_on
            )
            task.status = "ready" if dependencies_done else "blocked"

    @classmethod
    def _resolve_arguments(cls, value, results: dict[str, Any]):
        if isinstance(value, dict):
            if set(value.keys()) == {"from_task"}:
                dependency = value["from_task"]
                if dependency not in results:
                    raise RuntimeError(
                        f"Cannot resolve result from unfinished task {dependency}"
                    )
                return results[dependency]
            return {
                key: cls._resolve_arguments(item, results)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [cls._resolve_arguments(item, results) for item in value]
        return value
