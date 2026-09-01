"""Lesson: bounded fan-out / all-success fan-in, with one event-stream writer.

D1 keeps the resilient bulk download. A2 and A10 independently validate and
prepare the two series. Only their joined output can feed S1. Workers never
mutate run state or write HTTP: a Queue hands their events back to the owner.
This is concurrent scheduling, not a claim of Python CPU parallel speedup.
"""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from math import isfinite
from queue import Queue
import time
from uuid import uuid4

from rate_sources import load_bundled_rate_history
from rate_strategy import evaluate_rate_simulation
from rate_tooling import register_rate_tools
from tools import TOOL_REGISTRY, Tool, resolve_tool


SCENARIOS = {"live", "two_year_slow", "ten_year_slow", "ten_year_fail"}
GRAPH_ROWS = [["G1"], ["P1"], ["R1"], ["D1"], ["A2", "A10"], ["J1"], ["S1"], ["E1"]]
GRAPH_EDGES = [["G1", "P1"], ["P1", "R1"], ["R1", "D1"],
               ["D1", "A2"], ["D1", "A10"], ["A2", "J1"],
               ["A10", "J1"], ["J1", "S1"], ["S1", "E1"]]


def prepare_rate_series(history: dict, series_id: str, batch_id: str) -> dict:
    """Independent read-only task. Its real output is required by the Join."""
    if history.get("artifact_type") != "rate_curve_history":
        raise ValueError("history must be rate_curve_history")
    if series_id not in {"DGS2", "DGS10"}:
        raise ValueError("series_id must be DGS2 or DGS10")
    if not batch_id:
        raise ValueError("batch_id must identify the current run")
    values = []
    previous = None
    for row in history.get("observations", []):
        period = row["date"]
        if date.fromisoformat(period).isoformat() != period or (previous and period <= previous):
            raise ValueError("series dates must be unique and strictly increasing")
        value = row[series_id.lower()]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            raise ValueError(f"{series_id} has a non-finite or non-numeric value")
        values.append({"date": period, "value": value})
        previous = period
    if not values:
        raise ValueError("series must not be empty")
    fingerprint = hashlib.sha256(json.dumps(history, sort_keys=True).encode()).hexdigest()
    return {
        "artifact_type": "prepared_rate_series", "series_id": series_id,
        "batch_id": batch_id, "source_fingerprint": fingerprint,
        "source": {key: deepcopy(value) for key, value in history.items() if key != "observations"},
        "observations": values,
        "summary": {"count": len(values), "first_date": values[0]["date"],
                    "last_date": values[-1]["date"], "latest_yield_pct": values[-1]["value"]},
    }


def join_rate_series(two_year: dict, ten_year: dict) -> dict:
    """All-success Join: do not fabricate a missing branch or mix source batches."""
    for part, series_id in ((two_year, "DGS2"), (ten_year, "DGS10")):
        if part.get("artifact_type") != "prepared_rate_series" or part.get("series_id") != series_id:
            raise ValueError(f"join requires the completed {series_id} branch")
    if not two_year.get("batch_id") or two_year["batch_id"] != ten_year.get("batch_id"):
        raise ValueError("cannot join branches from different runs")
    if not two_year.get("source_fingerprint") or two_year["source_fingerprint"] != ten_year.get("source_fingerprint"):
        raise ValueError("cannot join different source snapshots")
    left = {row["date"]: row["value"] for row in two_year["observations"]}
    right = {row["date"]: row["value"] for row in ten_year["observations"]}
    rows = [{"date": day, "dgs2": left[day], "dgs10": right[day],
             "spread_bps": round((right[day] - left[day]) * 100, 6)}
            for day in sorted(left.keys() & right.keys())]
    if not rows:
        raise ValueError("branches have no common dates")
    history = deepcopy(two_year["source"])
    history.update(observations=rows, observation_count=len(rows), as_of=rows[-1]["date"])
    return history


PARALLEL_TOOLS = (
    Tool(name="prepare_rate_series", description="Validate and prepare one series from the shared batch, without external writes.",
         parameters={"type": "object", "properties": {
             "history": {"type": "object"}, "series_id": {"type": "string", "enum": ["DGS2", "DGS10"]},
             "batch_id": {"type": "string"}},
             "required": ["history", "series_id", "batch_id"], "additionalProperties": False},
         function=prepare_rate_series, max_retries=0, risk="low"),
    Tool(name="join_rate_series", description="Join two successful branches from the same run and source snapshot.",
         parameters={"type": "object", "properties": {"two_year": {"type": "object"}, "ten_year": {"type": "object"}},
                     "required": ["two_year", "ten_year"], "additionalProperties": False},
         function=join_rate_series, max_retries=0, risk="low"),
)


class ParallelRunError(RuntimeError):
    def __init__(self, message, task_id, trace, failures=None):
        super().__init__(message)
        self.task_id = task_id
        self.trace = deepcopy(trace)
        self.failures = dict(failures or {})


