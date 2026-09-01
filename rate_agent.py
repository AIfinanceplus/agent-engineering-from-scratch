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
from datetime import date, timedelta
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
    ) -> dict:
        start_date = start_date or (date.today() - timedelta(days=1_095)).isoformat()
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

        def emit(event: str, **payload) -> None:
            trace.append({"sequence": len(trace) + 1, "event": event, **payload})

        emit("goal_received", task_id="G1", goal="one auditable 2s10s paper simulation")
        emit(
            "plan_created",
            task_id="P1",
            planner="fixed_two_tool_dag",
            task_ids=[task["task_id"] for task in plan],
        )
        emit(
            "runtime_started",
            task_id="R1",
            model="none_deterministic_v1",
            registry_tools=[task["tool_name"] for task in plan],
        )
        for task in plan:
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
            )
            emit(
                "task_completed",
                task_id=task["task_id"],
                tool_name=tool.name,
                status="COMPLETED",
            )

        history = observations["D1"]
        simulation = observations["S1"]
        emit("eval_started", task_id="E1", evaluator="evaluate_rate_simulation")
        evaluation = evaluate_rate_simulation(simulation)
        emit(
            "eval_completed",
            task_id="E1",
            artifact_type=evaluation["artifact_type"],
            passed=evaluation["passed"],
        )
        emit("run_completed", task_id="END", status="COMPLETED_ONE_PAPER_SIMULATION")
        run_fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "config": simulation["configuration"],
                    "data_as_of": history["as_of"],
                    "trade": simulation["completed_trade"]["paper_trade_id"],
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()[:16]
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
            "run_id": f"RATE-RUN-{run_fingerprint}",
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
            "checkpoints": [],
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
