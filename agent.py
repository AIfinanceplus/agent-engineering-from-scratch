"""V0: the smallest useful agent loop.

This version intentionally uses a deterministic fake model so we can focus on
runtime mechanics before introducing a real model API.
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


def call_model(messages: list[dict]) -> dict:
    """Deterministic stand-in for an LLM.

    First it asks the runtime to call calculator. After receiving the tool
    observation, it produces the final answer.
    """
    last_message = messages[-1]

    if last_message["role"] == "user":
        return {
            "type": "tool_call",
            "tool_name": "calculator",
            "arguments": {
                "a": 10,
                "b": 20,
                "operation": "add",
            },
        }

    if last_message["role"] == "tool":
        return {
            "type": "final",
            "content": f"The result is {last_message['content']}.",
        }

    raise RuntimeError("Unexpected conversation state")


def run_agent(user_message: str) -> str:
    """Run the minimal Model -> Tool -> Observation -> Model loop."""
    messages = [
        {
            "role": "user",
            "content": user_message,
        }
    ]

    while True:
        response = call_model(messages)

        if response["type"] == "final":
            return response["content"]

        if response["type"] == "tool_call":
            tool_name = response["tool_name"]
            arguments = response["arguments"]

            tool = tool_registry[tool_name]
            result = tool(**arguments)

            messages.append(
                {
                    "role": "tool",
                    "name": tool_name,
                    "content": str(result),
                }
            )


if __name__ == "__main__":
    answer = run_agent("Please calculate 10 + 20.")
    print(answer)
