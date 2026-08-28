"""V5 Tool objects: capability facts stay with the Tool.

V4 made Tool the single source of truth for function, schema, validation, and
retry policy. V5 adds one more *fact* to the Tool: risk classification.

Important boundary:
- Tool says what the capability is and how risky it is.
- PolicyEngine decides what that risk means for the current request.
"""

from dataclasses import dataclass
from numbers import Real
from typing import Callable


RETRYABLE_ERRORS = (TimeoutError, ConnectionError)
VALID_RISK_LEVELS = {"low", "medium", "high"}


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    function: Callable
    max_retries: int = 0
    retryable_errors: tuple[type[Exception], ...] = RETRYABLE_ERRORS
    risk: str = "low"

    def __post_init__(self):
        if self.risk not in VALID_RISK_LEVELS:
            raise ValueError(f"Unsupported Tool risk level: {self.risk}")

    def to_model_schema(self) -> dict:
        """Return the model-facing function schema from the same Tool object."""
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "strict": True,
        }

    def trace_metadata(self) -> dict:
        """Serializable Tool facts shown by the visual debugger."""
        return {
            "name": self.name,
            "description": self.description,
            "risk": self.risk,
            "max_retries": self.max_retries,
            "retryable_errors": [error.__name__ for error in self.retryable_errors],
        }

    def validate(self, arguments) -> dict:
        """Validate arguments against the subset of JSON Schema used here."""
        if not isinstance(arguments, dict):
            return _error("invalid_arguments", "Tool arguments must be a JSON object.")

        properties = self.parameters.get("properties", {})
        required = set(self.parameters.get("required", []))
        supplied = set(arguments)
        missing = sorted(required - supplied)

        if missing:
            return _error(
                "missing_arguments",
                f"Missing required arguments: {', '.join(missing)}",
                {"missing": missing},
            )

        if self.parameters.get("additionalProperties") is False:
            extra = sorted(supplied - set(properties))
            if extra:
                return _error(
                    "unexpected_arguments",
                    f"Unexpected arguments: {', '.join(extra)}",
                    {"extra": extra},
                )

        for name, value in arguments.items():
            rule = properties.get(name, {})
            expected_type = rule.get("type")

            if expected_type == "number":
                if not isinstance(value, Real) or isinstance(value, bool):
                    return _error(
                        "invalid_argument_type",
                        f"{name} must be a number.",
                        {"argument": name, "expected": "number"},
                    )

            if expected_type == "string" and not isinstance(value, str):
                return _error(
                    "invalid_argument_type",
                    f"{name} must be a string.",
                    {"argument": name, "expected": "string"},
                )

            allowed_values = rule.get("enum")
            if allowed_values is not None and value not in allowed_values:
                allowed_text = ", ".join(repr(item) for item in allowed_values)
                return _error(
                    "invalid_argument_value",
                    f"{name} must be one of: {allowed_text}.",
                    {"argument": name, "value": value, "allowed": allowed_values},
                )

        return {"ok": True}


def calculator(a: float, b: float, operation: str) -> float:
    """Perform the actual calculation."""
    if operation == "add":
        return a + b
    if operation == "multiply":
        return a * b
    raise ValueError(f"Unsupported operation: {operation}")


class FlakyCalculator:
    """Teaching callable that times out once, then succeeds."""

    def __init__(self):
        self.attempts = 0

    def reset(self) -> None:
        self.attempts = 0

    def __call__(self, a: float, b: float, operation: str) -> float:
        self.attempts += 1
        if self.attempts == 1:
            raise TimeoutError("Simulated transient timeout")
        return calculator(a, b, operation)


flaky_calculator = FlakyCalculator()


def send_message(recipient: str, message: str) -> str:
    """Simulated side effect used only to teach approval policy.

    No external message is actually sent. The function only returns a string,
    but the Tool is classified medium-risk so PolicyEngine can stop execution.
    """
    return f"Simulated message sent to {recipient}: {message}"


def delete_record(record_id: str) -> str:
    """Simulated destructive capability used only to teach deny policy."""
    return f"Simulated deletion of record {record_id}"


ARITHMETIC_PARAMETERS = {
    "type": "object",
    "properties": {
        "a": {"type": "number"},
        "b": {"type": "number"},
        "operation": {"type": "string", "enum": ["add", "multiply"]},
    },
    "required": ["a", "b", "operation"],
    "additionalProperties": False,
}

MESSAGE_PARAMETERS = {
    "type": "object",
    "properties": {
        "recipient": {"type": "string"},
        "message": {"type": "string"},
    },
    "required": ["recipient", "message"],
    "additionalProperties": False,
}

DELETE_PARAMETERS = {
    "type": "object",
    "properties": {
        "record_id": {"type": "string"},
    },
    "required": ["record_id"],
    "additionalProperties": False,
}


CALCULATOR_TOOL = Tool(
    name="calculator",
    description="Perform a basic arithmetic calculation.",
    parameters=ARITHMETIC_PARAMETERS,
    function=calculator,
    max_retries=0,
    risk="low",
)

FLAKY_CALCULATOR_TOOL = Tool(
    name="flaky_calculator",
    description="Teaching calculator that may transiently time out before succeeding.",
    parameters=ARITHMETIC_PARAMETERS,
    function=flaky_calculator,
    max_retries=2,
    risk="low",
)

SEND_MESSAGE_TOOL = Tool(
    name="send_message",
    description="Simulate sending a message to a recipient.",
    parameters=MESSAGE_PARAMETERS,
    function=send_message,
    max_retries=0,
    risk="medium",
)

DELETE_RECORD_TOOL = Tool(
    name="delete_record",
    description="Simulate deleting a record by identifier.",
    parameters=DELETE_PARAMETERS,
    function=delete_record,
    max_retries=0,
    risk="high",
)


TOOL_REGISTRY: dict[str, Tool] = {
    CALCULATOR_TOOL.name: CALCULATOR_TOOL,
    FLAKY_CALCULATOR_TOOL.name: FLAKY_CALCULATOR_TOOL,
    SEND_MESSAGE_TOOL.name: SEND_MESSAGE_TOOL,
    DELETE_RECORD_TOOL.name: DELETE_RECORD_TOOL,
}


def resolve_tool(tool_name: str) -> Tool | None:
    """Return the complete Tool object, or None for an unknown capability."""
    return TOOL_REGISTRY.get(tool_name)


def model_tool_schemas() -> list[dict]:
    """Generate model schemas directly from Registry Tool objects."""
    return [tool.to_model_schema() for tool in TOOL_REGISTRY.values()]


def validate_tool_arguments(tool_name: str, arguments) -> dict:
    """Compatibility helper; Runtime normally calls Tool.validate directly."""
    tool = resolve_tool(tool_name)
    if tool is None:
        return _error("unknown_tool", f"Unknown tool: {tool_name}")
    return tool.validate(arguments)


def reset_teaching_tools() -> None:
    flaky_calculator.reset()


def _error(code: str, message: str, details: dict | None = None) -> dict:
    error = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"ok": False, "error": error}
