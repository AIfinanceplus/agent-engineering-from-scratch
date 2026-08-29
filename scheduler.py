"""Dependency-aware DAG Scheduler with V10 evidence lineage and V11 tracing.

Planner decides WHAT. Scheduler decides WHEN. The existing Agent Runtime still
controls HOW each selected Task executes. V10 adds EvidenceStore provenance.
V11 adds optional TraceRecorder spans and counters without changing task output.
"""

from dataclasses import replace
from typing import Any

from agent import run_agent
from context import ExecutionContext
from evidence import EvidenceRecord, EvidenceStore
from observability import TraceRecorder
from planner import ExecutionPlan, PlanTask, validate_plan
from state import InMemoryStateStore


class PlannedTaskModel:
    """Tiny deterministic model that proposes exactly one planned Tool Call."""

    def __init__(self, task: PlanTask, arguments: dict):
        self.task = task
        self.arguments = arguments

    def start(self, user_message: str) -> dict:
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
            "content": f"Task {self.task.task_id} completed.",
        }


class DAGScheduler:
    """Sequential teaching scheduler with explicit dependency transitions."""

    def run(
        self,
        plan: ExecutionPlan,
        *,
        execution_context: ExecutionContext,
        on_event=None,
        evidence_store: EvidenceStore | None = None,
        trace_recorder: TraceRecorder | None = None,
    ) -> dict:
        validate_plan(plan)
        plan.status = "running"
        results: dict[str, Any] = {}
        provenance = EvidenceStore() if evidence_store is None else evidence_store
        trace = trace_recorder
        root_span = (
            trace.start_span(
                "plan.run",
                attributes={"goal": plan.goal, "task_count": len(plan.tasks)},
            )
            if trace is not None
            else None
        )

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
            if trace is not None:
                trace.increment("scheduler_ticks")
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
                if trace is not None and root_span is not None:
                    trace.end_span(root_span, status="error", attributes={"error": error["code"]})
                return self._failure(plan, results, provenance, error, trace)

            task = ready[0]
            task.status = "running"
            resolved_arguments = self._resolve_arguments(task.arguments, results)
            if trace is not None:
                trace.increment("tasks_started")
            task_span = (
                trace.start_span(
                    f"task.{task.task_id}",
                    parent_span_id=root_span,
                    task_id=task.task_id,
                    attributes={
                        "title": task.title,
                        "tool_name": task.tool_name,
                        "depends_on": list(task.depends_on),
                    },
                )
                if trace is not None
                else None
            )
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
                if trace is not None:
                    trace.observe_runtime_event(event)
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
                if trace is not None and task_span is not None:
                    trace.end_span(task_span, status="error", attributes={"error": task.error["code"]})
                if trace is not None and root_span is not None:
                    trace.end_span(root_span, status="error", attributes={"error": task.error["code"]})
                return self._failure(plan, results, provenance, task.error, trace)

            result = task_state.last_observation
            if task_state.status != "completed" or (
                isinstance(result, dict) and "error" in result
            ):
                task.status = "failed"
                task.error = (
                    result.get("error")
                    if isinstance(result, dict) and "error" in result
                    else {"code": "task_runtime_failed", "message": answer}
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
                if trace is not None and task_span is not None:
                    trace.end_span(task_span, status="error", attributes={"error": task.error["code"]})
                if trace is not None and root_span is not None:
                    trace.end_span(root_span, status="error", attributes={"error": task.error["code"]})
                return self._failure(plan, results, provenance, task.error, trace)

            task.result = result
            provenance_kind = self._register_provenance(task, result, provenance, on_event)
            if trace is not None:
                if provenance_kind == "evidence":
                    trace.increment("evidence_registered")
                elif provenance_kind == "synthesis":
                    trace.increment("citations_verified", len(task.citation_ids))
            task.status = "completed"
            results[task.task_id] = result
            if trace is not None:
                trace.increment("tasks_completed")
                if task_span is not None:
                    trace.end_span(
                        task_span,
                        status="ok",
                        attributes={
                            "result_kind": result.get("kind") if isinstance(result, dict) else "value",
                            "evidence_ids": list(task.evidence_ids),
                            "citation_ids": list(task.citation_ids),
                        },
                    )
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
        final_artifact = results.get(final_task.task_id) if final_task else None
        final_result = (
            final_artifact.get("answer")
            if isinstance(final_artifact, dict) and final_artifact.get("kind") == "synthesis"
            else final_artifact
        )
        citations = (
            provenance.citations(final_artifact.get("evidence_ids", []))
            if isinstance(final_artifact, dict) and final_artifact.get("kind") == "synthesis"
            else []
        )
        if trace is not None and root_span is not None:
            trace.end_span(
                root_span,
                status="ok",
                attributes={
                    "plan_status": plan.status,
                    "evidence_count": len(provenance.all()),
                    "citation_count": len(citations),
                },
            )
        trace_summary = trace.summary() if trace is not None else None
        self._emit(
            on_event,
            "plan_completed",
            final_result=final_result,
            final_artifact=final_artifact,
            citations=citations,
            evidence=provenance.all(),
            trace=trace_summary,
            results=dict(results),
            plan=plan.to_dict(),
        )
        return {
            "ok": True,
            "plan": plan.to_dict(),
            "results": results,
            "final_result": final_result,
            "final_artifact": final_artifact,
            "evidence": provenance.all(),
            "citations": citations,
            "trace": trace_summary,
        }

    @classmethod
    def _register_provenance(
        cls,
        task: PlanTask,
        result,
        provenance: EvidenceStore,
        on_event,
    ) -> str | None:
        if not isinstance(result, dict):
            return None

        if result.get("kind") == "evidence":
            record = EvidenceRecord.from_dict(result)
            provenance.add(record)
            task.evidence_ids = [record.evidence_id]
            cls._emit(
                on_event,
                "evidence_registered",
                task_id=task.task_id,
                evidence=record.to_dict(),
            )
            return "evidence"

        if result.get("kind") == "synthesis":
            evidence_ids = list(result.get("evidence_ids", []))
            citations = provenance.citations(evidence_ids)
            task.evidence_ids = evidence_ids
            task.citation_ids = [item["citation"] for item in citations]
            cls._emit(
                on_event,
                "synthesis_verified",
                task_id=task.task_id,
                answer=result.get("answer"),
                confidence=result.get("confidence"),
                evidence_ids=evidence_ids,
                citations=citations,
            )
            return "synthesis"
        return None

    @staticmethod
    def _failure(plan, results, provenance, error, trace=None):
        return {
            "ok": False,
            "plan": plan.to_dict(),
            "error": error,
            "results": results,
            "evidence": provenance.all(),
            "citations": [],
            "trace": trace.summary() if trace is not None else None,
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
