"""Model adapters for the learning runtime.

FakeModel is deterministic and can intentionally produce good, bad, malformed,
or looping responses so Runtime guards are observable. OpenAIModel normalizes
provider-specific Responses API output into the same tiny runtime contract.
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


FAKE_SCENARIOS = {
    "success": {
        "tool_name": "calculator",
        "arguments": {"a": 10, "b": 20, "operation": "add"},
    },
    "unknown_tool": {
        "tool_name": "weather_machine",
        "arguments": {"city": "Irvine"},
    },
    "missing_argument": {
        "tool_name": "calculator",
        "arguments": {"a": 10, "operation": "add"},
    },
    "invalid_operation": {
        "tool_name": "calculator",
        "arguments": {"a": 10, "b": 20, "operation": "divide"},
    },
    "malformed_response": {
        "response": {
            "type": "tool_call",
            "tool_name": "calculator",
            "arguments": "this should have been a dictionary",
        }
    },
    "infinite_loop": {
        "tool_name": "calculator",
        "arguments": {"a": 1, "b": 1, "operation": "add"},
    },
}


class FakeModel:
    """Deterministic stand-in used to test runtime mechanics."""

    def __init__(self, scenario: str = "success"):
        if scenario not in FAKE_SCENARIOS:
            raise ValueError(f"Unknown fake scenario: {scenario}")
        self.scenario = scenario
        self.turn = 0

    def _tool_call(self, proposal: dict) -> dict:
        self.turn += 1
        return {
            "type": "tool_call",
            "response_id": f"fake-response-{self.scenario}-{self.turn}",
            "call_id": f"fake-call-{self.scenario}-{self.turn}",
            "tool_name": proposal["tool_name"],
            "arguments": dict(proposal["arguments"]),
        }

    def start(self, user_message: str) -> dict:
        scenario = FAKE_SCENARIOS[self.scenario]
        if "response" in scenario:
            return dict(scenario["response"])
        return self._tool_call(scenario)

    def continue_with_tool_result(
        self,
        *,
        previous_response_id,
        call_id,
        tool_name,
        result,
    ) -> dict:
        if self.scenario == "infinite_loop":
            return self._tool_call(FAKE_SCENARIOS["infinite_loop"])

        if isinstance(result, dict) and "error" in result:
            error = result["error"]
            return {
                "type": "final",
                "content": f"Tool call failed [{error['code']}]: {error['message']}",
            }

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
                    "output": json.dumps(result) if isinstance(result, dict) else str(result),
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
