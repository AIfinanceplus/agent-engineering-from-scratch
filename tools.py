"""Tool objects: capability facts stay with the Tool.

R1 adds real-source macro capabilities while keeping Tool execution behind the
same Runtime validation, Policy, Retry, State, Trace, and Evidence boundaries.
"""

from dataclasses import dataclass
from numbers import Real
from typing import Callable

from evidence import lookup_synthetic_evidence, synthesize_two_evidence
from macro_analysis import compare_cpi_series
from macro_sources import fetch_bls_series


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
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "strict": True,
        }

    def trace_metadata(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "risk": self.risk,
            "max_retries": self.max_retries,
            "retryable_errors": [error.__name__ for error in self.retryable_errors],
        }

    def validate(self, arguments) -> dict:
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

            if expected_type == "object" and not isinstance(value, dict):
                return _error(
                    "invalid_argument_type",
                    f"{name} must be an object.",
                    {"argument": name, "expected": "object"},
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
    if operation == "add":
        return a + b
    if operation == "multiply":
        return a * b
    raise ValueError(f"Unsupported operation: {operation}")


class FlakyCalculator:
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
    return f"Simulated message sent to {recipient}: {message}"


def delete_record(record_id: str) -> str:
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
    "properties": {"record_id": {"type": "string"}},
    "required": ["record_id"],
    "additionalProperties": False,
}

EVIDENCE_LOOKUP_PARAMETERS = {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "enum": ["energy", "shelter"]},
    },
    "required": ["topic"],
    "additionalProperties": False,
}

SYNTHESIS_PARAMETERS = {
    "type": "object",
    "properties": {
        "evidence_a": {"type": "object"},
        "evidence_b": {"type": "object"},
    },
    "required": ["evidence_a", "evidence_b"],
    "additionalProperties": False,
}

BLS_FETCH_PARAMETERS = {
    "type": "object",
    "properties": {
        "series_id": {"type": "string"},
        "label": {"type": "string"},
        "mode": {"type": "string", "enum": ["fixture", "live"]},
    },
    "required": ["series_id", "label", "mode"],
    "additionalProperties": False,
}

CPI_COMPARE_PARAMETERS = {
    "type": "object",
    "properties": {
        "headline": {"type": "object"},
        "core": {"type": "object"},
    },
    "required": ["headline", "core"],
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

EVIDENCE_LOOKUP_TOOL = Tool(
    name="lookup_evidence",
    description="Retrieve one synthetic teaching evidence record with provenance.",
    parameters=EVIDENCE_LOOKUP_PARAMETERS,
    function=lookup_synthetic_evidence,
    max_retries=0,
    risk="low",
)

SYNTHESIZE_EVIDENCE_TOOL = Tool(
    name="synthesize_evidence",
    description="Synthesize two collected evidence records while preserving citation IDs.",
    parameters=SYNTHESIS_PARAMETERS,
    function=synthesize_two_evidence,
    max_retries=0,
    risk="low",
)

FETCH_BLS_SERIES_TOOL = Tool(
    name="fetch_bls_series",
    description="Fetch and normalize one official BLS time series or a deterministic replay fixture.",
    parameters=BLS_FETCH_PARAMETERS,
    function=fetch_bls_series,
    max_retries=2,
    risk="low",
)

COMPARE_CPI_SERIES_TOOL = Tool(
    name="compare_cpi_series",
    description="Compute latest headline and core CPI year-over-year rates from collected BLS evidence.",
    parameters=CPI_COMPARE_PARAMETERS,
    function=compare_cpi_series,
    max_retries=0,
    risk="low",
)


TOOL_REGISTRY: dict[str, Tool] = {
    tool.name: tool
    for tool in (
        CALCULATOR_TOOL,
        FLAKY_CALCULATOR_TOOL,
        SEND_MESSAGE_TOOL,
        DELETE_RECORD_TOOL,
        EVIDENCE_LOOKUP_TOOL,
        SYNTHESIZE_EVIDENCE_TOOL,
        FETCH_BLS_SERIES_TOOL,
        COMPARE_CPI_SERIES_TOOL,
    )
}


def resolve_tool(tool_name: str) -> Tool | None:
    return TOOL_REGISTRY.get(tool_name)


def model_tool_schemas() -> list[dict]:
    return [tool.to_model_schema() for tool in TOOL_REGISTRY.values()]


def validate_tool_arguments(tool_name: str, arguments) -> dict:
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
