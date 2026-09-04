"""R12 Step 6 human-in-the-loop Strategy Agent orchestration.

The existing R12 functions are already registered as Tools. This module makes
their orchestration explicit: a deterministic Planner builds a dependency graph,
each executable task crosses the shared Agent Runtime/Tool Registry boundary, and
the workflow pauses at a durable human identity-review checkpoint.

Only read/compute Tools are in this workflow. It never places orders. A persisted
completed task is not re-executed on resume; an interrupted in-flight read may be
retried because no external side effect is permitted in this plan.
"""

from __future__ import annotations

import hashlib
import json
import os
from functools import wraps
from math import isfinite
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from agent import run_agent
from context import ExecutionContext
from observability import TraceRecorder
from planner import ExecutionPlan, PlanTask, validate_plan
from r12_identity import IDENTITY_CHECKS
from r12_tooling import register_r12_tools
from scheduler import PlannedTaskModel
from state import InMemoryStateStore


HUMAN_GATE_TASK_ID = "H1"
TERMINAL_RUN_STATUSES = {
    "COMPLETED_PAPER_QUOTE",
    "BLOCKED_RULES_ANALYSIS",
    "BLOCKED_IDENTITY_REJECTED",
    "FAILED_TOOL_EXECUTION",
}


def _serialized(method):
    """Serialize mutations performed by the local threaded preview server."""
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapper


class R12SimulatedOrchestratorCrash(RuntimeError):
    """Teaching-only crash raised after a durable task checkpoint."""


class R12StrategyPlanner:
    """Build the exact-pair R12 Tool DAG with one explicit human boundary."""

    def plan_exact_pair(
        self,
        *,
        kalshi_identifier: str,
        polymarket_identifier: str,
        target_contracts: float,
        fee_model: dict,
        latency_buffer_bps: float = 0.0,
        estimated_total_cost_per_basket: float = 0.0,
    ) -> ExecutionPlan:
        kalshi_identifier = _required_text(kalshi_identifier, "kalshi_identifier")
        polymarket_identifier = _required_text(polymarket_identifier, "polymarket_identifier")
        target_contracts = _positive_number(target_contracts, "target_contracts")
        latency_buffer_bps = _non_negative_number(latency_buffer_bps, "latency_buffer_bps")
        estimated_total_cost_per_basket = _non_negative_number(
            estimated_total_cost_per_basket,
            "estimated_total_cost_per_basket",
        )
        fee_model = _explicit_fee_model(fee_model)
        tasks = [
            PlanTask(
                "K1",
                "Fetch exact Kalshi market contract through the R12 Tool boundary",
                "fetch_r12_market_contract",
                {"provider": "kalshi", "identifier": kalshi_identifier},
            ),
            PlanTask(
                "P1",
                "Fetch exact Polymarket market contract through the R12 Tool boundary",
                "fetch_r12_market_contract",
                {"provider": "polymarket", "identifier": polymarket_identifier},
            ),
            PlanTask(
                "R1",
                "Analyze fingerprint-bound settlement rules without approving identity",
                "analyze_r12_settlement_rules",
                {
                    "kalshi_contract": {"from_task": "K1"},
                    "polymarket_contract": {"from_task": "P1"},
                },
                depends_on=["K1", "P1"],
            ),
            PlanTask(
                HUMAN_GATE_TASK_ID,
                "Pause for explicit human settlement-identity review",
                "human_identity_approval_boundary",
                {},
                depends_on=["R1"],
            ),
            PlanTask(
                "I1",
                "Validate event identity using current rules analysis and human attestation",
                "validate_r12_event_identity",
                {
                    "kalshi_contract": {"from_task": "K1"},
                    "polymarket_contract": {"from_task": "P1"},
                    "rules_analysis": {"from_task": "R1"},
                    "attestation": {"from_task": HUMAN_GATE_TASK_ID},
                },
                depends_on=["K1", "P1", "R1", HUMAN_GATE_TASK_ID],
            ),
            PlanTask(
                "V1",
                "Compare verified same-event top-of-book reciprocal baskets",
                "compare_r12_cross_market_locked_rv",
                {
                    "identity": {"from_task": "I1"},
                    "kalshi_contract": {"from_task": "K1"},
                    "polymarket_contract": {"from_task": "P1"},
                    "estimated_total_cost_per_basket": estimated_total_cost_per_basket,
                },
                depends_on=["I1"],
            ),
            PlanTask(
                "E1",
                "Quote target quantity against full visible depth with explicit costs",
                "quote_r12_cross_market_execution",
                {
                    "identity": {"from_task": "I1"},
                    "kalshi_contract": {"from_task": "K1"},
                    "polymarket_contract": {"from_task": "P1"},
                    "target_contracts": target_contracts,
                    "fee_model": deepcopy(fee_model),
                    "latency_buffer_bps": latency_buffer_bps,
                },
                depends_on=["I1"],
            ),
        ]
        plan = ExecutionPlan(
            goal=(
                "Evaluate one exact Kalshi/Polymarket pair through rules, human identity, "
                "relative-value, and depth-aware paper-quote gates"
            ),
            tasks=tasks,
        )
        validate_plan(plan)
        return plan


