"""Untrusted model proposals and deterministic plan validation for teaching."""

from copy import deepcopy
import json


SAFE_RATE_TASKS = [
    {"task_id": "D1", "tool_name": "fetch_public_rate_history", "depends_on": []},
    {"task_id": "A2", "tool_name": "prepare_rate_series", "depends_on": ["D1"]},
    {"task_id": "A10", "tool_name": "prepare_rate_series", "depends_on": ["D1"]},
    {"task_id": "J1", "tool_name": "join_rate_series", "depends_on": ["A2", "A10"]},
    {"task_id": "S1", "tool_name": "simulate_one_curve_trade", "depends_on": ["J1"]},
]


class ModelPlanParseError(ValueError):
    """The model response was not valid JSON."""


class ModelPlanRejected(ValueError):
    """The parsed proposal exceeded the Runtime's executable contract."""

    def __init__(self, reasons):
        self.reasons = list(reasons)
        super().__init__("model plan rejected: " + "; ".join(self.reasons))


class ScriptedRatePlanModel:
    """Repeatable teaching adapter; deliberately not presented as a real LLM."""

    model_name = "scripted-teaching-model-v1"
    is_real_llm = False

    def __init__(self, scenario):
        self.scenario = scenario
        self.calls = 0

    def complete(self, prompt, *, repair_error=None):
        self.calls += 1
        if self.scenario == "model_repair" and self.calls == 1:
            return '{"goal":"one paper simulation","tasks":['
        proposal = {
            "goal": "one auditable 2s10s paper simulation",
            "tasks": deepcopy(SAFE_RATE_TASKS),
            "claims": {
                "paper_only": True,
                "automatic_execution": False,
            },
        }
        if self.scenario == "model_unsafe":
            proposal["tasks"].append({
                "task_id": "X1",
                "tool_name": "place_real_order",
                "depends_on": ["S1"],
            })
            proposal["claims"]["automatic_execution"] = True
        return json.dumps(proposal, sort_keys=True, separators=(",", ":"))


def build_plan_prompt(goal, allowed_tools):
    """Keep the model contract explicit and exclude credentials or observations."""
    return {
        "role": "rate_plan_proposer",
        "goal": goal,
        "allowed_tools": sorted(allowed_tools),
        "response_contract": {
            "format": "JSON object only",
            "required": ["goal", "tasks", "claims"],
            "task_fields": ["task_id", "tool_name", "depends_on"],
            "constraints": ["paper_only", "no unknown tools", "acyclic dependencies"],
        },
        "authority": "proposal_only_runtime_must_validate",
    }


def parse_plan_proposal(raw_output):
    if not isinstance(raw_output, str):
        raise ModelPlanParseError("model output must be text")
    try:
        proposal = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise ModelPlanParseError(
            f"invalid JSON at line {exc.lineno} column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(proposal, dict):
        raise ModelPlanParseError("model output must decode to an object")
    return proposal


def validate_plan_proposal(proposal, *, allowed_tools, expected_tasks=None):
    """Validate schema, graph, capability allowlist and the executable template."""
    reasons = []
    if set(proposal) != {"goal", "tasks", "claims"}:
        reasons.append("proposal fields must be exactly goal, tasks and claims")
    if not isinstance(proposal.get("goal"), str) or not proposal.get("goal"):
        reasons.append("goal must be a non-empty string")
    tasks = proposal.get("tasks")
    claims = proposal.get("claims")
    if not isinstance(tasks, list) or not tasks:
        reasons.append("tasks must be a non-empty list")
        tasks = []
    if not isinstance(claims, dict):
        reasons.append("claims must be an object")
        claims = {}
    if claims.get("paper_only") is not True or claims.get("automatic_execution") is not False:
        reasons.append("plan must remain paper_only with automatic_execution=false")

    ids = []
    for index, task in enumerate(tasks):
        if not isinstance(task, dict) or set(task) != {"task_id", "tool_name", "depends_on"}:
            reasons.append(f"task {index} has invalid fields")
            continue
        task_id, tool_name, dependencies = task["task_id"], task["tool_name"], task["depends_on"]
        if not isinstance(task_id, str) or not task_id:
            reasons.append(f"task {index} has invalid task_id")
        else:
            ids.append(task_id)
        if tool_name not in allowed_tools:
            reasons.append(f"tool {tool_name!r} is not in the Runtime allowlist")
        if not isinstance(dependencies, list) or not all(isinstance(dep, str) for dep in dependencies):
            reasons.append(f"task {task_id!r} depends_on must be a string list")
    if len(ids) != len(set(ids)):
        reasons.append("task_id values must be unique")
    known = set(ids)
    for task in tasks:
        if isinstance(task, dict) and isinstance(task.get("depends_on"), list):
            unknown = [dep for dep in task["depends_on"] if dep not in known]
            if unknown:
                reasons.append(f"task {task.get('task_id')!r} has unknown dependencies {unknown}")

    # Kahn's algorithm: Runtime proves acyclicity instead of trusting the model.
    dependencies = {
        task["task_id"]: set(task["depends_on"])
        for task in tasks
        if isinstance(task, dict) and isinstance(task.get("task_id"), str)
        and isinstance(task.get("depends_on"), list)
        and all(isinstance(dep, str) for dep in task["depends_on"])
    }
    pending = dict(dependencies)
    while pending:
        ready = {task_id for task_id, deps in pending.items() if not deps}
        if not ready:
            reasons.append("task graph must be acyclic")
            break
        pending = {task_id: deps - ready for task_id, deps in pending.items() if task_id not in ready}

    expected_tasks = SAFE_RATE_TASKS if expected_tasks is None else expected_tasks
    if tasks != expected_tasks:
        reasons.append("proposal does not match the approved rate-strategy execution template")
    if reasons:
        raise ModelPlanRejected(dict.fromkeys(reasons))
    return {
        "artifact_type": "validated_model_plan",
        "accepted": True,
        "tasks": deepcopy(tasks),
        "checks": {
            "schema": True,
            "tool_allowlist": True,
            "acyclic": True,
            "paper_only": True,
            "executable_template": True,
        },
    }