class RateParallelAgent:
    def __init__(self, tool_overrides=None, *, sleeper=time.sleep):
        register_rate_tools()
        for tool in PARALLEL_TOOLS:
            if tool.name in TOOL_REGISTRY and TOOL_REGISTRY[tool.name] != tool:
                raise RuntimeError(f"Tool Registry collision for {tool.name}")
            TOOL_REGISTRY[tool.name] = tool
        self.overrides = dict(tool_overrides or {})
        self.sleep = sleeper

    def run_once(self, *, lookback_days=60, entry_z=1.0, holding_days=20,
                 dv01_usd_per_bp=100.0, round_trip_cost_bps=1.0, start_date=None,
                 run_id=None, event_sink=None, demo_scenario="live"):
        if demo_scenario not in SCENARIOS:
            raise ValueError("unknown parallel demo_scenario")
        run_id = run_id or f"RATE-RUN-{uuid4().hex[:16]}"
        start_date = start_date or (date.today() - timedelta(days=1095)).isoformat()
        configuration = dict(lookback_days=lookback_days, entry_z=entry_z,
                             holding_days=holding_days, dv01_usd_per_bp=dv01_usd_per_bp,
                             round_trip_cost_bps=round_trip_cost_bps)
        trace, observations = [], {}
        current_task = "G1"
        plan = [
            {"task_id": "D1", "tool_name": "fetch_public_rate_history", "depends_on": []},
            {"task_id": "A2", "tool_name": "prepare_rate_series", "depends_on": ["D1"]},
            {"task_id": "A10", "tool_name": "prepare_rate_series", "depends_on": ["D1"]},
            {"task_id": "J1", "tool_name": "join_rate_series", "depends_on": ["A2", "A10"]},
            {"task_id": "S1", "tool_name": "simulate_one_curve_trade", "depends_on": ["J1"]},
        ]
        by_id = {task["task_id"]: task for task in plan}

        def emit(event, **payload):
            row = deepcopy({"sequence": len(trace) + 1, "run_id": run_id,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "event": event, **payload})
            trace.append(row)
            if event_sink:
                event_sink(deepcopy(row))

        def call(task_id, arguments, publish=emit):
            task = by_id[task_id]
            name = task["tool_name"]
            publish("task_started", task_id=task_id, tool_name=name, depends_on=task["depends_on"])
            tool = resolve_tool(name)
            publish("tool_lookup", task_id=task_id, tool_name=name, found=tool is not None)
            if tool is None:
                raise RuntimeError(f"missing Tool {name}")
            validation = tool.validate(arguments)
            publish("tool_validation", task_id=task_id, tool_name=name,
                    passed=validation.get("ok") is True, validation=validation)
            if not validation.get("ok"):
                raise ValueError(validation["error"]["message"])
            function = self.overrides.get(name, tool.function)
            if task_id == "D1" and demo_scenario != "live":
                function = load_bundled_rate_history
            for attempt in range(1, tool.max_retries + 2):
                publish("tool_execution_started", task_id=task_id, tool_name=name,
                        arguments=arguments, attempt=attempt, max_attempts=tool.max_retries + 1,
                        max_retries=tool.max_retries, risk=tool.risk)
                try:
                    if task_id in {"A2", "A10"} and demo_scenario != "live":
                        slow = "A10" if demo_scenario == "ten_year_slow" else "A2"
                        delay_ms = 2000 if task_id == slow else 400
                        publish("demo_delay_started", task_id=task_id, delay_ms=delay_ms,
                                demo=True, reason="教学延时；不是网络耗时")
                        self.sleep(delay_ms / 1000)
                        if demo_scenario == "ten_year_fail" and task_id == "A10":
                            raise ValueError("教学故障注入：10Y 分支失败；未伪造数据")
                    output = function(**arguments)
                except Exception as exc:
                    retryable = isinstance(exc, tool.retryable_errors) and attempt <= tool.max_retries
                    publish("tool_execution_failed", task_id=task_id, tool_name=name,
                            attempt=attempt, error_type=type(exc).__name__, error_message=str(exc), retryable=retryable)
                    if not retryable:
                        raise
                    delay_ms = 250 * 2 ** (attempt - 1)
                    publish("tool_retry_scheduled", task_id=task_id, tool_name=name,
                            next_attempt=attempt + 1, delay_ms=delay_ms)
                    self.sleep(delay_ms / 1000)
                    continue
                if task_id == "D1":
                    for source in output.get("source_attempts", []):
                        publish("data_source_attempt", task_id="D1", **source)
                publish("tool_observation", task_id=task_id, tool_name=name,
                        artifact_type=output.get("artifact_type"), output=output, status="COMPLETED")
                publish("task_completed", task_id=task_id, tool_name=name, status="COMPLETED")
                return output

        try:
            emit("goal_received", task_id="G1", goal="one auditable 2s10s paper simulation",
                 configuration={**configuration, "start_date": start_date}, demo_scenario=demo_scenario)
            emit("plan_created", task_id="P1", planner="bounded_fanout_all_success_join",
                 task_ids=list(by_id), tasks=plan, graph={"rows": GRAPH_ROWS, "edges": GRAPH_EDGES})
            emit("runtime_started", task_id="R1", model="none_deterministic_v1", max_workers=2,
                 registry_tools=list(dict.fromkeys(t["tool_name"] for t in plan)))
            if demo_scenario != "live":
                emit("demo_scenario_selected", task_id="R1", scenario=demo_scenario,
                     source_freshness="SNAPSHOT", teaching_delay=True,
                     message="明确的离线教学演示；Tool 真正执行，延时/故障由教学模式注入。")
            current_task = "D1"
            observations["D1"] = call("D1", {"start_date": start_date})
            emit("parallel_group_started", task_id="R1", task_ids=["A2", "A10"], max_workers=2)
            emit("join_waiting", task_id="J1", completed_dependencies=[], waiting_for=["A2", "A10"], required=2)
            queue = Queue()

            def worker(task_id, series_id):
                def publish(event, **payload):
                    queue.put(("event", event, deepcopy({"timestamp": datetime.now(timezone.utc).isoformat(), **payload})))
                try:
                    output = call(task_id, {"history": deepcopy(observations["D1"]),
                                           "series_id": series_id, "batch_id": run_id}, publish)
                    queue.put(("done", task_id, (output, None)))
                except Exception as exc:
                    publish("task_failed", task_id=task_id, error_type=type(exc).__name__, error_message=str(exc))
                    queue.put(("done", task_id, (None, exc)))

            failures, finished = {}, set()
            # Workers are read-only; let any in-flight sibling finish after failure.
            # Only this owner loop updates observations or writes the event stream.
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="rate-branch") as pool:
                pool.submit(worker, "A2", "DGS2")
                pool.submit(worker, "A10", "DGS10")
                while len(finished) < 2:
                    kind, key, payload = queue.get()
                    if kind == "event":
                        emit(key, **payload)
                        continue
                    finished.add(key)
                    output, error = payload
                    if error:
                        failures[key] = str(error)
                        emit("join_blocked", task_id="J1", failed_dependencies=list(failures),
                             reason="all_success requires both branches; no partial strategy run")
                        for downstream in ("S1", "E1"):
                            emit("task_blocked", task_id=downstream, reason="J1 cannot complete")
                    else:
                        observations[key] = output
                        if not failures:
                            emit("join_waiting", task_id="J1",
                                 completed_dependencies=[key for key in ("A2", "A10") if key in observations],
                                 waiting_for=[key for key in ("A2", "A10") if key not in observations], required=2)
            if failures:
                raise ParallelRunError("并行分支失败；Join、S1 和 E1 未执行。", next(iter(failures)), trace, failures)
            emit("join_released", task_id="J1", completed_dependencies=["A2", "A10"], required=2)
            current_task = "J1"
            observations["J1"] = call("J1", {"two_year": observations["A2"], "ten_year": observations["A10"]})
            current_task = "S1"
            observations["S1"] = call("S1", {"history": observations["J1"], **configuration})
            current_task = "E1"
            emit("eval_started", task_id="E1", evaluator="evaluate_rate_simulation", arguments={"simulation": observations["S1"]})
            evaluation = evaluate_rate_simulation(observations["S1"])
            emit("eval_completed", task_id="E1", passed=evaluation["passed"], output=evaluation,
                 artifact_type=evaluation["artifact_type"])
            emit("run_completed", task_id="END", status="COMPLETED_ONE_PAPER_SIMULATION")
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            raise
        except ParallelRunError:
            raise
        except Exception as exc:
            emit("task_failed", task_id=current_task, error_type=type(exc).__name__, error_message=str(exc))
            raise ParallelRunError(str(exc), current_task, trace) from exc
        return {
            "artifact_type": "rate_strategy_agent_run", "run_id": run_id,
            "status": "COMPLETED_ONE_PAPER_SIMULATION", "trace": trace,
            "plan": {"artifact_type": "rate_strategy_plan", "status": "completed",
                     "tasks": [{**task, "status": "completed"} for task in plan]},
            "data": observations["J1"], "simulation": observations["S1"], "eval": evaluation,
            "observations": observations,
            "state": {"phase": "completed", "completed_tasks": [*by_id, "E1"]},
            "architecture": {"planner": "bounded_fanout_all_success_join", "model": "none_deterministic_v1",
                             "max_workers": 2, "join_policy": "all_success", "stream_writer": "owner_thread"},
            "lesson": {"topic": "fan_out_fan_in", "demo_scenario": demo_scenario,
                       "teaching_delay": demo_scenario != "live", "graph": {"rows": GRAPH_ROWS, "edges": GRAPH_EDGES}},
            "guardrails": {"paper_only": True, "broker_connection": False, "automatic_execution": False,
                           "partial_join_allowed": False, "concurrent_external_writes": False},
        }
