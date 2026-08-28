"""V1: a model-agnostic agent runtime with a defensive Tool Registry boundary.

The model proposes tool calls. The runtime resolves the name, validates the
arguments, executes only valid calls, and turns failures into Observations
instead of crashing the whole agent loop.
"""

from tools import (
    TOOL_REGISTRY,
    calculator,
    resolve_tool,
    validate_tool_arguments,
)


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


def run_agent(user_message: str, model=None, on_event=None) -> str:
    """Run Model -> Registry -> Tool -> Observation -> Model until final.

    V1 adds a trust boundary around model-proposed tool calls:
    unknown names and invalid arguments become Observations instead of uncaught
    runtime exceptions.
    """
    if model is None:
        from model_adapters import FakeModel

        model = FakeModel()

    _emit(on_event, "user_input", message=user_message)
    _emit(on_event, "model_request", phase="start", message=user_message)

    response = model.start(user_message)
    _emit(on_event, "model_response", response=response)

    while True:
        if response["type"] == "final":
            _emit(on_event, "final", content=response["content"])
            return response["content"]

        if response["type"] != "tool_call":
            raise RuntimeError(f"Unknown model response type: {response['type']}")

        tool_name = response.get("tool_name", "")
        arguments = response.get("arguments")
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
