"""R8 Tool pack: R7 research/forecast tools plus professional D1 decision lens."""

from r7_tooling import register_r7_tools
from r8_decision import synthesize_professional_decision_brief
from tools import TOOL_REGISTRY, Tool


PROFESSIONAL_DECISION_TOOL = Tool(
    name="synthesize_professional_decision_brief",
    description=(
        "Translate an already-grounded S1 research synthesis into a professional Investment "
        "or Policy decision framework without fetching new data or inventing pricing/causal evidence."
    ),
    parameters={
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "domain": {"type": "string", "enum": ["investment", "policy"]},
            "research_synthesis": {"type": "object"},
            "reference_date": {"type": "string"},
        },
        "required": ["question", "domain", "research_synthesis", "reference_date"],
        "additionalProperties": False,
    },
    function=synthesize_professional_decision_brief,
    max_retries=0,
    risk="low",
)


def register_r8_tools() -> tuple[str, ...]:
    names = list(register_r7_tools())
    existing = TOOL_REGISTRY.get(PROFESSIONAL_DECISION_TOOL.name)
    if existing is not None and existing != PROFESSIONAL_DECISION_TOOL:
        raise ValueError("Tool name collision while loading R8 decision tool")
    TOOL_REGISTRY[PROFESSIONAL_DECISION_TOOL.name] = PROFESSIONAL_DECISION_TOOL
    names.append(PROFESSIONAL_DECISION_TOOL.name)
    return tuple(names)
