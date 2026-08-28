"""V2: a model-agnostic agent runtime with deterministic execution guards.

V1 protected the Tool boundary. V2 adds two Runtime-level guards around the
model itself:
1. validate every normalized model response before trusting its shape;
2. cap the number of tool-call attempts with MAX_STEPS.
"""

from model_validation import validate_model_response
from tools import (
    TOOL_REGISTRY,
    calculator,
    resolve_tool,
    validate_tool_arguments,
)


DEFAULT_MAX_STEPS = 5

# Backwards-compatible public name used by earlier lessons/tests.
tool_registry = TOOL_REGISTRY


def _emit(on_event, event_type: str, **payload) -> None:
    """Send a read-only execution event to an optional observer."""
    if on_event is not None:
        on_event({"type": event_type, **payload})


def _execution_error(tool_name: str, exc: Exception) -> dict:
    """Normalize a Python exception into a model-visible Observation."""
    return {
        "error": {
            "code": "tool_execution_error",
            "message": f"{tool_name} failed: {exc}",
        }
    }


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
) -> str:
    """Run the Agent Loop with model validation and a deterministic step cap.

    `max_steps` counts attempted Tool Calls, not model responses. A final answer
    may arrive after the last allowed Tool Call, but an additional Tool Call is
    rejected before execution.
    """
    if not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps < 1:
        raise ValueError("max_steps must be a positive integer")

    if model is None:
        from model_adapters import FakeModel

        model = FakeModel()

    tool_steps = 0

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
        _emit(
            on_event,
            "runtime_step",
            step=tool_steps,
            max_steps=max_steps,
            tool_name=response["tool_name"],
        )

        tool_name = response["tool_name"]
        arguments = response["arguments"]
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
                error=validation["error"],
            )
        else:
            _emit(
                on_event,
                "tool_execute",
                tool_name=tool_name,
                arguments=arguments,
            )

            try:
                observation = tool(**arguments)
            except Exception as exc:
                observation = _execution_error(tool_name, exc)
                _emit(
                    on_event,
                    "tool_error",
                    tool_name=tool_name,
                    error=observation["error"],
                )
            else:
                _emit(
                    on_event,
                    "tool_result",
                    tool_name=tool_name,
                    result=observation,
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
