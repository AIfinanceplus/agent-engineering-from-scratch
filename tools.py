"""V3 tool registry helpers.

The registry still maps model-visible names to callables. V3 adds one special
teaching tool, ``flaky_calculator``, that fails once with TimeoutError and then
succeeds. This lets the Runtime demonstrate transient-error retry behavior
without using a real network dependency.
"""

from numbers import Real
from typing import Callable


def calculator(a: float, b: float, operation: str) -> float:
    """Perform the actual calculation."""
    if operation == "add":
        return a + b
    if operation == "multiply":
        return a * b
    raise ValueError(f"Unsupported operation: {operation}")


class FlakyCalculator:
    """Deterministic callable that times out once, then delegates to calculator.

    The mutable counter is only for the V3 teaching scenario. Production retry
    tests would normally use a fake/mocked external dependency instead.
    """

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


# V3 registry: model-visible name -> executable Python callable.
TOOL_REGISTRY: dict[str, Callable] = {
    "calculator": calculator,
    "flaky_calculator": flaky_calculator,
}


# Runtime validation rules stay deterministic and outside the model.
TOOL_ARGUMENT_RULES = {
    "calculator": {
        "required": {"a", "b", "operation"},
        "allowed": {"a", "b", "operation"},
    },
    "flaky_calculator": {
        "required": {"a", "b", "operation"},
        "allowed": {"a", "b", "operation"},
    },
}


def reset_teaching_tools() -> None:
    """Reset mutable teaching-tool state before a deterministic scenario."""
    flaky_calculator.reset()


def resolve_tool(tool_name: str):
    """Return the executable callable, or None for an unknown tool name."""
    return TOOL_REGISTRY.get(tool_name)


def validate_tool_arguments(tool_name: str, arguments) -> dict:
    """Validate one model-proposed tool call before execution.

    A structured result is returned instead of raising. That lets the runtime
    convert bad model output into an Observation the model can react to.
    """
    if tool_name not in TOOL_REGISTRY:
        return {
            "ok": False,
            "error": {
                "code": "unknown_tool",
                "message": f"Unknown tool: {tool_name}",
            },
        }

    if not isinstance(arguments, dict):
        return {
            "ok": False,
            "error": {
                "code": "invalid_arguments",
                "message": "Tool arguments must be a JSON object.",
            },
        }

    rules = TOOL_ARGUMENT_RULES[tool_name]
    supplied = set(arguments)
    missing = sorted(rules["required"] - supplied)
    extra = sorted(supplied - rules["allowed"])

    if missing:
        return {
            "ok": False,
            "error": {
                "code": "missing_arguments",
                "message": f"Missing required arguments: {', '.join(missing)}",
                "details": {"missing": missing},
            },
        }

    if extra:
        return {
            "ok": False,
            "error": {
                "code": "unexpected_arguments",
                "message": f"Unexpected arguments: {', '.join(extra)}",
                "details": {"extra": extra},
            },
        }

    if tool_name in {"calculator", "flaky_calculator"}:
        if not isinstance(arguments["a"], Real) or isinstance(arguments["a"], bool):
            return _type_error("a", "number")
        if not isinstance(arguments["b"], Real) or isinstance(arguments["b"], bool):
            return _type_error("b", "number")
        if arguments["operation"] not in {"add", "multiply"}:
            return {
                "ok": False,
                "error": {
                    "code": "invalid_argument_value",
                    "message": "operation must be 'add' or 'multiply'.",
                    "details": {"argument": "operation", "value": arguments["operation"]},
                },
            }

    return {"ok": True}


def _type_error(argument: str, expected: str) -> dict:
    return {
        "ok": False,
        "error": {
            "code": "invalid_argument_type",
            "message": f"{argument} must be a {expected}.",
            "details": {"argument": argument, "expected": expected},
        },
    }