class JsonR12StrategyRunStore:
    """Atomic durable store for resumable Strategy Agent run artifacts."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, run: dict) -> Path:
        _validate_run_artifact(run)
        path = self._path(run["run_id"])
        temp_path = path.with_suffix(".json.tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(run, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        return path

    def load(self, run_id: str) -> dict | None:
        path = self._path(_required_text(run_id, "run_id"))
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            run = json.load(handle)
        _validate_run_artifact(run)
        if run.get("run_id") != run_id:
            raise RuntimeError("R12 Strategy Agent run_id mismatch")
        return run

    def exists(self, run_id: str) -> bool:
        return self._path(_required_text(run_id, "run_id")).exists()

    def _path(self, run_id: str) -> Path:
        digest = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:24]
        return self.directory / f"{digest}.json"


class R12StrategyAgent:
    """Run, pause, approve, persist, and resume one exact-pair Tool plan."""

    def __init__(self, store: JsonR12StrategyRunStore, *, planner: R12StrategyPlanner | None = None):
        if not isinstance(store, JsonR12StrategyRunStore):
            raise TypeError("store must be a JsonR12StrategyRunStore")
        register_r12_tools()
        self.store = store
        self.planner = planner or R12StrategyPlanner()
        self._lock = RLock()

    @_serialized
    def start_exact_pair(
        self,
        *,
        kalshi_identifier: str,
        polymarket_identifier: str,
        target_contracts: float,
        fee_model: dict,
        latency_buffer_bps: float = 0.0,
        estimated_total_cost_per_basket: float = 0.0,
        run_id: str | None = None,
        crash_after_completed_tasks: int | None = None,
    ) -> dict:
        run_id = _required_text(run_id, "run_id") if run_id is not None else f"R12A-{uuid4().hex[:16]}"
        if self.store.exists(run_id):
            raise ValueError(f"run_id already exists: {run_id}")
        plan = self.planner.plan_exact_pair(
            kalshi_identifier=kalshi_identifier,
            polymarket_identifier=polymarket_identifier,
            target_contracts=target_contracts,
            fee_model=fee_model,
            latency_buffer_bps=latency_buffer_bps,
            estimated_total_cost_per_basket=estimated_total_cost_per_basket,
        )
        now = _utc_now()
        run = {
            "artifact_type": "r12_strategy_agent_run",
            "run_id": run_id,
            "status": "RUNNING",
            "created_at": now,
            "updated_at": now,
            "plan": plan.to_dict(),
            "results": {},
            "task_traces": {},
            "events": [],
            "checkpoints": [],
            "next_task_id": "K1",
            "approval": None,
            "final_artifact": None,
            "execution_context": {
                "tenant_id": "demo-tenant",
                "user_id": "local-human-reviewer",
                "agent_id": "r12-strategy-agent",
                "task_id": run_id,
                "trace_id": f"{run_id}-trace",
            },
            "guardrails": {
                "tools_execute_through_shared_agent_runtime": True,
                "human_identity_approval_required": True,
                "parser_can_check_human_attestation": False,
                "completed_tasks_reexecute_on_resume": False,
                "workflow_tools_are_read_or_compute_only": True,
                "automatic_execution": False,
            },
        }
        self._checkpoint(run, "run_created")
        return self._advance(run, crash_after_completed_tasks=crash_after_completed_tasks)

    @_serialized
    def get(self, run_id: str) -> dict:
        run = self.store.load(run_id)
        if run is None:
            raise KeyError(f"R12 Strategy Agent run not found: {run_id}")
        return run

    @_serialized
    def resume(self, run_id: str, *, crash_after_completed_tasks: int | None = None) -> dict:
        run = self.store.load(run_id)
        if run is None:
            raise KeyError(f"R12 Strategy Agent run not found: {run_id}")
        if run["status"] in TERMINAL_RUN_STATUSES or run["status"] == "WAITING_HUMAN_IDENTITY_APPROVAL":
            return run
        return self._advance(run, crash_after_completed_tasks=crash_after_completed_tasks)

    @_serialized
    def approve_and_resume(self, run_id: str, attestation: dict) -> dict:
        run = self.store.load(run_id)
        if run is None:
            raise KeyError(f"R12 Strategy Agent run not found: {run_id}")
        if run["status"] in TERMINAL_RUN_STATUSES:
            return run
        if run["status"] != "WAITING_HUMAN_IDENTITY_APPROVAL":
            raise ValueError("run is not waiting for human identity approval")
        approval = _human_approval_artifact(run, attestation)
        run["approval"] = approval
        run["results"][HUMAN_GATE_TASK_ID] = approval
        task = _task_row(run, HUMAN_GATE_TASK_ID)
        task["status"] = "completed"
        task["result"] = deepcopy(approval)
        run["status"] = "RUNNING"
        self._event(run, "human_identity_approved", task_id=HUMAN_GATE_TASK_ID)
        self._checkpoint(run, "after_human_identity_approval")
        return self._advance(run)

    def _advance(self, run: dict, *, crash_after_completed_tasks: int | None = None) -> dict:
        completed_this_call = 0
        while True:
            next_task = _next_unfinished_task(run)
            if next_task is None:
                run["status"] = "COMPLETED_PAPER_QUOTE"
                run["next_task_id"] = None
                run["plan"]["status"] = "completed"
                run["final_artifact"] = deepcopy(run["results"].get("E1"))
                self._event(run, "strategy_agent_completed")
                self._checkpoint(run, "run_completed")
                return deepcopy(run)

            task_id = next_task["task_id"]
            run["next_task_id"] = task_id
            if task_id == HUMAN_GATE_TASK_ID:
                rules = run["results"].get("R1") or {}
                if not rules.get("eligible_for_identity_review"):
                    next_task["status"] = "blocked"
                    run["status"] = "BLOCKED_RULES_ANALYSIS"
                    run["plan"]["status"] = "blocked"
                    self._event(run, "rules_analysis_blocked", task_id=task_id)
                    self._checkpoint(run, "rules_analysis_blocked")
                    return deepcopy(run)
                next_task["status"] = "waiting_approval"
                run["status"] = "WAITING_HUMAN_IDENTITY_APPROVAL"
                run["plan"]["status"] = "waiting_approval"
                self._event(run, "human_identity_approval_required", task_id=task_id)
                self._checkpoint(run, "before_human_identity_approval")
                return deepcopy(run)

            resolved_arguments = _resolve_arguments(next_task.get("arguments"), run["results"])
            next_task["status"] = "running"
            run["plan"]["status"] = "running"
            self._event(run, "task_started", task_id=task_id, tool_name=next_task["tool_name"])
            self._checkpoint(run, f"before_{task_id}")
            result, trace, error = self._run_tool_task(run, next_task, resolved_arguments)
            run["task_traces"][task_id] = trace
            if error is not None:
                next_task["status"] = "failed"
                next_task["error"] = error
                run["status"] = "FAILED_TOOL_EXECUTION"
                run["plan"]["status"] = "failed"
                self._event(run, "task_failed", task_id=task_id, tool_name=next_task["tool_name"])
                self._checkpoint(run, f"failed_{task_id}")
                return deepcopy(run)

            next_task["status"] = "completed"
            next_task["result"] = deepcopy(result)
            run["results"][task_id] = deepcopy(result)
            self._event(run, "task_completed", task_id=task_id, tool_name=next_task["tool_name"])
            self._checkpoint(run, f"after_{task_id}")
            completed_this_call += 1

            if task_id == "I1" and not result.get("settlement_compatible_for_rv"):
                run["status"] = "BLOCKED_IDENTITY_REJECTED"
                run["plan"]["status"] = "blocked"
                self._event(run, "identity_rejected", task_id=task_id)
                self._checkpoint(run, "identity_rejected")
                return deepcopy(run)

            if crash_after_completed_tasks is not None and completed_this_call >= crash_after_completed_tasks:
                raise R12SimulatedOrchestratorCrash(
                    f"simulated crash after durable completion of {task_id}"
                )

    def _run_tool_task(self, run: dict, task_row: dict, arguments: dict) -> tuple[Any, dict, dict | None]:
        task = PlanTask(
            task_id=task_row["task_id"],
            title=task_row["title"],
            tool_name=task_row["tool_name"],
            arguments=arguments,
            depends_on=list(task_row.get("depends_on") or []),
        )
        context_row = run["execution_context"]
        context = ExecutionContext(
            tenant_id=context_row["tenant_id"],
            user_id=context_row["user_id"],
            agent_id=context_row["agent_id"],
            task_id=f"{run['run_id']}:{task.task_id}",
            trace_id=f"{context_row['trace_id']}:{task.task_id}",
        )
        state_store = InMemoryStateStore()
        trace = TraceRecorder(context.trace_id)
        span_id = trace.start_span(
            f"r12_strategy_task.{task.task_id}",
            task_id=task.task_id,
            attributes={"tool_name": task.tool_name, "depends_on": list(task.depends_on)},
        )

        def on_event(event: dict) -> None:
            trace.observe_runtime_event(event)
            if event.get("type") in {"tool_attempt", "tool_retry", "tool_error", "runtime_stop"}:
                self._event(
                    run,
                    f"runtime_{event.get('type')}",
                    task_id=task.task_id,
                    tool_name=task.tool_name,
                )

        answer = run_agent(
            task.title,
            model=PlannedTaskModel(task, arguments),
            on_event=on_event,
            max_steps=2,
            execution_context=context,
            state_store=state_store,
        )
        state = state_store.load(context.task_id)
        if state is None:
            error = {"code": "missing_task_state", "message": "Task Runtime produced no state snapshot"}
            trace.end_span(span_id, status="error", attributes={"error": error["code"]})
            return None, trace.summary(), error
        result = state.last_observation
        if state.status != "completed" or (isinstance(result, dict) and "error" in result):
            error = (
                result.get("error")
                if isinstance(result, dict) and isinstance(result.get("error"), dict)
                else {"code": "task_runtime_failed", "message": answer}
            )
            trace.end_span(span_id, status="error", attributes={"error": error.get("code")})
            return result, trace.summary(), error
        trace.end_span(span_id, status="ok", attributes={"result_artifact": _artifact_type(result)})
        return result, trace.summary(), None

    def _event(self, run: dict, event_type: str, **fields) -> None:
        run["events"].append(
            {
                "sequence": len(run["events"]) + 1,
                "at": _utc_now(),
                "type": event_type,
                **fields,
            }
        )

    def _checkpoint(self, run: dict, boundary: str) -> None:
        run["updated_at"] = _utc_now()
        run["checkpoints"].append(
            {
                "checkpoint_id": f"ACP-{len(run['checkpoints']) + 1:03d}",
                "boundary": boundary,
                "at": run["updated_at"],
                "run_status": run["status"],
                "completed_task_ids": sorted(run["results"]),
                "next_task_id": run.get("next_task_id"),
                "durable": True,
                "automatic_execution": False,
            }
        )
        self.store.save(run)


def evaluate_r12_strategy_agent_run(run: dict) -> dict:
    """Deterministic Step 6 eval contract for orchestration safety."""
    _validate_run_artifact(run)
    tasks = {row.get("task_id"): row for row in (run.get("plan") or {}).get("tasks") or []}
    results = run.get("results") or {}
    waiting = run.get("status") == "WAITING_HUMAN_IDENTITY_APPROVAL"
    identity = results.get("I1") or {}
    approval = results.get(HUMAN_GATE_TASK_ID) or {}
    rules = results.get("R1") or {}
    checks = {
        "plan_contains_explicit_human_gate": HUMAN_GATE_TASK_ID in tasks,
        "rules_precede_human_gate": (tasks.get(HUMAN_GATE_TASK_ID) or {}).get("depends_on") == ["R1"],
        "identity_depends_on_human_gate": HUMAN_GATE_TASK_ID in ((tasks.get("I1") or {}).get("depends_on") or []),
        "waiting_run_has_no_identity_result": not waiting or "I1" not in results,
        "human_approval_bound_to_rules_analysis": not approval or (
            approval.get("rules_analysis_id") == rules.get("analysis_id")
            and approval.get("contract_fingerprints")
            == {
                provider: ((rules.get("contracts") or {}).get(provider) or {}).get("fingerprint")
                for provider in ("kalshi", "polymarket")
            }
        ),
        "completed_identity_is_human_attested": not identity or bool((identity.get("manual_attestation") or {}).get("complete")),
        "durable_checkpoint_present": bool(run.get("checkpoints")) and all(row.get("durable") for row in run.get("checkpoints") or []),
        "runtime_trace_present_for_completed_tools": all(task_id in (run.get("task_traces") or {}) for task_id in results if task_id != HUMAN_GATE_TASK_ID),
        "automatic_execution_disabled": (run.get("guardrails") or {}).get("automatic_execution") is False,
    }
    return {
        "artifact_type": "r12_strategy_agent_eval",
        "run_id": run.get("run_id"),
        "checks": checks,
        "passed": all(checks.values()),
    }


def _human_approval_artifact(run: dict, attestation: dict) -> dict:
    if not isinstance(attestation, dict):
        raise ValueError("attestation must be an object")
    checks = {name: attestation.get(name) is True for name in IDENTITY_CHECKS}
    source = attestation.get("attestation_source")
    if not all(checks.values()) or not isinstance(source, str) or not source.strip():
        raise ValueError("all six identity checks and a non-empty attestation_source are required")
    rules = (run.get("results") or {}).get("R1") or {}
    if rules.get("status") != "RULES_ANALYSIS_READY_FOR_HUMAN_REVIEW":
        raise ValueError("current rules analysis is not ready for human approval")
    return {
        "artifact_type": "r12_human_identity_approval",
        "approval_id": f"APP-{uuid4().hex[:16]}",
        "run_id": run["run_id"],
        "rules_analysis_id": rules.get("analysis_id"),
        "contract_fingerprints": {
            provider: ((rules.get("contracts") or {}).get(provider) or {}).get("fingerprint")
            for provider in ("kalshi", "polymarket")
        },
        **checks,
        "attestation_source": source.strip(),
        "approved_at": _utc_now(),
        "approved_by": "local-human-reviewer",
        "parser_checked_boxes": False,
        "automatic_execution": False,
    }


def _next_unfinished_task(run: dict) -> dict | None:
    tasks = (run.get("plan") or {}).get("tasks") or []
    complete = {row.get("task_id") for row in tasks if row.get("status") == "completed"}
    if len(complete) == len(tasks):
        return None
    for row in tasks:
        if row.get("status") == "completed":
            continue
        if row.get("status") in {"failed", "blocked"}:
            return None
        if all(dependency in complete for dependency in row.get("depends_on") or []):
            if row.get("status") == "running":
                row["status"] = "pending"
            return row
    raise RuntimeError("Strategy Agent plan has unfinished tasks but no dependency-ready task")


def _resolve_arguments(value, results: dict[str, Any]):
    if isinstance(value, dict):
        if set(value) == {"from_task"}:
            task_id = value["from_task"]
            if task_id not in results:
                raise RuntimeError(f"Cannot resolve unfinished Strategy Agent task {task_id}")
            return deepcopy(results[task_id])
        return {key: _resolve_arguments(item, results) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_arguments(item, results) for item in value]
    return deepcopy(value)


def _task_row(run: dict, task_id: str) -> dict:
    for row in (run.get("plan") or {}).get("tasks") or []:
        if row.get("task_id") == task_id:
            return row
    raise KeyError(f"Unknown Strategy Agent task: {task_id}")


def _validate_run_artifact(run: dict) -> None:
    if not isinstance(run, dict) or run.get("artifact_type") != "r12_strategy_agent_run":
        raise ValueError("run must be an r12_strategy_agent_run artifact")
    _required_text(run.get("run_id"), "run.run_id")
    if not isinstance(run.get("plan"), dict) or not isinstance(run.get("results"), dict):
        raise ValueError("run must contain plan and results objects")


def _required_text(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _positive_number(value, label: str) -> float:
    number = _non_negative_number(value, label)
    if number <= 0:
        raise ValueError(f"{label} must be > 0")
    return number


def _non_negative_number(value, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not isfinite(number) or number < 0:
        raise ValueError(f"{label} must be finite and >= 0")
    return number


def _explicit_fee_model(value) -> dict:
    if not isinstance(value, dict):
        raise ValueError("fee_model must be an explicit object")
    source = _required_text(value.get("source"), "fee_model.source")
    normalized = {"source": source}
    for provider in ("kalshi", "polymarket"):
        row = value.get(provider)
        if not isinstance(row, dict):
            raise ValueError(f"fee_model.{provider} must be an object")
        normalized[provider] = {
            field: _non_negative_number(row.get(field, 0.0), f"fee_model.{provider}.{field}")
            for field in ("fee_rate_on_notional", "fee_per_contract", "fixed_fee_per_order")
        }
    return normalized


def _artifact_type(value) -> str:
    return value.get("artifact_type", "dict") if isinstance(value, dict) else type(value).__name__


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
