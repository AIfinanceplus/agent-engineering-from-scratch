"""V4 Tool objects: one source of truth for each Runtime capability.

V3 stored a Tool's function, validation rules, model schema, and retry policy in
separate places. V4 groups those facts into a single Tool object so Registry,
Runtime, and Model adapters all read the same definition.
"""

from dataclasses import dataclass
from numbers import Real
from typing import Callable


RETRYABLE_ERRORS = (TimeoutError, ConnectionError)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    function: Callable
    max_retries: int = 0
    retryable_errors: tuple[type[Exception], ...] = RETRYABLE_ERRORS

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
        """Small serializable view used by the teaching visualizer."""
        return {
            "name": self.name,
            "description": self.description,
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


CALCULATOR_TOOL = Tool(
    name="calculator",
    description="Perform a basic arithmetic calculation.",
    parameters=ARITHMETIC_PARAMETERS,
    function=calculator,
    max_retries=0,
)

FLAKY_CALCULATOR_TOOL = Tool(
    name="flaky_calculator",
    description="Teaching calculator that may transiently time out before succeeding.",
    parameters=ARITHMETIC_PARAMETERS,
    function=flaky_calculator,
    max_retries=2,
)


# V4 Registry now maps model-visible name -> Tool object, not raw callable.
TOOL_REGISTRY: dict[str, Tool] = {
    CALCULATOR_TOOL.name: CALCULATOR_TOOL,
    FLAKY_CALCULATOR_TOOL.name: FLAKY_CALCULATOR_TOOL,
}


def resolve_tool(tool_name: str) -> Tool | None:
    """Return the complete Tool object, or None for an unknown capability."""
    return TOOL_REGISTRY.get(tool_name)


def model_tool_schemas() -> list[dict]:
    """Generate model schemas directly from the Registry's Tool objects."""
    return [tool.to_model_schema() for tool in TOOL_REGISTRY.values()]


def validate_tool_arguments(tool_name: str, arguments) -> dict:
    """Compatibility helper; Runtime now normally calls Tool.validate directly."""
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
