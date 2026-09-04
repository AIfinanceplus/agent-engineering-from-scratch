"""A deliberately small deterministic Agent for one rate-strategy simulation.

The Planner is a fixed two-Tool DAG.  The Runtime resolves each capability from
the shared Tool Registry, validates arguments, records the Observation, and then
runs an Eval.  There is no LLM planning in V1; that keeps the first learning loop
auditable and repeatable.
"""

from __future__ import annotations

import hashlib
import json
import time
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from typing import Callable

from rate_strategy import evaluate_rate_simulation
from rate_tooling import register_rate_tools
from tools import resolve_tool


class RateToolExecutionError(RuntimeError):
    """A Tool exhausted its declared retries; keep the partial trace inspectable."""

    def __init__(self, *, task_id: str, tool_name: str, attempts: int, cause: Exception, trace: list):
        super().__init__(
            f"{task_id} {tool_name} failed after {attempts} attempts: {cause}"
        )
        self.task_id = task_id
        self.tool_name = tool_name
        self.attempts = attempts
        self.error_type = cause.__class__.__name__
        self.transient = isinstance(cause, (ConnectionError, TimeoutError))
        self.trace = deepcopy(trace)


class RateSimulatedCrash(RuntimeError):
    """Teaching-only crash raised after a durable checkpoint has been written."""

    def __init__(self, *, run_id: str, task_id: str, trace: list):
        super().__init__(f"simulated process crash after checkpoint at {task_id}")
        self.run_id = run_id
        self.task_id = task_id
        self.trace = deepcopy(trace)


