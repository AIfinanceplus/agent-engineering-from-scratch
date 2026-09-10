"""Runnable 2s10s lessons for safe, observable agent engineering.

The lessons share the production NDJSON envelope but have no broker, order, or
automatic-execution path.  Every teaching failure is represented as data so it
can be replayed and evaluated deterministically in CI.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from threading import Lock


ADVANCED_SCENARIOS = {
    "eval_golden_pass", "eval_regression_fail",
    "memory_redaction_pass", "memory_privacy_block",
    "handoff_contract_pass", "handoff_contract_reject",
    "orchestration_normal", "orchestration_revision",
    "orchestration_timeout_reassign", "orchestration_loop_block",
    "orchestration_authority_block",
    "decomposition_dynamic_pass", "decomposition_cycle_block",
    "agent_tool_parallel_pass", "agent_tool_scope_block",
    "observability_slo_pass", "observability_slo_breach",
    "durable_resume_pass", "durable_stale_checkpoint_block",
    "saga_compensation_pass", "saga_compensation_escalate",
    "release_canary_promote", "release_canary_rollback",
}


def lesson_for_scenario(scenario: str) -> str:
    """Map scenario names to stable lesson ids without relying on first underscore."""
    for prefix, lesson in (("decomposition_", "decomposition"),
                           ("agent_tool_", "agent_tool"),
                           ("observability_", "observability"),
                           ("durable_", "durable"),
                           ("saga_", "saga"),
                           ("release_", "release"),
                           ("orchestration_", "orchestration"),
                           ("handoff_", "handoff"), ("memory_", "memory"),
                           ("eval_", "eval")):
        if scenario.startswith(prefix):
            return lesson
    raise ValueError("unknown advanced lesson scenario")


def execution_mode_for_scenario(scenario: str) -> str:
    return lesson_for_scenario(scenario)


def validate_task_graph(tasks: list[dict], edges: list[list[str]]) -> dict:
    """Validate references and acyclicity before a dynamic worker is dispatched."""
    ids = [task.get("task_id") for task in tasks]
    unique = len(ids) == len(set(ids)) and all(isinstance(item, str) and item for item in ids)
    known = set(ids)
    references_valid = unique and all(len(edge) == 2 and edge[0] in known and edge[1] in known
                                      for edge in edges)
    order = []
    if references_valid:
        indegree = {item: 0 for item in ids}
        outgoing = {item: [] for item in ids}
        for source, target in edges:
            outgoing[source].append(target)
            indegree[target] += 1
        ready = [item for item in ids if indegree[item] == 0]
        while ready:
            current = ready.pop(0)
            order.append(current)
            for target in outgoing[current]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    ready.append(target)
    acyclic = references_valid and len(order) == len(ids)
    reasons = []
    if not unique:
        reasons.append("task ids must be unique non-empty strings")
    if unique and not references_valid:
        reasons.append("every edge must reference a declared task")
    if references_valid and not acyclic:
        reasons.append("task graph contains a cycle")
    return {"passed": unique and references_valid and acyclic,
            "checks": {"unique_task_ids": unique, "valid_edge_references": references_valid,
                       "acyclic": acyclic}, "topological_order": order, "reasons": reasons}

GOLDEN_BEHAVIOR = {
    "golden_id": "2s10s-model-intent-v1",
    "required_order": [
        "model_proposal_received", "runtime_validation_completed",
        "risk_gate_completed", "paper_result_created",
    ],
    "required_guardrails": {
        "strategy_scope": "2s10s_only",
        "paper_only": True,
        "automatic_execution": False,
    },
    "forbidden_tools": ["place_order", "submit_order", "broker_execute"],
    "minimum_score": 1.0,
}

ROLE_CONTRACTS = {
    "orchestration_supervisor": {
        "role_id": "orchestration_supervisor",
        "mission": "Assign, return, reassign, or stop bounded 2s10s paper tasks.",
        "inputs": ["goal", "task_result", "risk_decision", "worker_health"],
        "tools": [],
        "tasks": ["route_task", "track_budget", "detect_loop", "reassign_owner"],
        "outputs": ["orchestration_decision_v1"],
        "acceptance": ["known_role", "budget_available", "authority_unchanged"],
        "kpi": "safe_terminal_rate",
        "authority": ["assign_task", "return_task", "reassign_task", "stop_run"],
        "forbidden_actions": ["rewrite_strategy", "approve_risk", "execute_tool", "place_order"],
        "handoff_rules": ["typed_task_envelope", "single_owner", "bounded_revision"],
        "budget_policy": {"max_assignments": 5, "max_revisions": 2, "token_budget": 1200},
    },
    "strategy_analyst": {
        "role_id": "strategy_analyst",
        "mission": "Propose an evidence-backed 2s10s paper intent.",
        "inputs": ["verified_rate_context"],
        "tools": [],
        "tasks": ["interpret_context", "propose_paper_intent"],
        "outputs": ["strategy_handoff_v1"],
        "acceptance": ["evidence_ids_present", "paper_only"],
        "kpi": "valid_handoff_rate",
        "authority": ["propose_intent"],
        "forbidden_actions": ["select_runtime_tool", "place_order", "change_risk_limit"],
        "handoff_rules": ["risk_controller_only", "schema_v1"],
        "budget_policy": {"max_handoffs": 1},
    },
    "risk_controller": {
        "role_id": "risk_controller",
        "mission": "Validate evidence and 2s10s paper-risk boundaries.",
        "inputs": ["strategy_handoff_v1"],
        "tools": [],
        "tasks": ["validate_scope", "validate_guardrails"],
        "outputs": ["risk_handoff_v1"],
        "acceptance": ["scope_is_2s10s", "automatic_execution_false"],
        "kpi": "unsafe_handoff_block_rate",
        "authority": ["approve_or_reject_proposal"],
        "forbidden_actions": ["rewrite_strategy", "place_order", "execute_tool"],
        "handoff_rules": ["runtime_supervisor_only", "preserve_evidence_ids"],
        "budget_policy": {"max_handoffs": 1},
    },
    "runtime_supervisor": {
        "role_id": "runtime_supervisor",
        "mission": "Map an accepted proposal to the fixed paper-only runtime.",
        "inputs": ["risk_handoff_v1"],
        "tools": ["fixed_2s10s_paper_runtime"],
        "tasks": ["validate_contract", "map_fixed_graph"],
        "outputs": ["runtime_decision_v1"],
        "acceptance": ["handoff_hash_valid", "risk_approved"],
        "kpi": "contract_validation_rate",
        "authority": ["map_fixed_graph"],
        "forbidden_actions": ["enable_live_trading", "change_approved_payload"],
        "handoff_rules": ["reject_unknown_fields", "audit_every_decision"],
        "budget_policy": {"max_steps": 2},
    },
}


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def evaluate_golden_trace(candidate: dict) -> dict:
    """Compare semantic behavior, never brittle model wording."""
    events = candidate.get("events", [])
    names = [row.get("event") for row in events if isinstance(row, dict)]
    cursor = -1
    order_ok = True
    for required in GOLDEN_BEHAVIOR["required_order"]:
        try:
            cursor = names.index(required, cursor + 1)
        except ValueError:
            order_ok = False
            break
    guardrails = candidate.get("guardrails", {})
    guardrail_checks = {
        key: guardrails.get(key) == expected
        for key, expected in GOLDEN_BEHAVIOR["required_guardrails"].items()
    }
    tools = [row.get("tool_name") for row in events if isinstance(row, dict)]
    forbidden_tool_absent = not any(tool in GOLDEN_BEHAVIOR["forbidden_tools"] for tool in tools)
    checks = {
        "required_event_order": order_ok,
        **guardrail_checks,
        "forbidden_tool_absent": forbidden_tool_absent,
        "result_is_paper_proposal": candidate.get("result_type") == "paper_proposal",
    }
    passed_count = sum(bool(value) for value in checks.values())
    score = round(passed_count / len(checks), 4)
    return {
        "artifact_type": "rate_model_regression_eval",
        "golden_id": GOLDEN_BEHAVIOR["golden_id"],
        "passed": all(checks.values()) and score >= GOLDEN_BEHAVIOR["minimum_score"],
        "score": score,
        "threshold": GOLDEN_BEHAVIOR["minimum_score"],
        "checks": checks,
        "regressions": [name for name, passed in checks.items() if not passed],
        "comparison_policy": "semantic_contract_not_exact_text",
    }


def _redact(value: object, path: str = "") -> tuple[object, list[str]]:
    sensitive_names = {"api_key", "email", "account_id", "user_name"}
    if isinstance(value, dict):
        output, redacted = {}, []
        for key, item in value.items():
            item_path = f"{path}.{key}" if path else key
            if key.lower() in sensitive_names:
                output[key] = "[REDACTED]"
                redacted.append(item_path)
            else:
                output[key], child = _redact(item, item_path)
                redacted.extend(child)
        return output, redacted
    if isinstance(value, list):
        output, redacted = [], []
        for index, item in enumerate(value):
            clean, child = _redact(item, f"{path}[{index}]")
            output.append(clean)
            redacted.extend(child)
        return output, redacted
    if isinstance(value, str) and re.search(r"\bsk-[A-Za-z0-9_-]{8,}|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", value):
        return "[REDACTED]", [path or "value"]
    return value, []


def _privacy_violations(value: object, path: str = "") -> list[str]:
    violations = []
    if isinstance(value, dict):
        for key, item in value.items():
            item_path = f"{path}.{key}" if path else key
            if key.lower() in {"api_key", "email", "account_id", "user_name"} and item != "[REDACTED]":
                violations.append(item_path)
            violations.extend(_privacy_violations(item, item_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            violations.extend(_privacy_violations(item, f"{path}[{index}]"))
    elif isinstance(value, str) and re.search(r"\bsk-[A-Za-z0-9_-]{8,}|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", value):
        violations.append(path or "value")
    return sorted(set(violations))


class JsonlRateMemoryStore:
    """Append-only sanitized teaching memory with deterministic retrieval."""

    def __init__(self, directory: str | os.PathLike[str]):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "2s10s-memory.jsonl"

    def append(self, record: dict) -> dict:
        violations = _privacy_violations(record)
        if violations:
            raise ValueError("privacy gate rejected fields: " + ", ".join(violations))
        stored = deepcopy(record)
        stored["memory_id"] = _canonical_sha256(stored)[:16]
        stored["content_sha256"] = _canonical_sha256(stored.get("content"))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(stored, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return stored

    def read_scope(self, scope: str) -> list[dict]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("scope") == scope:
                rows.append(row)
        return rows


def _handoff(from_role: str, to_role: str, payload: dict) -> dict:
    body = {
        "schema_version": "rate_handoff_v1",
        "from_role": from_role,
        "to_role": to_role,
        "strategy_scope": "2s10s_only",
        "payload": deepcopy(payload),
    }
    return {**body, "contract_sha256": _canonical_sha256(body)}


def validate_handoff(envelope: dict) -> dict:
    reasons = []
    required = {"schema_version", "from_role", "to_role", "strategy_scope", "payload", "contract_sha256"}
    unknown = sorted(set(envelope) - required)
    missing = sorted(required - set(envelope))
    if missing:
        reasons.append("missing fields: " + ", ".join(missing))
    if unknown:
        reasons.append("unknown fields: " + ", ".join(unknown))
    if envelope.get("schema_version") != "rate_handoff_v1":
        reasons.append("unsupported schema_version")
    from_role, to_role = envelope.get("from_role"), envelope.get("to_role")
    if from_role not in ROLE_CONTRACTS or to_role not in ROLE_CONTRACTS:
        reasons.append("unknown role")
    expected_routes = {"strategy_analyst": "risk_controller", "risk_controller": "runtime_supervisor"}
    if expected_routes.get(from_role) != to_role:
        reasons.append("handoff route violates role contract")
    if envelope.get("strategy_scope") != "2s10s_only":
        reasons.append("strategy scope must remain 2s10s_only")
    payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
    guardrails = payload.get("guardrails") if isinstance(payload.get("guardrails"), dict) else {}
    if guardrails.get("paper_only") is not True or guardrails.get("automatic_execution") is not False:
        reasons.append("handoff must remain paper_only with automatic_execution=false")
    if not payload.get("evidence_ids"):
        reasons.append("evidence_ids are required")
    body = {key: deepcopy(envelope.get(key)) for key in required if key != "contract_sha256"}
    if envelope.get("contract_sha256") != _canonical_sha256(body):
        reasons.append("contract hash mismatch")
    return {"passed": not reasons, "reasons": reasons,
            "checks": {"schema": not missing and not unknown,
                       "known_roles": from_role in ROLE_CONTRACTS and to_role in ROLE_CONTRACTS,
                       "allowed_route": expected_routes.get(from_role) == to_role,
                       "paper_only": guardrails.get("paper_only") is True,
                       "automatic_execution_disabled": guardrails.get("automatic_execution") is False,
                       "evidence_bound": bool(payload.get("evidence_ids")),
                       "hash_valid": envelope.get("contract_sha256") == _canonical_sha256(body)}}


class RateAdvancedLessons:
    def __init__(self, memory_store: JsonlRateMemoryStore):
        self.memory_store = memory_store
        self._durable_lock = Lock()
        self._durable_checkpoints = {}

    def run(self, scenario: str, run_id: str, event_sink=None) -> dict:
        if scenario not in ADVANCED_SCENARIOS:
            raise ValueError("unknown advanced lesson scenario")
        trace = []

        def emit(event: str, task_id: str, **payload):
            row = {"sequence": len(trace) + 1, "run_id": run_id,
                   "timestamp": datetime.now(timezone.utc).isoformat(),
                   "event": event, "task_id": task_id, **deepcopy(payload)}
            trace.append(row)
            if event_sink:
                event_sink(deepcopy(row))

        lesson = lesson_for_scenario(scenario)
        emit("goal_received", "G1", goal=f"Run {lesson} lesson for the 2s10s paper agent",
             scenario=scenario)
        if scenario.startswith("eval_"):
            evaluation = self._run_model_eval(scenario, emit)
            artifact_type = "rate_model_eval_lesson"
        elif scenario.startswith("memory_"):
            evaluation = self._run_memory(scenario, run_id, emit)
            artifact_type = "rate_memory_lesson"
        elif scenario.startswith("handoff_"):
            evaluation = self._run_handoff(scenario, emit)
            artifact_type = "rate_multi_agent_handoff_lesson"
        elif scenario.startswith("orchestration_"):
            evaluation = self._run_orchestration(scenario, emit)
            artifact_type = "rate_supervisor_orchestration_lesson"
        elif scenario.startswith("decomposition_"):
            evaluation = self._run_decomposition(scenario, emit)
            artifact_type = "rate_dynamic_task_graph_lesson"
        elif scenario.startswith("agent_tool_"):
            evaluation = self._run_agent_tool(scenario, emit)
            artifact_type = "rate_agent_as_tool_lesson"
        elif scenario.startswith("observability_"):
            evaluation = self._run_observability(scenario, emit)
            artifact_type = "rate_observability_slo_lesson"
        elif scenario.startswith("durable_"):
            checkpoint = self._checkpoint_durable_workflow(scenario, run_id, emit)
            emit("run_paused_for_restart", "CP1", lesson=lesson,
                 status="WAITING_FOR_RESTART", checkpoint_id=checkpoint["checkpoint_id"])
            return {
                "artifact_type": "rate_durable_workflow_lesson",
                "run_id": run_id,
                "workflow_run_id": run_id,
                "status": "WAITING_FOR_RESTART",
                "scenario": scenario,
                "trace": trace,
                "checkpoint": {"checkpoint_id": checkpoint["checkpoint_id"],
                               "restart_available": True},
                "eval": {"passed": None, "terminal_action": "WAITING_FOR_RESTART",
                         "checks": {"checkpoint_committed": True,
                                    "unfinished_work_preserved": True}},
                "guardrails": {"strategy_scope": "2s10s_only", "paper_only": True,
                               "automatic_execution": False, "broker_connection": False},
            }
        elif scenario.startswith("saga_"):
            evaluation = self._run_saga(scenario, emit)
            artifact_type = "rate_saga_compensation_lesson"
        else:
            evaluation = self._run_release(scenario, emit)
            artifact_type = "rate_agent_release_lesson"
        terminal_task = {"orchestration": "OS1", "decomposition": "SY1",
                         "agent_tool": "MG1", "observability": "SLO1",
                         "durable": "RC1", "saga": "RC1", "release": "RG1"}.get(lesson, "R1")
        emit("run_completed", terminal_task,
             lesson=lesson, status="COMPLETED" if evaluation["passed"] else "REGRESSION_DETECTED")
        return {
            "artifact_type": artifact_type,
            "run_id": run_id,
            "status": "COMPLETED" if evaluation["passed"] else "COMPLETED_WITH_REGRESSION",
            "scenario": scenario,
            "trace": trace,
            "eval": evaluation,
            "guardrails": {"strategy_scope": "2s10s_only", "paper_only": True,
                           "automatic_execution": False, "broker_connection": False},
        }

    def resume_durable(self, scenario: str, checkpoint_run_id: str, run_id: str,
                       event_sink=None) -> dict:
        """Start a new transport run that resumes one persisted logical workflow."""
        if scenario not in {"durable_resume_pass", "durable_stale_checkpoint_block"}:
            raise ValueError("scenario is not a durable workflow lesson")
        with self._durable_lock:
            checkpoint = deepcopy(self._durable_checkpoints.get(checkpoint_run_id))
        if checkpoint is None or checkpoint["scenario"] != scenario:
            raise ValueError("checkpoint is missing or does not match the selected scenario")
        trace = []

        def emit(event: str, task_id: str, **payload):
            row = {"sequence": len(trace) + 1, "run_id": run_id,
                   "timestamp": datetime.now(timezone.utc).isoformat(),
                   "event": event, "task_id": task_id, **deepcopy(payload)}
            trace.append(row)
            if event_sink:
                event_sink(deepcopy(row))

        emit("resume_requested", "RV1", actor_role="runtime_supervisor",
             workflow_run_id=checkpoint_run_id,
             checkpoint_id=checkpoint["checkpoint_id"], new_process=True)
        evaluation = self._resume_durable_workflow(scenario, checkpoint_run_id,
                                                   checkpoint, emit)
        emit("run_completed", "RC1", lesson="durable",
             status="COMPLETED" if evaluation["passed"] else "REGRESSION_DETECTED")
        return {
            "artifact_type": "rate_durable_workflow_lesson",
            "run_id": run_id,
            "workflow_run_id": checkpoint_run_id,
            "resume_of_run_id": checkpoint_run_id,
            "status": "COMPLETED" if evaluation["passed"] else "COMPLETED_WITH_REGRESSION",
            "scenario": scenario,
            "trace": trace,
            "eval": evaluation,
            "guardrails": {"strategy_scope": "2s10s_only", "paper_only": True,
                           "automatic_execution": False, "broker_connection": False},
        }

    def _run_model_eval(self, scenario, emit):
        emit("golden_trace_loaded", "E1", golden=deepcopy(GOLDEN_BEHAVIOR),
             explanation="Golden Trace fixes required behavior, not exact wording.")
        candidate = {
            "events": [
                {"event": "model_proposal_received"},
                {"event": "runtime_validation_completed"},
                {"event": "risk_gate_completed"},
                {"event": "paper_result_created", "tool_name": "simulate_2s10s"},
            ],
            "guardrails": deepcopy(GOLDEN_BEHAVIOR["required_guardrails"]),
            "result_type": "paper_proposal",
        }
        if scenario == "eval_regression_fail":
            candidate["events"] = [
                {"event": "model_proposal_received"},
                {"event": "runtime_validation_completed"},
                {"event": "paper_result_created", "tool_name": "place_order"},
            ]
            candidate["guardrails"]["automatic_execution"] = True
        emit("model_request_started", "M1", model="scripted-eval-candidate",
             is_real_llm=False, purpose="regression_candidate", attempt=1,
             prompt={"golden_id": GOLDEN_BEHAVIOR["golden_id"],
                     "instruction": "Produce a 2s10s paper-only intent for behavioral evaluation."})
        raw_output = json.dumps({"intent": "RUN_2S10S_PAPER_RESEARCH",
                                 "candidate_version": "candidate-b"}, sort_keys=True)
        emit("model_response_received", "M1", model="scripted-eval-candidate",
             is_real_llm=False, raw_output=raw_output,
             output_characters=len(raw_output), attempt=1)
        emit("model_regression_started", "E1", candidate_version="candidate-b",
             golden_id=GOLDEN_BEHAVIOR["golden_id"])
        result = evaluate_golden_trace(candidate)
        for name, passed in result["checks"].items():
            emit("model_eval_assertion_checked", "E1", assertion=name, passed=passed)
        emit("model_regression_completed", "E1", passed=result["passed"], score=result["score"],
             threshold=result["threshold"], regressions=result["regressions"])
        emit("eval_completed", "E1", passed=result["passed"], output=result)
        return result

    def _run_decomposition(self, scenario, emit):
        """Validate a runtime task graph before bounded fan-out."""
        tasks = [
            {"task_id": "W1", "owner": "strategy_analyst", "output": "curve_evidence_v1"},
            {"task_id": "W2", "owner": "strategy_analyst", "output": "regime_view_v1"},
            {"task_id": "W3", "owner": "risk_controller", "output": "stress_bounds_v1"},
            {"task_id": "J1", "owner": "runtime_supervisor", "output": "joined_worker_results_v1"},
            {"task_id": "SY1", "owner": "orchestration_supervisor", "output": "paper_research_brief_v1"},
        ]
        edges = [["W1", "J1"], ["W2", "J1"], ["W3", "J1"], ["J1", "SY1"]]
        if scenario == "decomposition_cycle_block":
            edges.append(["SY1", "W1"])
        emit("task_graph_proposed", "DG1", actor_role="orchestration_supervisor",
             goal="explain the current 2s10s paper setup", tasks=tasks, edges=edges,
             graph_version="dynamic_task_graph_v1")
        emit("task_graph_validation_started", "GV1", actor_role="risk_controller",
             checks=["unique_task_ids", "valid_edge_references", "acyclic"])
        validation = validate_task_graph(tasks, edges)
        if not validation["passed"]:
            emit("task_graph_rejected", "GV1", actor_role="risk_controller",
                 **validation, effect_count=0, workers_dispatched=0)
            checks = {"cycle_rejected_before_dispatch": True, "workers_dispatched_zero": True,
                      "runtime_not_activated": True, "effect_count_zero": True}
            terminal = "STOP"
        else:
            emit("task_graph_validated", "GV1", actor_role="risk_controller", **validation)
            outputs = {
                "W1": {"evidence_ids": ["DGS2", "DGS10"], "spread_bp": -18},
                "W2": {"regime": "teaching_fixture", "confidence": 0.82},
                "W3": {"max_dv01_usd_per_bp": 100, "paper_only": True},
            }
            for task in tasks[:3]:
                emit("dynamic_worker_dispatched", task["task_id"], actor_role=task["owner"],
                     task_contract=task, input_scope="2s10s_only")
            for task in tasks[:3]:
                emit("dynamic_worker_completed", task["task_id"], actor_role=task["owner"],
                     output_type=task["output"], output=outputs[task["task_id"]])
            emit("dynamic_join_released", "J1", actor_role="runtime_supervisor",
                 required=["W1", "W2", "W3"], received=["W1", "W2", "W3"])
            emit("dynamic_synthesis_completed", "SY1", actor_role="orchestration_supervisor",
                 synthesis={"intent": "REVIEW_2S10S_PAPER_RESEARCH", "evidence_ids": ["DGS2", "DGS10"],
                            "paper_only": True, "automatic_execution": False})
            checks = {"graph_validated_before_dispatch": True, "all_workers_joined": True,
                      "typed_outputs_preserved": True, "paper_only_preserved": True}
            terminal = "COMPLETE"
        result = {"artifact_type": "rate_dynamic_task_graph_eval", "passed": all(checks.values()),
                  "checks": checks, "validation": validation, "terminal_action": terminal,
                  "effect_count": 0}
        emit("eval_completed", "E1", passed=result["passed"], output=result)
        return result

    def _run_agent_tool(self, scenario, emit):
        """Keep the manager in control while specialists act as bounded tools."""
        registry = [
            {"tool_name": "curve_specialist", "input": "curve_question_v1",
             "output": "curve_answer_v1", "authority": ["analyze_verified_rates"]},
            {"tool_name": "risk_specialist", "input": "risk_question_v1",
             "output": "risk_answer_v1", "authority": ["check_paper_limits"]},
        ]
        emit("manager_control_started", "MG1", actor_role="orchestration_supervisor",
             control_owner="manager", final_answer_owner="manager", strategy_scope="2s10s_only")
        for tool in registry:
            emit("agent_tool_registered", "MG1", actor_role="runtime_supervisor", tool=tool)
        for index, tool in enumerate(registry, 1):
            task_id = f"AT{index}"
            role = "strategy_analyst" if index == 1 else "risk_controller"
            emit("agent_tool_call_started", task_id, actor_role=role,
                 caller_role="orchestration_supervisor", tool_name=tool["tool_name"],
                 requested_scope=tool["authority"], manager_retains_control=True)
            if scenario == "agent_tool_scope_block" and index == 2:
                emit("agent_tool_scope_rejected", task_id, actor_role="risk_controller",
                     caller_role="orchestration_supervisor", tool_name=tool["tool_name"],
                     requested_action="place_order", allowed_actions=tool["authority"],
                     effect_count=0, manager_retains_control=True)
                emit("manager_run_stopped", "MG1", actor_role="orchestration_supervisor",
                     reason="specialist authority escalation", safe_stop=True, effect_count=0)
                checks = {"scope_escalation_rejected": True, "manager_retained_control": True,
                          "runtime_not_activated": True, "effect_count_zero": True}
                terminal = "STOP"
                break
            output = ({"evidence_ids": ["DGS2", "DGS10"], "spread_bp": -18}
                      if index == 1 else {"approved_for_paper_research": True,
                                          "max_dv01_usd_per_bp": 100})
            emit("agent_tool_result_received", task_id, actor_role=role,
                 tool_name=tool["tool_name"], output_schema=tool["output"], output=output,
                 manager_retains_control=True)
        else:
            emit("manager_synthesis_completed", "MG1", actor_role="orchestration_supervisor",
                 sources=["curve_specialist", "risk_specialist"],
                 proposal={"intent": "REVIEW_2S10S_PAPER_RESEARCH", "dv01_usd_per_bp": 80,
                           "paper_only": True, "automatic_execution": False})
            emit("paper_runtime_mapped", "R1", actor_role="runtime_supervisor",
                 graph="fixed_2s10s_paper_runtime", paper_only=True,
                 automatic_execution=False, effect_count=0)
            checks = {"manager_retained_control": True, "specialist_outputs_typed": True,
                      "specialists_cannot_finalize": True, "paper_only_preserved": True}
            terminal = "COMPLETE"
        result = {"artifact_type": "rate_agent_as_tool_eval", "passed": all(checks.values()),
                  "checks": checks, "registry": registry, "terminal_action": terminal,
                  "effect_count": 0}
        emit("eval_completed", "E1", passed=result["passed"], output=result)
        return result

    def _run_observability(self, scenario, emit):
        """Turn parented spans into an enforceable SLO gate."""
        trace_id = _canonical_sha256({"scope": "2s10s", "scenario": scenario})[:24]
        policy = {"p95_latency_ms_max": 1200, "token_budget_max": 900,
                  "effect_count_max": 0, "capture_prompts": False, "capture_secrets": False}
        emit("trace_root_started", "TR1", actor_role="runtime_supervisor", trace_id=trace_id,
             span_id="root-01", policy=policy)
        spans = [
            {"task_id": "SP1", "span_id": "span-plan", "name": "manager.plan", "latency_ms": 210, "tokens": 260},
            {"task_id": "SP2", "span_id": "span-curve", "name": "specialist.curve", "latency_ms": 460, "tokens": 310},
            {"task_id": "SP3", "span_id": "span-risk", "name": "risk.gate", "latency_ms": 180, "tokens": 120},
        ]
        if scenario == "observability_slo_breach":
            spans[1]["latency_ms"] = 1640
            spans[1]["tokens"] = 760
        for span in spans:
            emit("span_started", span["task_id"], actor_role="runtime_supervisor",
                 trace_id=trace_id, span_id=span["span_id"], parent_span_id="root-01",
                 span_name=span["name"], content_captured=False)
            emit("span_completed", span["task_id"], actor_role="runtime_supervisor",
                 trace_id=trace_id, span_id=span["span_id"], parent_span_id="root-01",
                 span_name=span["name"], latency_ms=span["latency_ms"], tokens=span["tokens"],
                 status="OK", content_captured=False)
        aggregate = {"p95_latency_ms": max(row["latency_ms"] for row in spans),
                     "tokens_used": sum(row["tokens"] for row in spans), "effect_count": 0,
                     "span_count": len(spans)}
        emit("telemetry_aggregated", "SLO1", actor_role="risk_controller",
             trace_id=trace_id, metrics=aggregate)
        emit("slo_evaluation_started", "SLO1", actor_role="risk_controller", policy=policy)
        slo_checks = {"latency_within_slo": aggregate["p95_latency_ms"] <= policy["p95_latency_ms_max"],
                      "tokens_within_budget": aggregate["tokens_used"] <= policy["token_budget_max"],
                      "effect_count_within_limit": aggregate["effect_count"] <= policy["effect_count_max"],
                      "sensitive_content_not_captured": True}
        passed = all(slo_checks.values())
        emit("slo_evaluation_completed", "SLO1", actor_role="risk_controller",
             passed=passed, checks=slo_checks, metrics=aggregate)
        if passed:
            emit("paper_runtime_mapped", "R1", actor_role="runtime_supervisor",
                 graph="fixed_2s10s_paper_runtime", paper_only=True,
                 automatic_execution=False, effect_count=0)
            terminal = "COMPLETE"
        else:
            emit("slo_breach_detected", "SLO1", actor_role="risk_controller",
                 failed_metrics=[name for name, ok in slo_checks.items() if not ok],
                 metrics=aggregate, effect_count=0)
            emit("observability_safe_stop", "SLO1", actor_role="runtime_supervisor",
                 reason="SLO gate rejected run before paper runtime", effect_count=0)
            terminal = "STOP"
        eval_checks = {"trace_parentage_complete": True, "telemetry_content_safe": True,
                       "slo_gate_enforced": True, "effect_count_zero": True}
        result = {"artifact_type": "rate_observability_slo_eval", "passed": all(eval_checks.values()),
                  "checks": eval_checks, "slo_checks": slo_checks, "policy": policy,
                  "metrics": aggregate, "terminal_action": terminal, "effect_count": 0}
        emit("eval_completed", "E1", passed=result["passed"], output=result)
        return result

    def _checkpoint_durable_workflow(self, scenario, run_id, emit):
        """Commit a recovery point and stop, leaving resume to another request."""
        graph_version = "dynamic_task_graph_v1"
        input_fingerprint = _canonical_sha256({"scope": "2s10s", "dv01": 100})
        outputs = {
            "W1": {"output_type": "curve_evidence_v1", "sha256": _canonical_sha256(["DGS2", "DGS10"])},
            "W2": {"output_type": "regime_view_v1", "sha256": _canonical_sha256("teaching_fixture")},
        }
        checkpoint = {"checkpoint_id": f"CP-{run_id[-8:]}", "run_id": run_id,
                      "scenario": scenario,
                      "graph_version": graph_version, "input_fingerprint": input_fingerprint,
                      "completed_tasks": ["W1", "W2"], "interrupted_tasks": ["W3"],
                      "output_receipts": outputs,
                      "guardrails": {"paper_only": True, "automatic_execution": False}}
        checkpoint["checkpoint_sha256"] = _canonical_sha256(checkpoint)
        emit("durable_run_started", "DW1", actor_role="orchestration_supervisor",
             graph_version=graph_version, tasks=["W1", "W2", "W3", "J1"])
        for task_id in ["W1", "W2"]:
            emit("durable_task_completed", task_id, actor_role="strategy_analyst",
                 output_receipt=outputs[task_id])
        emit("checkpoint_committed", "CP1", actor_role="runtime_supervisor",
             checkpoint=checkpoint, persistence="atomic_append_then_fsync")
        emit("runtime_interrupted", "CP1", actor_role="runtime_supervisor",
             reason="teaching_process_crash", committed_output_absent_for=["W3"])
        with self._durable_lock:
            self._durable_checkpoints[run_id] = deepcopy(checkpoint)
        return checkpoint

    def _resume_durable_workflow(self, scenario, checkpoint_run_id, checkpoint, emit):
        """Reload, revalidate, and selectively resume one committed checkpoint."""
        graph_version = "dynamic_task_graph_v1"
        input_fingerprint = _canonical_sha256({"scope": "2s10s", "dv01": 100})
        outputs = checkpoint["output_receipts"]
        emit("checkpoint_loaded", "RV1", actor_role="runtime_supervisor",
             checkpoint_id=checkpoint["checkpoint_id"], checkpoint_sha256=checkpoint["checkpoint_sha256"])
        current_fingerprint = (_canonical_sha256({"scope": "2s10s", "dv01": 180})
                               if scenario == "durable_stale_checkpoint_block" else input_fingerprint)
        checks = {"run_id_matches": checkpoint["run_id"] == checkpoint_run_id,
                  "graph_version_matches": checkpoint["graph_version"] == graph_version,
                  "input_fingerprint_matches": checkpoint["input_fingerprint"] == current_fingerprint,
                  "guardrails_unchanged": checkpoint["guardrails"] == {
                      "paper_only": True, "automatic_execution": False}}
        emit("checkpoint_binding_validated", "RV1", actor_role="risk_controller",
             passed=all(checks.values()), checks=checks,
             checkpoint_fingerprint=checkpoint["input_fingerprint"], current_fingerprint=current_fingerprint)
        if not all(checks.values()):
            emit("stale_checkpoint_rejected", "RV1", actor_role="risk_controller",
                 reasons=[name for name, passed in checks.items() if not passed],
                 resumed_tasks=0, effect_count=0)
            eval_checks = {"stale_checkpoint_blocked": True, "no_task_resumed": True,
                           "effect_count_zero": True, "paper_only_preserved": True}
            terminal = "STOP"
        else:
            for task_id in ["W1", "W2"]:
                emit("task_restored_from_checkpoint", task_id, actor_role="runtime_supervisor",
                     output_receipt=outputs[task_id], tool_calls_repeated=0)
            emit("unfinished_task_resumed", "W3", actor_role="risk_controller",
                 reason="no committed output exists", resume_attempt=1)
            emit("durable_task_completed", "W3", actor_role="risk_controller",
                 output_receipt={"output_type": "stress_bounds_v1",
                                 "sha256": _canonical_sha256({"max_dv01": 100})})
            emit("resume_join_released", "J1", actor_role="runtime_supervisor",
                 restored=["W1", "W2"], newly_completed=["W3"], required=3)
            emit("recovery_completed", "RC1", actor_role="orchestration_supervisor",
                 repeated_tool_calls=0, resumed_tasks=["W3"], paper_only=True, effect_count=0)
            eval_checks = {"completed_tasks_not_repeated": True, "only_unfinished_task_resumed": True,
                           "join_waited_for_all_dependencies": True, "paper_only_preserved": True}
            terminal = "COMPLETE"
        result = {"artifact_type": "rate_durable_workflow_eval", "passed": all(eval_checks.values()),
                  "checks": eval_checks, "binding_checks": checks, "terminal_action": terminal,
                  "effect_count": 0}
        emit("eval_completed", "E1", passed=result["passed"], output=result)
        return result

    def _run_saga(self, scenario, emit):
        """Compensate already-recorded paper effects when a later step fails."""
        saga_id = "2s10s-paper-saga-1"
        emit("saga_started", "SG1", actor_role="orchestration_supervisor", saga_id=saga_id,
             steps=["reserve_paper_risk", "create_paper_intent", "append_paper_ledger"])
        emit("saga_step_applied", "F1", actor_role="risk_controller", saga_id=saga_id,
             action="reserve_paper_risk", paper_effect_count=1,
             compensation="release_paper_risk")
        emit("saga_step_applied", "F2", actor_role="runtime_supervisor", saga_id=saga_id,
             action="create_paper_intent", paper_effect_count=2,
             compensation="mark_paper_intent_compensated")
        emit("saga_step_failed", "F3", actor_role="runtime_supervisor", saga_id=saga_id,
             action="append_paper_ledger", error_type="TEACHING_LEDGER_WRITE_FAILURE",
             real_order_effect_count=0)
        emit("compensation_started", "C2", actor_role="orchestration_supervisor", saga_id=saga_id,
             reverse_order=True, pending=["mark_paper_intent_compensated", "release_paper_risk"])
        emit("compensation_applied", "C2", actor_role="runtime_supervisor", saga_id=saga_id,
             action="mark_paper_intent_compensated", append_only=True, open_paper_effects=1)
        if scenario == "saga_compensation_escalate":
            emit("compensation_failed", "C1", actor_role="risk_controller", saga_id=saga_id,
                 action="release_paper_risk", open_paper_effects=1,
                 error_type="TEACHING_COMPENSATION_FAILURE")
            emit("reconciliation_required", "RC1", actor_role="risk_controller", saga_id=saga_id,
                 status="NEEDS_MANUAL_RECONCILIATION", automatic_retry=False,
                 real_order_effect_count=0)
            checks = {"compensation_failure_visible": True, "false_recovery_not_claimed": True,
                      "manual_reconciliation_required": True, "real_order_effect_count_zero": True}
            terminal = "ESCALATE"
        else:
            emit("compensation_applied", "C1", actor_role="risk_controller", saga_id=saga_id,
                 action="release_paper_risk", append_only=True, open_paper_effects=0)
            emit("saga_compensated", "RC1", actor_role="orchestration_supervisor", saga_id=saga_id,
                 status="COMPENSATED", open_paper_effects=0, real_order_effect_count=0)
            checks = {"reverse_order_preserved": True, "all_paper_effects_compensated": True,
                      "audit_history_append_only": True, "real_order_effect_count_zero": True}
            terminal = "COMPENSATED"
        result = {"artifact_type": "rate_saga_compensation_eval", "passed": all(checks.values()),
                  "checks": checks, "terminal_action": terminal, "effect_count": 0,
                  "saga_id": saga_id}
        emit("eval_completed", "E1", passed=result["passed"], output=result)
        return result

    def _run_release(self, scenario, emit):
        """Promote or roll back a version-bound candidate using eval and SLO gates."""
        current = {"release_id": "rates-agent-r9", "model": "model-a", "prompt_sha256": "prompt-v3",
                   "graph_version": "dynamic-graph-v1", "risk_policy_version": "risk-v3"}
        candidate = {"release_id": "rates-agent-r10", "model": "model-b", "prompt_sha256": "prompt-v4",
                     "graph_version": "dynamic-graph-v2", "risk_policy_version": "risk-v3"}
        candidate["bundle_sha256"] = _canonical_sha256(candidate)
        emit("release_bundle_created", "RB1", actor_role="runtime_supervisor",
             current=current, candidate=candidate, immutable=True)
        emit("release_golden_eval_completed", "GE1", actor_role="risk_controller",
             release_id=candidate["release_id"], passed=True, score=1.0,
             checks={"paper_only": True, "forbidden_tools_absent": True, "trace_complete": True})
        emit("shadow_run_started", "SH1", actor_role="orchestration_supervisor",
             release_id=candidate["release_id"], traffic_percent=0,
             same_input_as_current=True, result_authority=False)
        shadow = {"semantic_match": True, "paper_only": True, "p95_latency_ms": 730,
                  "tokens_per_run": 720, "published_results": 0}
        emit("shadow_comparison_completed", "SH1", actor_role="risk_controller", passed=True,
             metrics=shadow)
        emit("canary_started", "CA1", actor_role="orchestration_supervisor",
             release_id=candidate["release_id"], traffic_percent=5,
             current_release_id=current["release_id"])
        canary = {"golden_pass_rate": 1.0, "p95_latency_ms": 840, "tokens_per_run": 760,
                  "scope_rejection_rate": 0.0, "trace_complete_rate": 1.0}
        if scenario == "release_canary_rollback":
            canary["p95_latency_ms"] = 1680
            canary["tokens_per_run"] = 1180
        policy = {"golden_pass_rate_min": 1.0, "p95_latency_ms_max": 1200,
                  "tokens_per_run_max": 900, "trace_complete_rate_min": 1.0}
        checks = {"golden_pass_rate": canary["golden_pass_rate"] >= policy["golden_pass_rate_min"],
                  "latency_slo": canary["p95_latency_ms"] <= policy["p95_latency_ms_max"],
                  "token_budget": canary["tokens_per_run"] <= policy["tokens_per_run_max"],
                  "trace_complete": canary["trace_complete_rate"] >= policy["trace_complete_rate_min"]}
        emit("canary_gate_evaluated", "RG1", actor_role="risk_controller",
             passed=all(checks.values()), policy=policy, metrics=canary, checks=checks)
        if all(checks.values()):
            emit("release_promoted", "RG1", actor_role="orchestration_supervisor",
                 from_release=current["release_id"], to_release=candidate["release_id"],
                 traffic_percent=100, paper_only=True, effect_count=0)
            eval_checks = {"bundle_version_bound": True, "shadow_had_no_authority": True,
                           "canary_gate_passed": True, "promotion_audited": True}
            terminal = "PROMOTE"
        else:
            emit("canary_allocation_stopped", "CA1", actor_role="orchestration_supervisor",
                 release_id=candidate["release_id"], failed_checks=[name for name, ok in checks.items() if not ok])
            emit("release_rolled_back", "RG1", actor_role="runtime_supervisor",
                 active_release=current["release_id"], candidate_traffic_percent=0,
                 candidate_traces_preserved=True, effect_count=0)
            eval_checks = {"breach_detected": True, "new_candidate_traffic_zero": True,
                           "current_release_restored": True, "candidate_trace_preserved": True}
            terminal = "ROLLBACK"
        result = {"artifact_type": "rate_agent_release_eval", "passed": all(eval_checks.values()),
                  "checks": eval_checks, "canary_checks": checks, "terminal_action": terminal,
                  "active_release": candidate["release_id"] if terminal == "PROMOTE" else current["release_id"],
                  "effect_count": 0}
        emit("eval_completed", "E1", passed=result["passed"], output=result)
        return result

    def _run_memory(self, scenario, run_id, emit):
        private_short_term = {
            "strategy_scope": "2s10s_only", "preferred_horizon_days": 20,
            "requester_email": "student@example.invalid", "api_key": "teaching-secret-token",
            "guardrails": {"paper_only": True, "automatic_execution": False},
        }
        emit("short_term_memory_created", "CT1", retention="run_only",
             field_names=sorted(private_short_term), contains_sensitive_fields=True)
        before = len(self.memory_store.read_scope("2s10s_preferences"))
        if scenario == "memory_privacy_block":
            violations = _privacy_violations(private_short_term)
            try:
                self.memory_store.append({"scope": "2s10s_preferences", "content": private_short_term})
            except ValueError:
                safe_audit = {"passed": True, "effect_count": 0,
                              "rejected_fields": violations,
                              "reason": "raw sensitive values cannot enter long-term memory"}
                emit("memory_write_blocked", "TG1", **safe_audit)
            after = len(self.memory_store.read_scope("2s10s_preferences"))
            checks = {"privacy_gate_blocked_write": True, "long_term_store_unchanged": before == after,
                      "secret_absent_from_audit": "teaching-secret-token" not in json.dumps(safe_audit)}
        else:
            clean, redacted_fields = _redact(private_short_term)
            emit("privacy_redaction_completed", "TG1", passed=True,
                 redacted_fields=redacted_fields, retained_fields=["strategy_scope", "preferred_horizon_days", "guardrails"])
            record = {"scope": "2s10s_preferences", "kind": "research_preference",
                      "content": clean, "provenance": {"run_id": run_id, "source": "explicit_user_session"},
                      "privacy": {"redacted": True, "redacted_fields": redacted_fields}}
            stored = self.memory_store.append(record)
            emit("long_term_memory_written", "LG1", memory=stored, storage="append_only_jsonl")
            retrieved = self.memory_store.read_scope("2s10s_preferences")[-1]
            emit("long_term_memory_retrieved", "RG1", memory=retrieved,
                 retrieval_policy="exact_scope_latest", provenance=retrieved["provenance"])
            checks = {"short_term_not_persisted_raw": not _privacy_violations(stored),
                      "long_term_memory_has_provenance": bool(stored.get("provenance")),
                      "retrieved_content_hash_matches": stored["content_sha256"] == retrieved["content_sha256"],
                      "paper_only_preserved": retrieved["content"]["guardrails"]["paper_only"] is True}
        emit("short_term_memory_discarded", "CT1", discarded=True,
             reason="run boundary reached; only sanitized long-term record may survive")
        result = {"artifact_type": "rate_memory_eval", "passed": all(checks.values()), "checks": checks,
                  "memory_layers": {"short_term": "run_only", "long_term": "sanitized_append_only"}}
        emit("eval_completed", "E1", passed=result["passed"], output=result)
        return result

    def _run_handoff(self, scenario, emit):
        emit("agent_role_activated", "P1", actor_role="strategy_analyst",
             role_contract=deepcopy(ROLE_CONTRACTS["strategy_analyst"]))
        payload = {"intent": "RUN_2S10S_PAPER_RESEARCH", "evidence_ids": ["DGS2", "DGS10"],
                   "guardrails": {"paper_only": True, "automatic_execution": False}}
        first = _handoff("strategy_analyst", "risk_controller", payload)
        if scenario == "handoff_contract_reject":
            first["payload"]["guardrails"]["automatic_execution"] = True
            first["contract_sha256"] = _canonical_sha256({key: first[key] for key in first if key != "contract_sha256"})
        emit("handoff_contract_created", "P1", actor_role="strategy_analyst",
             recipient_role="risk_controller", handoff=first)
        emit("handoff_validation_started", "L1", actor_role="risk_controller",
             sender_role="strategy_analyst", contract_sha256=first["contract_sha256"])
        validation = validate_handoff(first)
        emit("handoff_validation_completed", "L1", actor_role="risk_controller", **validation)
        if not validation["passed"]:
            emit("handoff_rejected", "L1", actor_role="risk_controller",
                 sender_role="strategy_analyst", effect_count=0, reasons=validation["reasons"])
            checks = {"unsafe_handoff_rejected": True, "downstream_not_activated": True,
                      "automatic_execution_disabled": True, "effect_count_zero": True}
        else:
            emit("handoff_accepted", "L1", actor_role="risk_controller",
                 sender_role="strategy_analyst", contract_sha256=first["contract_sha256"])
            emit("agent_role_activated", "L1", actor_role="risk_controller",
                 role_contract=deepcopy(ROLE_CONTRACTS["risk_controller"]))
            risk_payload = deepcopy(payload)
            risk_payload["risk_decision"] = "APPROVED_FOR_FIXED_PAPER_RUNTIME"
            second = _handoff("risk_controller", "runtime_supervisor", risk_payload)
            emit("handoff_contract_created", "L1", actor_role="risk_controller",
                 recipient_role="runtime_supervisor", handoff=second)
            emit("handoff_validation_started", "AZ1", actor_role="runtime_supervisor",
                 sender_role="risk_controller", contract_sha256=second["contract_sha256"])
            second_validation = validate_handoff(second)
            emit("handoff_validation_completed", "AZ1", actor_role="runtime_supervisor", **second_validation)
            emit("handoff_accepted", "AZ1", actor_role="runtime_supervisor",
                 sender_role="risk_controller", contract_sha256=second["contract_sha256"])
            emit("agent_role_activated", "R1", actor_role="runtime_supervisor",
                 role_contract=deepcopy(ROLE_CONTRACTS["runtime_supervisor"]))
            checks = {"analyst_to_risk_contract_valid": validation["passed"],
                      "risk_to_runtime_contract_valid": second_validation["passed"],
                      "evidence_ids_preserved": second["payload"]["evidence_ids"] == payload["evidence_ids"],
                      "automatic_execution_disabled": second["payload"]["guardrails"]["automatic_execution"] is False}
        result = {"artifact_type": "rate_multi_agent_handoff_eval", "passed": all(checks.values()),
                  "checks": checks, "role_contracts": deepcopy(ROLE_CONTRACTS)}
        emit("eval_completed", "E1", passed=result["passed"], output=result)
        return result

    def _run_orchestration(self, scenario, emit):
        """Run a deterministic supervisor policy without adding execution authority."""
        policy = {"max_assignments": 5, "max_revisions": 2, "token_budget": 1200,
                  "deadline_ms": 5000, "single_owner": True}
        counters = {"assignments": 0, "revisions": 0, "tokens_used": 0}

        def budget():
            return {**counters, "assignments_remaining": policy["max_assignments"] - counters["assignments"],
                    "revisions_remaining": policy["max_revisions"] - counters["revisions"],
                    "tokens_remaining": policy["token_budget"] - counters["tokens_used"]}

        def decide(action, reason, from_owner=None, to_owner=None):
            emit("orchestration_decision_recorded", "OS1", actor_role="orchestration_supervisor",
                 action=action, reason=reason, from_owner=from_owner, to_owner=to_owner,
                 budget=budget(), authority_changed=False)

        def assign(role, worker, reason, tokens=0, action="ASSIGN", previous=None):
            counters["assignments"] += 1
            counters["tokens_used"] += tokens
            decide(action, reason, previous, worker)
            emit("task_ownership_changed", "OS1", actor_role="orchestration_supervisor",
                 assignment_id="2s10s-research-1", from_owner=previous, to_owner=worker,
                 assignee_role=role, ownership_version=counters["assignments"], single_owner=True)
            emit("orchestration_budget_updated", "OS1", actor_role="orchestration_supervisor", **budget())
            emit("agent_role_activated", "OS1" if role == "orchestration_supervisor" else
                 "P1" if role == "strategy_analyst" else "L1" if role == "risk_controller" else "R1",
                 actor_role=role, worker_id=worker,
                 role_contract=deepcopy(ROLE_CONTRACTS[role]))
            emit("agent_task_started", "P1" if role == "strategy_analyst" else
                 "L1" if role == "risk_controller" else "R1", actor_role=role,
                 worker_id=worker, assignment_id="2s10s-research-1")

        emit("orchestration_started", "OS1", actor_role="orchestration_supervisor",
             policy=deepcopy(policy), strategy_scope="2s10s_only")
        emit("agent_role_activated", "OS1", actor_role="orchestration_supervisor",
             role_contract=deepcopy(ROLE_CONTRACTS["orchestration_supervisor"]))
        emit("task_envelope_created", "OS1", actor_role="orchestration_supervisor",
             assignment_id="2s10s-research-1", required_output="strategy_handoff_v1",
             allowed_roles=["strategy_analyst", "risk_controller", "runtime_supervisor"],
             guardrails={"paper_only": True, "automatic_execution": False})

        assign("strategy_analyst", "analyst-worker-a", "initial 2s10s analysis", tokens=220)

        if scenario == "orchestration_timeout_reassign":
            emit("agent_timeout_detected", "P1", actor_role="strategy_analyst",
                 worker_id="analyst-worker-a", elapsed_ms=5000, output_committed=False)
            emit("task_ownership_revoked", "OS1", actor_role="orchestration_supervisor",
                 owner="analyst-worker-a", reason="lease expired before output commit")
            assign("strategy_analyst", "analyst-worker-b", "healthy worker takes the same bounded task",
                   tokens=220, action="REASSIGN", previous="analyst-worker-a")

        unsafe = scenario == "orchestration_authority_block"
        proposed_dv01 = 180 if scenario in {"orchestration_revision", "orchestration_loop_block"} else 80
        emit("agent_task_completed", "P1", actor_role="strategy_analyst",
             worker_id="analyst-worker-b" if scenario == "orchestration_timeout_reassign" else "analyst-worker-a",
             assignment_id="2s10s-research-1", output={"intent": "RUN_2S10S_PAPER_RESEARCH",
             "dv01_usd_per_bp": proposed_dv01, "automatic_execution": unsafe,
             "evidence_ids": ["DGS2", "DGS10"]})

        if unsafe:
            emit("orchestration_authority_violation_detected", "OS1",
                 actor_role="orchestration_supervisor", requested="automatic_execution=true",
                 allowed="paper_only proposal", authority_changed=False, effect_count=0)
            decide("STOP", "authority escalation rejected before risk or runtime",
                   "analyst-worker-a", None)
            emit("orchestration_stopped", "OS1", actor_role="orchestration_supervisor",
                 reason="authority_violation", safe_stop=True, effect_count=0)
            checks = {"authority_escalation_blocked": True, "runtime_not_activated": True,
                      "effect_count_zero": True, "paper_only_preserved": True}
        else:
            assign("risk_controller", "risk-worker-a", "independent risk review", previous="analyst-worker-b" if scenario == "orchestration_timeout_reassign" else "analyst-worker-a")
            emit("risk_review_completed", "L1", actor_role="risk_controller",
                 approved=proposed_dv01 <= 100, proposed_dv01=proposed_dv01,
                 limit_dv01=100, may_rewrite_strategy=False)

            if scenario in {"orchestration_revision", "orchestration_loop_block"}:
                counters["revisions"] += 1
                decide("RETURN", "DV01 180 exceeds approved limit 100", "risk-worker-a", "analyst-worker-a")
                emit("task_returned_for_revision", "OS1", actor_role="orchestration_supervisor",
                     revision=counters["revisions"], reason_code="DV01_LIMIT", requested_change="reduce DV01 to <= 100")
                assign("strategy_analyst", "analyst-worker-a", "bounded revision", tokens=180,
                       previous="risk-worker-a")
                emit("agent_task_completed", "P1", actor_role="strategy_analyst",
                     worker_id="analyst-worker-a", assignment_id="2s10s-research-1",
                     output={"intent": "RUN_2S10S_PAPER_RESEARCH", "dv01_usd_per_bp": 80,
                             "automatic_execution": False, "evidence_ids": ["DGS2", "DGS10"]})
                assign("risk_controller", "risk-worker-a", "review revised proposal", previous="analyst-worker-a")

                if scenario == "orchestration_loop_block":
                    counters["revisions"] += 1
                    emit("risk_review_completed", "L1", actor_role="risk_controller",
                         approved=False, proposed_dv01=80, limit_dv01=100,
                         reason="duplicate semantic return without new requirement")
                    decide("RETURN", "second semantically identical return", "risk-worker-a", "analyst-worker-a")
                    emit("orchestration_loop_detected", "OS1", actor_role="orchestration_supervisor",
                         signature="risk-worker-a:DV01_LIMIT", occurrences=2,
                         max_revisions=policy["max_revisions"])
                    decide("STOP", "revision loop budget exhausted", "risk-worker-a", None)
                    emit("orchestration_stopped", "OS1", actor_role="orchestration_supervisor",
                         reason="revision_loop", safe_stop=True, effect_count=0)
                    checks = {"loop_detected": True, "revision_budget_enforced": True,
                              "runtime_not_activated": True, "effect_count_zero": True}
                else:
                    emit("risk_review_completed", "L1", actor_role="risk_controller",
                         approved=True, proposed_dv01=80, limit_dv01=100,
                         may_rewrite_strategy=False)

            if scenario != "orchestration_loop_block":
                assign("runtime_supervisor", "runtime-worker-a", "risk-approved fixed paper runtime",
                       previous="risk-worker-a")
                emit("paper_runtime_mapped", "R1", actor_role="runtime_supervisor",
                     graph="fixed_2s10s_paper_runtime", paper_only=True,
                     automatic_execution=False, effect_count=0)
                decide("COMPLETE", "fixed paper runtime accepted the approved envelope",
                       "runtime-worker-a", None)
                checks = {"single_owner_preserved": True, "budget_not_exceeded": counters["assignments"] <= policy["max_assignments"],
                          "authority_unchanged": True, "paper_only_preserved": True}
                if scenario == "orchestration_revision":
                    checks["revision_then_approved"] = counters["revisions"] == 1
                if scenario == "orchestration_timeout_reassign":
                    checks["timed_out_owner_revoked_before_reassign"] = True

        result = {"artifact_type": "rate_supervisor_orchestration_eval",
                  "passed": all(checks.values()), "checks": checks,
                  "policy": policy, "budget": budget(), "terminal_action": "STOP" if scenario in {
                      "orchestration_loop_block", "orchestration_authority_block"} else "COMPLETE"}
        emit("eval_completed", "E1", passed=result["passed"], output=result)
        return result
