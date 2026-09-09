"""Untrusted model proposals and deterministic plan validation for teaching."""

from copy import deepcopy
import json
import os


SAFE_RATE_TASKS = [
    {"task_id": "D1", "tool_name": "fetch_public_rate_history", "depends_on": []},
    {"task_id": "A2", "tool_name": "prepare_rate_series", "depends_on": ["D1"]},
    {"task_id": "A10", "tool_name": "prepare_rate_series", "depends_on": ["D1"]},
    {"task_id": "J1", "tool_name": "join_rate_series", "depends_on": ["A2", "A10"]},
    {"task_id": "S1", "tool_name": "simulate_one_curve_trade", "depends_on": ["J1"]},
]
SAFE_RATE_INTENTS = {"RUN_2S10S_PAPER_SIMULATION", "ABSTAIN"}


class ModelPlanParseError(ValueError):
    """The model response was not valid JSON."""


class ModelPlanRejected(ValueError):
    """The parsed proposal exceeded the Runtime's executable contract."""

    def __init__(self, reasons):
        self.reasons = list(reasons)
        super().__init__("model plan rejected: " + "; ".join(self.reasons))


class ModelIntentRejected(ValueError):
    """A model intent failed the smaller Runtime-owned intent contract."""

    def __init__(self, reasons):
        self.reasons = list(reasons)
        super().__init__("model intent rejected: " + "; ".join(self.reasons))


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


class RatePlanModelUnavailable(RuntimeError):
    """The explicitly requested local LLM adapter cannot make a call."""


class OpenAIRatePlanModel:
    """Optional local OpenAI adapter that returns text for Runtime validation.

    The adapter never receives credentials in its prompt and cannot execute a
    Tool.  It is only constructed for explicit ``model_live`` or ``intent_live`` scenarios;
    CI continues to exercise ``ScriptedRatePlanModel`` instead.
    """

    is_real_llm = True

    def __init__(self, *, model=None, client=None, api_key=None):
        self.model_name = model or os.environ.get("RATE_OPENAI_MODEL", "gpt-5.6")
        self._client = client
        self._api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY")
        self.calls = 0

    def complete(self, prompt, *, repair_error=None):
        if not self._api_key:
            raise RatePlanModelUnavailable("OPENAI_API_KEY is required for a live model scenario")
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self._api_key)
            except Exception as exc:  # dependency/client setup is a provider boundary
                raise RatePlanModelUnavailable(f"OpenAI adapter unavailable: {exc}") from exc
        self.calls += 1
        request = {
            "role": "user",
            "content": json.dumps({
                "instruction": "Return only one JSON object matching the response_contract. You only make a proposal; Runtime has final authority.",
                "prompt": prompt,
                "repair_error": repair_error,
            }, sort_keys=True),
        }
        try:
            response = self._client.responses.create(
                model=self.model_name,
                input=[request],
                text={"format": {"type": "json_object"}},
            )
        except Exception as exc:
            raise RatePlanModelUnavailable(f"OpenAI request failed: {exc}") from exc
        output = getattr(response, "output_text", None)
        if not isinstance(output, str) or not output.strip():
            raise RatePlanModelUnavailable("OpenAI response contained no text output")
        return output


def build_plan_prompt(goal, allowed_tools):
    """Keep the model contract explicit and exclude credentials or observations."""
    approved_template = {
        "goal": "one auditable 2s10s paper simulation",
        "tasks": deepcopy(SAFE_RATE_TASKS),
        "claims": {"paper_only": True, "automatic_execution": False},
    }
    return {
        "role": "rate_plan_proposer",
        "goal": goal,
        "allowed_tools": sorted(allowed_tools),
        "response_contract": {
            "format": "JSON object only",
            "required": ["goal", "tasks", "claims"],
            "task_fields": ["task_id", "tool_name", "depends_on"],
            "constraints": ["paper_only", "no unknown tools", "acyclic dependencies", "no markdown fences"],
        },
        "approved_template": approved_template,
        "template_rule": "Return this exact task list and claims object. Do not add, remove, rename, or reorder fields or tasks.",
        "authority": "proposal_only_runtime_must_validate",
    }


def build_intent_prompt(goal):
    """A narrower model contract: propose whether to start the fixed run."""
    return {
        "role": "rate_intent_proposer",
        "goal": goal,
        "response_contract": {
            "format": "JSON object only",
            "exact_fields": ["intent", "reason"],
            "allowed_intents": sorted(SAFE_RATE_INTENTS),
            "constraints": ["no tools", "no arguments", "no orders", "no markdown fences"],
        },
        "runtime_mapping": {
            "RUN_2S10S_PAPER_SIMULATION": "Runtime maps this to its fixed paper-only task template",
            "ABSTAIN": "Runtime starts no Tools",
        },
        "decision_rule": "For this fixed paper-only teaching goal, choose RUN_2S10S_PAPER_SIMULATION unless the goal cannot be met without adding an undeclared capability; otherwise choose ABSTAIN.",
        "authority": "proposal_only_runtime_must_validate_and_map",
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


def parse_intent_proposal(raw_output):
    """Parse model text without granting it any authority."""
    return parse_plan_proposal(raw_output)


def validate_intent_proposal(proposal):
    reasons = []
    if set(proposal) != {"intent", "reason"}:
        reasons.append("intent proposal fields must be exactly intent and reason")
    intent = proposal.get("intent")
    if intent not in SAFE_RATE_INTENTS:
        reasons.append(f"intent {intent!r} is not Runtime-allowlisted")
    if not isinstance(proposal.get("reason"), str) or not proposal["reason"].strip():
        reasons.append("intent reason must be a non-empty string")
    if reasons:
        raise ModelIntentRejected(dict.fromkeys(reasons))
    return {
        "artifact_type": "validated_model_intent",
        "accepted": True,
        "intent": intent,
        "reason": proposal["reason"],
        "checks": {"schema": True, "intent_allowlist": True, "no_arguments": True, "paper_only_mapping": True},
    }


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
