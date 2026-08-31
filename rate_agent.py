"""A deliberately small deterministic Agent for one rate-strategy simulation.

The Planner is a fixed two-Tool DAG.  The Runtime resolves each capability from
the shared Tool Registry, validates arguments, records the Observation, and then
runs an Eval.  There is no LLM planning in V1; that keeps the first learning loop
auditable and repeatable.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import date, timedelta
from typing import Callable

from rate_strategy import evaluate_rate_simulation
from rate_tooling import register_rate_tools
from tools import resolve_tool


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
        for task in plan:
            arguments = _resolve_arguments(task["arguments"], observations)
            tool = resolve_tool(task["tool_name"])
            if tool is None:
                raise RuntimeError(f"Tool Registry missing {task['tool_name']}")
            validation = tool.validate(arguments)
            trace.append(
                {
                    "event": "tool_validation",
                    "task_id": task["task_id"],
                    "tool_name": tool.name,
                    "passed": validation.get("ok") is True,
                }
            )
            if not validation.get("ok"):
                raise ValueError(validation["error"]["message"])
            function = self.tool_overrides.get(tool.name, tool.function)
            observation = function(**arguments)
            observations[task["task_id"]] = observation
            trace.append(
                {
                    "event": "tool_observation",
                    "task_id": task["task_id"],
                    "tool_name": tool.name,
                    "artifact_type": observation.get("artifact_type"),
                    "status": "COMPLETED",
                }
            )

        history = observations["D1"]
        simulation = observations["S1"]
        evaluation = evaluate_rate_simulation(simulation)
        trace.append(
            {
                "event": "eval_completed",
                "task_id": "E1",
                "artifact_type": evaluation["artifact_type"],
                "passed": evaluation["passed"],
            }
        )
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
        return {
            "artifact_type": "rate_strategy_agent_run",
            "run_id": f"RATE-RUN-{run_fingerprint}",
            "status": "COMPLETED_ONE_PAPER_SIMULATION",
            "goal": "Run one auditable U.S. Treasury 2s10s mean-reversion paper simulation",
            "plan": deepcopy(plan),
            "data": history,
            "simulation": simulation,
            "eval": evaluation,
            "trace": trace,
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
