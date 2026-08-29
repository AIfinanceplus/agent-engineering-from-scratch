"""R6 Tool pack: R3 source/research tools plus grounded domain synthesis."""

from r3_tooling import register_r3_tools
from r6_domain import synthesize_domain_brief
from tools import TOOL_REGISTRY, Tool


DOMAIN_SYNTHESIS_TOOL = Tool(
    name="synthesize_domain_brief",
    description=(
        "Translate an already-grounded research synthesis into an investment or policy "
        "decision brief without fetching new data or increasing confidence."
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
    function=synthesize_domain_brief,
    max_retries=0,
    risk="low",
)


def register_r6_tools() -> tuple[str, ...]:
    names = list(register_r3_tools())
    existing = TOOL_REGISTRY.get(DOMAIN_SYNTHESIS_TOOL.name)
    if existing is not None and existing != DOMAIN_SYNTHESIS_TOOL:
        raise ValueError("Tool name collision while loading R6 domain synthesis tool")
    TOOL_REGISTRY[DOMAIN_SYNTHESIS_TOOL.name] = DOMAIN_SYNTHESIS_TOOL
    names.append(DOMAIN_SYNTHESIS_TOOL.name)
    return tuple(names)
