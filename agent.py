"""V3: a model-agnostic Agent Runtime with retry and loop detection.

V1 protected the Tool boundary. V2 constrained the model with response
validation and MAX_STEPS. V3 adds two different protections:

1. Runtime retry for transient Tool failures such as TimeoutError.
2. Exact duplicate Tool Call detection for model-level loops.

A retry is the Runtime repeating the SAME approved action because execution
failed transiently. A duplicate Tool Call is the MODEL proposing the same
action again after an Observation. They are intentionally different concepts.
"""

import json

from model_validation import validate_model_response
from tools import (
    TOOL_REGISTRY,
    calculator,
    resolve_tool,
    validate_tool_arguments,
)


DEFAULT_MAX_STEPS = 5
DEFAULT_MAX_RETRIES = 2
RETRYABLE_ERRORS = (TimeoutError, ConnectionError)

# Backwards-compatible public name used by earlier lessons/tests.
tool_registry = TOOL_REGISTRY


def _emit(on_event, event_type: str, **payload) -> None:
    """Send a read-only execution event to an optional observer."""
    if on_event is not None:
        on_event({"type": event_type, **payload})


def _tool_call_key(tool_name: str, arguments: dict) -> str:
    """Create a stable identity for one model-proposed action.

    Sorting JSON keys means {"a": 1, "b": 2} and {"b": 2, "a": 1}
    are treated as the same action.
    """
    normalized_arguments = json.dumps(
        arguments,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return f"{tool_name}:{normalized_arguments}"


def _execution_error(tool_name: str, exc: Exception) -> dict:
    """Normalize a non-retryable Python exception into an Observation."""
    return {
        "error": {
            "code": "tool_execution_error",
            "message": f"{tool_name} failed: {exc}",
        }
    }


def _execute_tool_with_retry(
    *,
    tool_name: str,
    tool,
    arguments: dict,
    max_retries: int,
    on_event=None,
):
    """Execute one Tool Call, retrying only transient failures.

    max_retries=2 means at most 3 total execution attempts:
    initial attempt + retry #1 + retry #2.

    These retries remain inside ONE model step. The model is not consulted
    between attempts because the Runtime is repeating the exact same action.
    """
    total_attempts = max_retries + 1

    for attempt in range(1, total_attempts + 1):
        _emit(
            on_event,
            "tool_attempt",
            tool_name=tool_name,
            arguments=arguments,
            attempt=attempt,
            total_attempts=total_attempts,
        )

        try:
            result = tool(**arguments)
        except RETRYABLE_ERRORS as exc:
            if attempt < total_attempts:
                _emit(
                    on_event,
                    "tool_retry",
                    tool_name=tool_name,
                    attempt=attempt,
                    next_attempt=attempt + 1,
                    error_type=exc.__class__.__name__,
                    error=str(exc),
                )
                continue

            error = {
                "code": "tool_retry_exhausted",
                "message": (
                    f"{tool_name} still failed after {total_attempts} "
                    f"attempt(s): {exc}"
                ),
            }
            _emit(
                on_event,
                "tool_error",
                tool_name=tool_name,
                retryable=True,
                attempts=attempt,
                error=error,
            )
            return {"error": error}
        except Exception as exc:
            observation = _execution_error(tool_name, exc)
            _emit(
                on_event,
                "tool_error",
                tool_name=tool_name,
                retryable=False,
                attempts=attempt,
                error=observation["error"],
            )
            return observation
        else:
            _emit(
                on_event,
                "tool_result",
                tool_name=tool_name,
                result=result,
                attempts=attempt,
            )
            return result

    raise AssertionError("retry loop exited unexpectedly")


def _stop_agent(on_event, error: dict, *, reason: str, step: int, max_steps: int) -> str:
    """Stop the Runtime safely and expose the reason as trace data."""
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


def run_agent(
    user_message: str,
    model=None,
    on_event=None,
    max_steps: int = DEFAULT_MAX_STEPS,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> str:
    """Run the Agent Loop with deterministic Runtime guards.

    `max_steps` counts model-proposed Tool Calls.
    `max_retries` counts extra Runtime execution attempts for one Tool Call.
    """
    if not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps < 1:
        raise ValueError("max_steps must be a positive integer")
    if not isinstance(max_retries, int) or isinstance(max_retries, bool) or max_retries < 0:
        raise ValueError("max_retries must be a non-negative integer")

    if model is None:
        from model_adapters import FakeModel

        model = FakeModel()

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
            # Remember the model action before execution. Runtime retries happen
            # internally and do NOT create new entries in this set.
            seen_calls.add(call_key)

            tool = resolve_tool(tool_name)
            _emit(
                on_event,
                "tool_lookup",
                tool_name=tool_name,
                found=tool is not None,
                registry_keys=list(tool_registry.keys()),
            )

            validation = validate_tool_arguments(tool_name, arguments)
            _emit(
                on_event,
                "tool_validation",
                tool_name=tool_name,
                arguments=arguments,
                validation=validation,
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
                _emit(
                    on_event,
                    "tool_execute",
                    tool_name=tool_name,
                    arguments=arguments,
                    max_retries=max_retries,
                )
                observation = _execute_tool_with_retry(
                    tool_name=tool_name,
                    tool=tool,
                    arguments=arguments,
                    max_retries=max_retries,
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
