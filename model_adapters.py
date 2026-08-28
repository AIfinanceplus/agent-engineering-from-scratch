"""Model adapters for the learning runtime.

FakeModel is deterministic and used by tests.
OpenAIModel uses the Responses API but normalizes provider-specific output into
one tiny runtime-facing contract: either `tool_call` or `final`.
"""

import json


CALCULATOR_TOOL_SCHEMA = {
    "type": "function",
    "name": "calculator",
    "description": "Perform a basic arithmetic calculation.",
    "parameters": {
        "type": "object",
        "properties": {
            "a": {"type": "number"},
            "b": {"type": "number"},
            "operation": {
                "type": "string",
                "enum": ["add", "multiply"],
            },
        },
        "required": ["a", "b", "operation"],
        "additionalProperties": False,
    },
    "strict": True,
}


class FakeModel:
    """Deterministic stand-in used to test runtime mechanics."""

    def start(self, user_message: str) -> dict:
        return {
            "type": "tool_call",
            "response_id": "fake-response-1",
            "call_id": "fake-call-1",
            "tool_name": "calculator",
            "arguments": {
                "a": 10,
                "b": 20,
                "operation": "add",
            },
        }

    def continue_with_tool_result(
        self,
        *,
        previous_response_id,
        call_id,
        tool_name,
        result,
    ) -> dict:
        return {
            "type": "final",
            "content": f"The result is {result}.",
        }


class OpenAIModel:
    """OpenAI Responses API adapter.

    The API key is read by the OpenAI SDK from the OPENAI_API_KEY environment
    variable. No secret is stored in this repository.
    """

    def __init__(self, model: str = "gpt-5.6"):
        from openai import OpenAI

        self.client = OpenAI()
        self.model = model
        self.tools = [CALCULATOR_TOOL_SCHEMA]

    def start(self, user_message: str) -> dict:
        response = self.client.responses.create(
            model=self.model,
            input=user_message,
            tools=self.tools,
        )
        return self._normalize(response)

    def continue_with_tool_result(
        self,
        *,
        previous_response_id,
        call_id,
        tool_name,
        result,
    ) -> dict:
        if not previous_response_id or not call_id:
            raise RuntimeError("OpenAI tool continuation requires response_id and call_id")

        response = self.client.responses.create(
            model=self.model,
            previous_response_id=previous_response_id,
            input=[
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": str(result),
                }
            ],
            tools=self.tools,
        )
        return self._normalize(response)

    @staticmethod
    def _normalize(response) -> dict:
        for item in response.output:
            if item.type == "function_call":
                return {
                    "type": "tool_call",
                    "response_id": response.id,
                    "call_id": item.call_id,
                    "tool_name": item.name,
                    "arguments": json.loads(item.arguments),
                }

        return {
            "type": "final",
            "content": response.output_text,
        }
