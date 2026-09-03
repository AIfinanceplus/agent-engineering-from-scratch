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
from queue import Empty, Queue
import time
from uuid import uuid4

from rate_sources import load_bundled_rate_history
from rate_control import RunControl, RunStopped, check_run_control
from rate_resilience import AdmissionController, CircuitBreaker, CircuitOpen
from rate_strategy import evaluate_rate_simulation
from rate_tooling import register_rate_tools
from tools import TOOL_REGISTRY, Tool, resolve_tool


SCENARIOS = {"live", "two_year_slow", "ten_year_slow", "ten_year_fail", "deadline", "manual_cancel", "late_result",
             "breaker_open", "breaker_recovery", "backpressure", "overload_rejected"}
BREAKER_SCENARIOS = {"breaker_open", "breaker_recovery"}
ADMISSION_SCENARIOS = {"backpressure", "overload_rejected"}
TIMING_SCENARIOS = {"two_year_slow", "ten_year_slow", "ten_year_fail", "deadline", "manual_cancel", "late_result"}
GRAPH_ROWS = [["G1"], ["P1"], ["R1"], ["C1"], ["D1"], ["Q1"], ["A2", "A10"], ["J1"], ["S1"], ["E1"]]
GRAPH_EDGES = [["G1", "P1"], ["P1", "R1"], ["R1", "C1"], ["C1", "D1"], ["D1", "Q1"],
               ["Q1", "A2"], ["Q1", "A10"], ["A2", "J1"],
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
        check_run_control()
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
    check_run_control()
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


class RateRunStopped(RunStopped):
    def __init__(self, reason, trace):
        super().__init__(reason)
        self.task_id = "R1"
        self.trace = deepcopy(trace)
        self.code = "RUN_DEADLINE_EXCEEDED" if reason == "deadline" else "RUN_CANCELLED"


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
                 run_id=None, event_sink=None, demo_scenario="live", control=None):
        if demo_scenario not in SCENARIOS:
            raise ValueError("unknown parallel demo_scenario")
        control = control or RunControl()
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
        completed = set()
        inflight = set()
        stop_announced = False
        breaker = CircuitBreaker(
            failure_threshold=2,
            reset_timeout_ms=300 if demo_scenario == "breaker_recovery" else 30000,
        ) if demo_scenario in BREAKER_SCENARIOS else None
        injected_source_failures = 0

        def emit(event, **payload):
            row = deepcopy({"sequence": len(trace) + 1, "run_id": run_id,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "event": event, **payload})
            trace.append(row)
            if event_sink:
                event_sink(deepcopy(row))

        def announce_stop():
            nonlocal stop_announced
            info = control.snapshot()
            if not info["stop_requested"] or stop_announced:
                return
            stop_announced = True
            if info["reason"] == "deadline":
                emit("deadline_exceeded", task_id="R1", **info)
            emit("cancellation_requested", task_id="R1", active_tasks=sorted(inflight - completed), **info)
            for task_id in ["C1", "Q1", *by_id, "E1"]:
                if task_id not in completed and task_id not in inflight:
                    emit("task_blocked", task_id=task_id, reason="run stop requested")

        def call(task_id, arguments, publish=emit):
            nonlocal injected_source_failures
            control.check()
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
                if demo_scenario in BREAKER_SCENARIOS:
                    def breaker_demo_source(**kwargs):
                        nonlocal injected_source_failures
                        injected_source_failures += 1
                        if injected_source_failures <= 2:
                            raise ConnectionError(f"教学故障注入：上游连续失败 {injected_source_failures}/2")
                        return load_bundled_rate_history(**kwargs)
                    function = breaker_demo_source
                else:
                    function = load_bundled_rate_history
            for attempt in range(1, tool.max_retries + 2):
                control.check()
                if task_id == "D1" and breaker:
                    decision = breaker.before_call()
                    if decision.get("transition"):
                        publish("circuit_state_changed", task_id="C1", tool_name=name,
                                **decision["transition"], snapshot=decision)
                    if not decision["allowed"]:
                        publish("circuit_call_rejected", task_id="C1", tool_name=name,
                                attempt=attempt, snapshot=decision,
                                reason="OPEN circuit rejects the call before Tool execution")
                        raise CircuitOpen("fetch_public_rate_history circuit is OPEN; Tool was not called")
                    publish("circuit_call_allowed", task_id="C1", tool_name=name,
                            attempt=attempt, state=decision["state"], scope="single_teaching_run",
                            snapshot=decision)
                publish("tool_execution_started", task_id=task_id, tool_name=name,
                        arguments=arguments, attempt=attempt, max_attempts=tool.max_retries + 1,
                        max_retries=tool.max_retries, risk=tool.risk)
                try:
                    if task_id in {"A2", "A10"} and demo_scenario in TIMING_SCENARIOS | ADMISSION_SCENARIOS:
                        slow = "A10" if demo_scenario == "ten_year_slow" else "A2"
                        delay_ms = 350 if demo_scenario in ADMISSION_SCENARIOS else (2000 if task_id == slow else 400)
                        if demo_scenario == "manual_cancel":
                            delay_ms = 8000
                        if demo_scenario == "late_result":
                            delay_ms = 2400 if task_id == "A2" else 400
                        publish("demo_delay_started", task_id=task_id, delay_ms=delay_ms,
                                demo=True, reason="教学延时；不是网络耗时")
                        if demo_scenario == "late_result" and task_id == "A2":
                            # Explicit non-cooperative adapter demo: no stop checks
                            # during this bounded wait. Its output must be discarded.
                            publish("non_cooperative_wait", task_id=task_id, demo=True,
                                    delay_ms=delay_ms, reason="教学模拟：此等待不响应停止信号")
                            self.sleep(delay_ms / 1000)
                            return prepare_rate_series(arguments["history"], arguments["series_id"], arguments["batch_id"])
                        if self.sleep is time.sleep:
                            control.wait(delay_ms / 1000)
                        else:
                            self.sleep(delay_ms / 1000)
                            control.check()
                        if demo_scenario == "ten_year_fail" and task_id == "A10":
                            raise ValueError("教学故障注入：10Y 分支失败；未伪造数据")
                    with control.bind():
                        output = function(**arguments)
                except RunStopped:
                    raise
                except Exception as exc:
                    control.check()  # A stop request is not a retryable Tool failure.
                    if task_id == "D1" and breaker:
                        breaker_result = breaker.record_failure()
                        publish("circuit_failure_recorded", task_id="C1", tool_name=name,
                                error_type=type(exc).__name__, snapshot=breaker_result)
                        if breaker_result.get("transition"):
                            publish("circuit_state_changed", task_id="C1", tool_name=name,
                                    **breaker_result["transition"], snapshot=breaker_result)
                    retryable = isinstance(exc, tool.retryable_errors) and attempt <= tool.max_retries
                    publish("tool_execution_failed", task_id=task_id, tool_name=name,
                            attempt=attempt, error_type=type(exc).__name__, error_message=str(exc), retryable=retryable)
                    if not retryable:
                        raise
                    delay_ms = 250 * 2 ** (attempt - 1)
                    publish("tool_retry_scheduled", task_id=task_id, tool_name=name,
                            next_attempt=attempt + 1, delay_ms=delay_ms)
                    if self.sleep is time.sleep:
                        control.wait(delay_ms / 1000)
                    else:
                        self.sleep(delay_ms / 1000)
                        control.check()
                    continue
                if task_id == "D1" and breaker:
                    breaker_result = breaker.record_success()
                    publish("circuit_success_recorded", task_id="C1", tool_name=name,
                            snapshot=breaker_result)
                    if breaker_result.get("transition"):
                        publish("circuit_state_changed", task_id="C1", tool_name=name,
                                **breaker_result["transition"], snapshot=breaker_result)
                return output

        def run_batch(arguments_by_id, *, fan_in=False):
            """The owner stays responsive while Tools work; only it accepts results."""
            control.check()
            queue = Queue()
            finished, failures = set(), {}

            def worker(task_id, arguments):
                def publish(event, **payload):
                    queue.put(("event", event, deepcopy({"timestamp": datetime.now(timezone.utc).isoformat(), **payload})))
                try:
                    output = call(task_id, arguments, publish)
                    queue.put(("done", task_id, (output, None)))
                except BaseException as exc:
                    # Even a callable that exits abruptly must release the owner
                    # from its wait; never leave a missing "done" handshake.
                    queue.put(("done", task_id, (None, exc)))

            pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="rate-tool")
            inflight.update(arguments_by_id)
            try:
                for task_id, arguments in arguments_by_id.items():
                    pool.submit(worker, task_id, deepcopy(arguments))
                while len(finished) < len(arguments_by_id):
                    announce_stop()
                    try:
                        kind, key, payload = queue.get(timeout=0.025)
                    except Empty:
                        continue
                    if kind == "event":
                        emit(key, **payload)
                        continue
                    finished.add(key)
                    output, error = payload
                    # Linearization point: outputs not accepted before the stop
                    # boundary are audit-only, never downstream observations.
                    if control.snapshot()["stop_requested"] or isinstance(error, RunStopped):
                        announce_stop()
                        if error is None:
                            emit("tool_output_discarded", task_id=key, tool_name=by_id[key]["tool_name"],
                                 output=output, reason=control.snapshot()["reason"], accepted=False)
                        emit("task_cancelled", task_id=key, reason=control.snapshot()["reason"],
                             worker_stopped=True)
                    elif error:
                        failures[key] = str(error)
                        emit("task_failed", task_id=key, error_type=type(error).__name__, error_message=str(error))
                        if fan_in:
                            emit("join_blocked", task_id="J1", failed_dependencies=list(failures),
                                 reason="all_success requires both branches; no partial strategy run")
                            for downstream in ("S1", "E1"):
                                emit("task_blocked", task_id=downstream, reason="J1 cannot complete")
                    else:
                        observations[key] = output
                        completed.add(key)
                        if key == "D1":
                            for source in output.get("source_attempts", []):
                                emit("data_source_attempt", task_id="D1", **source)
                        emit("tool_observation", task_id=key, tool_name=by_id[key]["tool_name"],
                             artifact_type=output.get("artifact_type"), output=output, status="COMPLETED")
                        emit("task_completed", task_id=key, tool_name=by_id[key]["tool_name"], status="COMPLETED")
                        if fan_in and not failures:
                            emit("join_waiting", task_id="J1", required=2,
                                 completed_dependencies=[k for k in ("A2", "A10") if k in observations],
                                 waiting_for=[k for k in ("A2", "A10") if k not in observations])
                    inflight.discard(key)
            except BaseException:
                control.request_stop("disconnect")
                raise
            finally:
                # No "stopped" event until every submitted callable has exited.
                pool.shutdown(wait=True)
            control.check()
            if failures:
                raise ParallelRunError("Tool 失败；依赖它的下游未执行。", next(iter(failures)), trace, failures)

        def run_admission_demo(arguments_by_id):
            """Make overload handling visible without creating fake Tool results."""
            queue_capacity = 0 if demo_scenario == "overload_rejected" else 1
            admission = AdmissionController(max_in_flight=1, queue_capacity=queue_capacity,
                                            min_interval_ms=500)
            decisions = {}
            for task_id in ("A2", "A10"):
                emit("admission_requested", task_id="Q1", target_task=task_id,
                     scope="single_teaching_run", policy=admission.snapshot())
                decisions[task_id] = admission.request(task_id)
                decision = decisions[task_id]["decision"]
                if decision == "granted":
                    emit("rate_limit_granted", task_id="Q1", target_task=task_id,
                         snapshot=decisions[task_id])
                elif decision == "queued":
                    emit("backpressure_queued", task_id="Q1", target_task=task_id,
                         queue_depth=len(decisions[task_id]["queued"]), snapshot=decisions[task_id])
                else:
                    emit("admission_rejected", task_id="Q1", target_task=task_id,
                         reason="bounded queue is full", snapshot=decisions[task_id])

            run_batch({"A2": arguments_by_id["A2"]})
            admission.release("A2")
            emit("admission_capacity_released", task_id="Q1", target_task="A2",
                 snapshot=admission.snapshot())
            if decisions["A10"]["decision"] == "rejected":
                emit("task_failed", task_id="A10", error_type="AdmissionRejected",
                     error_message="Runtime rejected A10 before Tool execution; bounded queue was full")
                emit("join_blocked", task_id="J1", failed_dependencies=["A10"],
                     reason="all_success requires both branches; rejected work is not a result")
                for downstream in ("S1", "E1"):
                    emit("task_blocked", task_id=downstream, reason="J1 cannot complete")
                raise ParallelRunError("负载超过容量；A10 在 Tool 调用前被拒绝。", "A10", trace,
                                       {"A10": "admission rejected"})

            wait_ms = admission.next_wait_ms()
            if wait_ms and wait_ms > 0:
                emit("rate_limit_waiting", task_id="Q1", target_task="A10",
                     delay_ms=wait_ms, reason="respect minimum admission interval")
                control.wait(wait_ms / 1000)
            promoted = admission.promote()
            if not promoted:
                raise RuntimeError("queued task was not promotable")
            emit("backpressure_released", task_id="Q1", target_task="A10",
                 queue_depth=len(promoted["queued"]), snapshot=promoted)
            run_batch({"A10": arguments_by_id["A10"]})
            admission.release("A10")
            emit("admission_cycle_completed", task_id="Q1", snapshot=admission.snapshot())

        try:
            emit("goal_received", task_id="G1", goal="one auditable 2s10s paper simulation",
                 configuration={**configuration, "start_date": start_date}, demo_scenario=demo_scenario)
            emit("plan_created", task_id="P1", planner="bounded_fanout_all_success_join",
                 task_ids=list(by_id), tasks=plan, graph={"rows": GRAPH_ROWS, "edges": GRAPH_EDGES})
            emit("runtime_started", task_id="R1", model="none_deterministic_v1", max_workers=2,
                 registry_tools=list(dict.fromkeys(t["tool_name"] for t in plan)))
            emit("run_budget_started", task_id="R1", budget_ms=control.budget_ms,
                 scope="whole_run", policy="cooperative_stop_then_drain")
            if demo_scenario != "live":
                emit("demo_scenario_selected", task_id="R1", scenario=demo_scenario,
                     source_freshness="SNAPSHOT", teaching_delay=True,
                     message="明确的离线教学演示；Tool 真正执行，延时/故障由教学模式注入。")
            if not breaker:
                emit("circuit_bypassed", task_id="C1", reason="本场景不注入连续上游故障")
                completed.add("C1")
            current_task = "D1"
            run_batch({"D1": {"start_date": start_date}})
            if breaker:
                completed.add("C1")
            emit("parallel_group_started", task_id="R1", task_ids=["A2", "A10"], max_workers=2)
            emit("join_waiting", task_id="J1", completed_dependencies=[], waiting_for=["A2", "A10"], required=2)
            branch_arguments = {task_id: {"history": observations["D1"], "series_id": series_id, "batch_id": run_id}
                                for task_id, series_id in (("A2", "DGS2"), ("A10", "DGS10"))}
            if demo_scenario in ADMISSION_SCENARIOS:
                run_admission_demo(branch_arguments)
                completed.add("Q1")
            else:
                emit("admission_bypassed", task_id="Q1", reason="本场景允许两个独立分支并发")
                completed.add("Q1")
                run_batch(branch_arguments, fan_in=True)
            emit("join_released", task_id="J1", completed_dependencies=["A2", "A10"], required=2)
            current_task = "J1"
            run_batch({"J1": {"two_year": observations["A2"], "ten_year": observations["A10"]}})
            current_task = "S1"
            run_batch({"S1": {"history": observations["J1"], **configuration}})
            current_task = "E1"
            control.check()
            inflight.add("E1")
            emit("eval_started", task_id="E1", evaluator="evaluate_rate_simulation", arguments={"simulation": observations["S1"]})
            evaluation = evaluate_rate_simulation(observations["S1"])
            control.check()
            emit("eval_completed", task_id="E1", passed=evaluation["passed"], output=evaluation,
                 artifact_type=evaluation["artifact_type"])
            completed.add("E1")
            inflight.discard("E1")
            control.finish("completed")
            emit("run_completed", task_id="END", status="COMPLETED_ONE_PAPER_SIMULATION")
        except RunStopped as exc:
            announce_stop()
            if "E1" in inflight:
                emit("task_cancelled", task_id="E1", reason=exc.reason, worker_stopped=True)
                inflight.discard("E1")
            control.finish(exc.status)
            emit("run_stopped", task_id="R1", reason=exc.reason, status=exc.status,
                 workers_stopped=True, completed_tasks=sorted(completed))
            raise RateRunStopped(exc.reason, trace) from exc
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            control.request_stop("disconnect")
            control.finish("disconnected")
            raise
        except ParallelRunError:
            control.finish("failed")
            raise
        except Exception as exc:
            control.finish("failed")
            emit("task_failed", task_id=current_task, error_type=type(exc).__name__, error_message=str(exc))
            raise ParallelRunError(str(exc), current_task, trace) from exc
        return {
            "artifact_type": "rate_strategy_agent_run", "run_id": run_id,
            "status": "COMPLETED_ONE_PAPER_SIMULATION", "trace": trace,
            "plan": {"artifact_type": "rate_strategy_plan", "status": "completed",
                     "tasks": [{**task, "status": "completed"} for task in plan]},
            "data": observations["J1"], "simulation": observations["S1"], "eval": evaluation,
            "observations": observations,
            "state": {"phase": "completed", "completed_tasks": ["C1", "Q1", *by_id, "E1"]},
            "architecture": {"planner": "bounded_fanout_all_success_join", "model": "none_deterministic_v1",
                             "max_workers": 2, "join_policy": "all_success", "stream_writer": "owner_thread"},
            "lesson": {"topic": "resilience_guards", "demo_scenario": demo_scenario,
                       "teaching_delay": demo_scenario != "live", "graph": {"rows": GRAPH_ROWS, "edges": GRAPH_EDGES}},
            "guardrails": {"paper_only": True, "broker_connection": False, "automatic_execution": False,
                           "partial_join_allowed": False, "concurrent_external_writes": False},
            "run_control": control.snapshot(),
        }
