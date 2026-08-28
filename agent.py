"""V0.1: a minimal model-agnostic agent runtime.

The runtime knows how to execute tool calls, but it does not know which model
provider is being used. A model adapter decides whether the next step is a tool
call or a final answer.
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


def run_agent(user_message: str, model=None) -> str:
    """Run Model -> Tool -> Observation -> Model until a final answer exists.

    `model` is intentionally injected. That keeps the runtime independent from
    OpenAI or any other model provider.
    """
    if model is None:
        from model_adapters import FakeModel

        model = FakeModel()

    response = model.start(user_message)

    while True:
        if response["type"] == "final":
            return response["content"]

        if response["type"] != "tool_call":
            raise RuntimeError(f"Unknown model response type: {response['type']}")

        tool_name = response["tool_name"]
        arguments = response["arguments"]

        tool = tool_registry[tool_name]
        result = tool(**arguments)

        response = model.continue_with_tool_result(
            previous_response_id=response.get("response_id"),
            call_id=response.get("call_id"),
            tool_name=tool_name,
            result=result,
        )


if __name__ == "__main__":
    answer = run_agent("Please calculate 10 + 20.")
    print(answer)
