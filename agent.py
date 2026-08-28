"""V5: Agent Runtime with an explicit Policy Engine.

V4 made Tool the single source of capability facts. V5 separates capability
from permission: a valid Tool Call still cannot execute until PolicyEngine
returns ALLOW.
"""

import json

from model_validation import validate_model_response
from policy import DEFAULT_POLICY, PolicyDecision
from tools import TOOL_REGISTRY, Tool, calculator, resolve_tool


DEFAULT_MAX_STEPS = 5

tool_registry = TOOL_REGISTRY


def _emit(on_event, event_type: str, **payload) -> None:
    if on_event is not None:
        on_event({"type": event_type, **payload})


def _tool_call_key(tool_name: str, arguments: dict) -> str:
    normalized_arguments = json.dumps(
        arguments,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return f"{tool_name}:{normalized_arguments}"


def _execution_error(tool_name: str, exc: Exception) -> dict:
    return {
        "error": {
            "code": "tool_execution_error",
            "message": f"{tool_name} failed: {exc}",
        }
    }


def _execute_tool_with_retry(
    *,
    tool: Tool,
    arguments: dict,
    on_event=None,
    max_retries_override: int | None = None,
):
    """Execute one already-approved Tool using Tool-owned retry policy."""
    max_retries = tool.max_retries if max_retries_override is None else max_retries_override
    total_attempts = max_retries + 1

    for attempt in range(1, total_attempts + 1):
        _emit(
            on_event,
            "tool_attempt",
            tool_name=tool.name,
            arguments=arguments,
            attempt=attempt,
            total_attempts=total_attempts,
            retry_policy={
                "max_retries": max_retries,
                "retryable_errors": [error.__name__ for error in tool.retryable_errors],
            },
        )

        try:
            result = tool.function(**arguments)
        except tool.retryable_errors as exc:
            if attempt < total_attempts:
                _emit(
                    on_event,
                    "tool_retry",
                    tool_name=tool.name,
                    attempt=attempt,
                    next_attempt=attempt + 1,
                    error_type=exc.__class__.__name__,
                    error=str(exc),
                    policy_source="Tool.max_retries",
                )
                continue

            error = {
                "code": "tool_retry_exhausted",
                "message": (
                    f"{tool.name} still failed after {total_attempts} "
                    f"attempt(s): {exc}"
                ),
            }
            _emit(
                on_event,
                "tool_error",
                tool_name=tool.name,
                retryable=True,
                attempts=attempt,
                error=error,
            )
            return {"error": error}
        except Exception as exc:
            observation = _execution_error(tool.name, exc)
            _emit(
                on_event,
                "tool_error",
                tool_name=tool.name,
                retryable=False,
                attempts=attempt,
                error=observation["error"],
            )
            return observation
        else:
            _emit(
                on_event,
                "tool_result",
                tool_name=tool.name,
                result=result,
                attempts=attempt,
            )
            return result

    raise AssertionError("retry loop exited unexpectedly")


def _stop_agent(on_event, error: dict, *, reason: str, step: int, max_steps: int) -> str:
    content = f"Agent stopped [{error['code']}]: {error['message']}"
    _emit(
        on_event,
        "runtime_stop",
        reason=reason,
        error=error,
        step=step,
        max_steps=max_steps,
    )
    _emit(on_event, "final", content=content, stopped=True)
    return content


def _policy_observation(decision: PolicyDecision, reason: str) -> dict:
    if decision is PolicyDecision.REQUIRE_APPROVAL:
        return {
            "error": {
                "code": "approval_required",
                "message": reason,
            }
        }

    return {
        "error": {
            "code": "policy_denied",
            "message": reason,
        }
    }


def run_agent(
    user_message: str,
    model=None,
    on_event=None,
    max_steps: int = DEFAULT_MAX_STEPS,
    max_retries: int | None = None,
    policy=None,
) -> str:
    """Run the Agent Loop with deterministic policy before execution.

    Order for a Tool Call:
        Model contract → step/loop guards → Registry → Tool validation
        → Policy decision → retry/execution.

    V5 surfaces REQUIRE_APPROVAL as an Observation; actual pause/resume approval
    is intentionally deferred to a later lesson.
    """
    if not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps < 1:
        raise ValueError("max_steps must be a positive integer")
    if max_retries is not None and (
        not isinstance(max_retries, int)
        or isinstance(max_retries, bool)
        or max_retries < 0
    ):
        raise ValueError("max_retries must be None or a non-negative integer")

    if model is None:
        from model_adapters import FakeModel

        model = FakeModel()

    policy_engine = DEFAULT_POLICY if policy is None else policy
    tool_steps = 0
    seen_calls: set[str] = set()

    _emit(on_event, "user_input", message=user_message)
    _emit(on_event, "model_request", phase="start", message=user_message)

    response = model.start(user_message)
    _emit(on_event, "model_response", response=response)

    while True:
        response_validation = validate_model_response(response)
        _emit(
            on_event,
            "model_validation",
            response=response,
            validation=response_validation,
        )

        if not response_validation["ok"]:
            return _stop_agent(
                on_event,
                response_validation["error"],
                reason="invalid_model_response",
                step=tool_steps,
                max_steps=max_steps,
            )

        if response["type"] == "final":
            _emit(on_event, "final", content=response["content"], stopped=False)
            return response["content"]

        if tool_steps >= max_steps:
            error = {
                "code": "max_steps_exceeded",
                "message": (
                    f"Runtime refused another Tool Call after {max_steps} "
                    "allowed step(s)."
                ),
            }
            return _stop_agent(
                on_event,
                error,
                reason="max_steps",
                step=tool_steps,
                max_steps=max_steps,
            )

        tool_steps += 1
        tool_name = response["tool_name"]
        arguments = response["arguments"]

        _emit(
            on_event,
            "runtime_step",
            step=tool_steps,
            max_steps=max_steps,
            tool_name=tool_name,
        )

        call_key = _tool_call_key(tool_name, arguments)
        is_duplicate = call_key in seen_calls
        _emit(
            on_event,
            "duplicate_check",
            tool_name=tool_name,
            arguments=arguments,
            call_key=call_key,
            duplicate=is_duplicate,
        )

        if is_duplicate:
            observation = {
                "error": {
                    "code": "duplicate_tool_call",
                    "message": (
                        "Runtime blocked an exact repeated Tool Call. "
                        "The model should use the existing Observation or choose a new action."
                    ),
                }
            }
            _emit(
                on_event,
                "tool_rejected",
                tool_name=tool_name,
                reason="duplicate_tool_call",
                error=observation["error"],
            )
        else:
            seen_calls.add(call_key)
            tool = resolve_tool(tool_name)

            _emit(
                on_event,
                "tool_lookup",
                tool_name=tool_name,
                found=tool is not None,
                registry_keys=list(tool_registry.keys()),
                tool_metadata=tool.trace_metadata() if tool is not None else None,
            )

            if tool is None:
                validation = {
                    "ok": False,
                    "error": {
                        "code": "unknown_tool",
                        "message": f"Unknown tool: {tool_name}",
                    },
                }
            else:
                validation = tool.validate(arguments)

            _emit(
                on_event,
                "tool_validation",
                tool_name=tool_name,
                arguments=arguments,
                validation=validation,
                validator_source="Tool.validate" if tool is not None else "Registry",
            )

            if not validation["ok"]:
                observation = {"error": validation["error"]}
                _emit(
                    on_event,
                    "tool_rejected",
                    tool_name=tool_name,
                    reason="validation",
                    error=validation["error"],
                )
            else:
                policy_result = policy_engine.evaluate(tool, arguments)
                _emit(
                    on_event,
                    "policy_decision",
                    tool_name=tool.name,
                    arguments=arguments,
                    tool_risk=tool.risk,
                    policy=policy_result.to_dict(),
                )

                if policy_result.decision is not PolicyDecision.ALLOW:
                    observation = _policy_observation(
                        policy_result.decision,
                        policy_result.reason,
                    )
                    _emit(
                        on_event,
                        "tool_rejected",
                        tool_name=tool.name,
                        reason=policy_result.decision.value,
                        error=observation["error"],
                    )
                else:
                    effective_retries = tool.max_retries if max_retries is None else max_retries
                    _emit(
                        on_event,
                        "tool_execute",
                        tool_name=tool.name,
                        arguments=arguments,
                        tool_metadata=tool.trace_metadata(),
                        effective_max_retries=effective_retries,
                        retry_policy_source=(
                            "Tool.max_retries" if max_retries is None else "Runtime override"
                        ),
                    )
                    observation = _execute_tool_with_retry(
                        tool=tool,
                        arguments=arguments,
                        max_retries_override=max_retries,
                        on_event=on_event,
                    )

        _emit(
            on_event,
            "tool_observation",
            tool_name=tool_name,
            observation=observation,
        )

        _emit(
            on_event,
            "model_request",
            phase="continue",
            previous_response_id=response.get("response_id"),
            call_id=response.get("call_id"),
            tool_name=tool_name,
            result=observation,
        )

        response = model.continue_with_tool_result(
            previous_response_id=response.get("response_id"),
            call_id=response.get("call_id"),
            tool_name=tool_name,
            result=observation,
        )
        _emit(on_event, "model_response", response=response)


if __name__ == "__main__":
    answer = run_agent("Please calculate 10 + 20.")
    print(answer)
