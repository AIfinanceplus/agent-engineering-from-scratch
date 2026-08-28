"""V0.2: a minimal model-agnostic agent runtime with observable execution.

The runtime still controls execution exactly as before. The only new idea is an
optional `on_event` callback that lets a debugger observe what is happening
without changing the decisions made by the model or the runtime.
"""


def calculator(a: float, b: float, operation: str) -> float:
    """A real Python function that performs the work."""
    if operation == "add":
        return a + b
    if operation == "multiply":
        return a * b
    raise ValueError(f"Unsupported operation: {operation}")


# Runtime-side mapping from model-visible tool name to real implementation.
tool_registry = {
    "calculator": calculator,
}


def _emit(on_event, event_type: str, **payload) -> None:
    """Send a read-only execution event to an optional observer.

    This is instrumentation, not control logic: the observer can see what the
    runtime is doing, but it cannot decide which tool runs next.
    """
    if on_event is not None:
        on_event({"type": event_type, **payload})


def run_agent(user_message: str, model=None, on_event=None) -> str:
    """Run Model -> Tool -> Observation -> Model until a final answer exists.

    `model` is intentionally injected so the runtime remains provider-agnostic.
    `on_event` is optional and exists only for tracing / visualization.
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

        tool_name = response["tool_name"]
        arguments = response["arguments"]

        _emit(
            on_event,
            "tool_lookup",
            tool_name=tool_name,
            registry_keys=list(tool_registry.keys()),
        )

        tool = tool_registry[tool_name]

        _emit(
            on_event,
            "tool_execute",
            tool_name=tool_name,
            arguments=arguments,
        )
        result = tool(**arguments)
        _emit(
            on_event,
            "tool_result",
            tool_name=tool_name,
            result=result,
        )

        _emit(
            on_event,
            "model_request",
            phase="continue",
            previous_response_id=response.get("response_id"),
            call_id=response.get("call_id"),
            tool_name=tool_name,
            result=result,
        )

        response = model.continue_with_tool_result(
            previous_response_id=response.get("response_id"),
            call_id=response.get("call_id"),
            tool_name=tool_name,
            result=result,
        )
        _emit(on_event, "model_response", response=response)


if __name__ == "__main__":
    answer = run_agent("Please calculate 10 + 20.")
    print(answer)