class RateStrategyAgent:
    def __init__(self, tool_overrides: dict[str, Callable] | None = None):
        register_rate_tools()
        self.tool_overrides = dict(tool_overrides or {})

    def run_once(
        self,
        *,
        lookback_days: int = 60,
        entry_z: float = 1.0,
        holding_days: int = 20,
        dv01_usd_per_bp: float = 100.0,
        round_trip_cost_bps: float = 1.0,
        start_date: str | None = None,
        run_id: str | None = None,
        checkpoint_store=None,
        resume: bool = False,
        crash_after_task: str | None = None,
        event_sink=None,
    ) -> dict:
        start_date = start_date or (date.today() - timedelta(days=1_095)).isoformat()
        configuration = {
            "lookback_days": lookback_days,
            "entry_z": entry_z,
            "holding_days": holding_days,
            "dv01_usd_per_bp": dv01_usd_per_bp,
            "round_trip_cost_bps": round_trip_cost_bps,
            "start_date": start_date,
        }
        run_id = run_id or _stable_rate_run_id(configuration)
        plan = [
            {
                "task_id": "D1",
                "title": "Fetch and align public DGS2 / DGS10 observations",
                "tool_name": "fetch_public_rate_history",
                "arguments": {"start_date": start_date},
                "depends_on": [],
            },
            {
                "task_id": "S1",
                "title": "Generate signal and close one historical paper trade",
                "tool_name": "simulate_one_curve_trade",
                "arguments": {
                    "history": {"from_task": "D1"},
                    "lookback_days": lookback_days,
                    "entry_z": entry_z,
                    "holding_days": holding_days,
                    "dv01_usd_per_bp": dv01_usd_per_bp,
                    "round_trip_cost_bps": round_trip_cost_bps,
                },
                "depends_on": ["D1"],
            },
        ]
        observations: dict[str, dict] = {}
        trace = []
        checkpoints: list[dict] = []
        completed_task_ids: set[str] = set()

        def emit(event: str, **payload) -> None:
            # Capture values at the event boundary, not mutable Tool references.
            row = deepcopy({"sequence": len(trace) + 1, "event": event,
                            "run_id": run_id,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            **payload})
            trace.append(row)
            if event_sink is not None:
                event_sink(deepcopy(row))

        def persist_checkpoint(boundary: str, next_task: str | None) -> None:
            if checkpoint_store is None:
                return
            checkpoint_id = f"CP-{len(checkpoints) + 1:03d}"
            emit(
                "checkpoint_saved",
                task_id=next_task or "END",
                checkpoint_id=checkpoint_id,
                boundary=boundary,
                next_task=next_task,
            )
            checkpoint_plan = deepcopy(plan)
            for checkpoint_task in checkpoint_plan:
                task_id = checkpoint_task["task_id"]
                checkpoint_task["status"] = (
                    "completed" if task_id in completed_task_ids
                    else "ready" if task_id == next_task
                    else "pending"
                )
            checkpoint = {
                "checkpoint_id": checkpoint_id,
                "run_id": run_id,
                "boundary": boundary,
                "durable": True,
                "restore_enabled": True,
                "configuration": deepcopy(configuration),
                "next_task": next_task,
                "completed_task_ids": sorted(completed_task_ids),
                "plan": checkpoint_plan,
                "observations": deepcopy(observations),
                "trace": deepcopy(trace),
            }
            checkpoint_store.save(checkpoint)
            checkpoints.append(checkpoint)

        if resume:
            if checkpoint_store is None:
                raise RuntimeError("resume requires a checkpoint_store")
            loaded = checkpoint_store.load(run_id)
            if loaded is None:
                raise RuntimeError(f"no checkpoint found for {run_id}")
            if loaded.get("configuration") != configuration:
                raise RuntimeError("checkpoint configuration does not match resume request")
            observations = deepcopy(loaded.get("observations") or {})
            trace = deepcopy(loaded.get("trace") or [])
            checkpoints = deepcopy(checkpoint_store.history(run_id))
            completed_task_ids = set(loaded.get("completed_task_ids") or [])
            emit(
                "checkpoint_loaded",
                task_id=loaded.get("next_task") or "END",
                checkpoint_id=loaded.get("checkpoint_id"),
                boundary=loaded.get("boundary"),
                completed_tasks=sorted(completed_task_ids),
            )
            emit(
                "resume_boundary",
                task_id=loaded.get("next_task") or "END",
                resume_candidate=loaded.get("next_task"),
                skipped_tasks=sorted(completed_task_ids),
            )
            emit(
                "process_restarted",
                task_id=loaded.get("next_task") or "END",
                previous_checkpoint=loaded.get("checkpoint_id"),
            )

        if not resume:
            emit("goal_received", task_id="G1", goal="one auditable 2s10s paper simulation",
                 configuration=configuration)
            emit(
                "plan_created",
                task_id="P1",
                planner="fixed_two_tool_dag",
                task_ids=[task["task_id"] for task in plan],
                tasks=plan,
            )
            emit(
                "runtime_started",
                task_id="R1",
                model="none_deterministic_v1",
                registry_tools=[task["tool_name"] for task in plan],
            )
            persist_checkpoint("after_plan_created", "D1")
        for task in plan:
            if task["task_id"] in completed_task_ids:
                emit(
                    "task_skipped_from_checkpoint",
                    task_id=task["task_id"],
                    tool_name=task["tool_name"],
                    reason="durably_completed",
                )
                continue
            arguments = _resolve_arguments(task["arguments"], observations)
            emit(
                "task_started",
                task_id=task["task_id"],
                tool_name=task["tool_name"],
                depends_on=task["depends_on"],
            )
            tool = resolve_tool(task["tool_name"])
            emit(
                "tool_lookup",
                task_id=task["task_id"],
                tool_name=task["tool_name"],
                found=tool is not None,
            )
            if tool is None:
                raise RuntimeError(f"Tool Registry missing {task['tool_name']}")
            validation = tool.validate(arguments)
            emit(
                "tool_validation",
                task_id=task["task_id"],
                tool_name=tool.name,
                passed=validation.get("ok") is True,
                validation=validation,
            )
            if not validation.get("ok"):
                raise ValueError(validation["error"]["message"])
            function = self.tool_overrides.get(tool.name, tool.function)
            max_attempts = tool.max_retries + 1
            attempt = 1
            while True:
                emit(
                    "tool_execution_started",
                    task_id=task["task_id"],
                    tool_name=tool.name,
                    risk=tool.risk,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    max_retries=tool.max_retries,
                    arguments=arguments,
                )
                try:
                    observation = function(**arguments)
                    break
                except Exception as exc:
                    transient = isinstance(exc, (ConnectionError, TimeoutError))
                    will_retry = transient and attempt < max_attempts
                    emit(
                        "tool_execution_failed",
                        task_id=task["task_id"],
                        tool_name=tool.name,
                        attempt=attempt,
                        error_type=exc.__class__.__name__,
                        error_message=str(exc),
                        retryable=will_retry,
                    )
                    if not will_retry:
                        if not transient:
                            raise
                        raise RateToolExecutionError(
                            task_id=task["task_id"],
                            tool_name=tool.name,
                            attempts=attempt,
                            cause=exc,
                            trace=trace,
                        ) from exc
                    delay_ms = 250 * (2 ** (attempt - 1))
                    emit(
                        "tool_retry_scheduled",
                        task_id=task["task_id"],
                        tool_name=tool.name,
                        next_attempt=attempt + 1,
                        delay_ms=delay_ms,
                    )
                    time.sleep(delay_ms / 1000)
                    attempt += 1
            observations[task["task_id"]] = observation
            if task["task_id"] == "D1":
                for source_attempt in observation.get("source_attempts", []):
                    emit(
                        "data_source_attempt",
                        task_id="D1",
                        provider=source_attempt.get("provider"),
                        source_mode=source_attempt.get("source_mode"),
                        status=source_attempt.get("status"),
                        error_type=source_attempt.get("error_type"),
                        error_message=source_attempt.get("error_message"),
                    )
                if observation.get("fallback_used"):
                    emit(
                        "data_source_fallback_selected",
                        task_id="D1",
                        provider=observation.get("provider"),
                        source_mode=observation.get("source_mode"),
                        source_freshness=observation.get("source_freshness"),
                        as_of=observation.get("as_of"),
                    )
            emit(
                "tool_observation",
                task_id=task["task_id"],
                tool_name=tool.name,
                artifact_type=observation.get("artifact_type"),
                status="COMPLETED",
                output=observation,
            )
            emit(
                "task_completed",
                task_id=task["task_id"],
                tool_name=tool.name,
                status="COMPLETED",
            )
            completed_task_ids.add(task["task_id"])
            next_task = next(
                (candidate["task_id"] for candidate in plan
                 if candidate["task_id"] not in completed_task_ids),
                None,
            )
            persist_checkpoint(f"after_{task['task_id']}", next_task)
            if crash_after_task == task["task_id"]:
                raise RateSimulatedCrash(
                    run_id=run_id,
                    task_id=task["task_id"],
                    trace=trace,
                )

        history = observations["D1"]
        simulation = observations["S1"]
        emit("eval_started", task_id="E1", evaluator="evaluate_rate_simulation",
             arguments={"simulation": simulation})
        evaluation = evaluate_rate_simulation(simulation)
        emit(
            "eval_completed",
            task_id="E1",
            artifact_type=evaluation["artifact_type"],
            passed=evaluation["passed"],
            output=evaluation,
        )
        emit("run_completed", task_id="END", status="COMPLETED_ONE_PAPER_SIMULATION")
        persist_checkpoint("after_E1", None)
        latest = history["observations"][-1]
        evidence = [
            {
                "kind": "evidence",
                "evidence_id": series.get("evidence_id", f"FRED:{series['series_id']}"),
                "provider": series.get("provider", history.get("provider", "FRED")),
                "series_id": series["series_id"],
                "value": latest[series["series_id"].lower()],
                "unit": series["unit"],
                "as_of": history["as_of"],
                "source": {
                    "title": series["label"],
                    "publisher": series.get("publisher", "Federal Reserve Bank of St. Louis"),
                    "uri": series["source_url"],
                },
            }
            for series in history["series"]
        ]
        completed_plan = deepcopy(plan)
        for task in completed_plan:
            task["status"] = "completed"
        return {
            "artifact_type": "rate_strategy_agent_run",
            "run_id": run_id,
            "status": "COMPLETED_ONE_PAPER_SIMULATION",
            "goal": "Run one auditable U.S. Treasury 2s10s mean-reversion paper simulation",
            "plan": {
                "artifact_type": "rate_strategy_plan",
                "status": "completed",
                "tasks": completed_plan,
            },
            "data": history,
            "evidence": evidence,
            "simulation": simulation,
            "eval": evaluation,
            "trace": trace,
            "state": {
                "phase": "completed",
                "current_task": None,
                "completed_tasks": ["D1", "S1", "E1"],
                "observation_artifacts": [history["artifact_type"], simulation["artifact_type"]],
            },
            "checkpoints": checkpoints,
            "recovery": {
                "resumed": resume,
                "checkpoint_count": len(checkpoints),
                "d1_executions": 0 if resume else 1,
                "durable": checkpoint_store is not None,
            },
            "architecture": {
                "planner": "fixed_two_tool_dag",
                "runtime": "shared_tool_registry_plus_argument_validation",
                "tools": ["fetch_public_rate_history", "simulate_one_curve_trade"],
                "model": "none_deterministic_v1",
            },
            "guardrails": {
                "paper_only": True,
                "automatic_execution": False,
                "broker_connection": False,
            },
        }


def _resolve_arguments(arguments: dict, observations: dict[str, dict]) -> dict:
    resolved = {}
    for key, value in arguments.items():
        if isinstance(value, dict) and set(value) == {"from_task"}:
            task_id = value["from_task"]
            if task_id not in observations:
                raise RuntimeError(f"dependency {task_id} is not complete")
            resolved[key] = observations[task_id]
        else:
            resolved[key] = value
    return resolved


def _stable_rate_run_id(configuration: dict) -> str:
    fingerprint = hashlib.sha256(
        json.dumps(configuration, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    return f"RATE-RUN-{fingerprint}"
