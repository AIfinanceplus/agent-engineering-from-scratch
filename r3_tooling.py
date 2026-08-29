"""Tool registration for the active R3 research workbench."""

from r2_api_tooling import register_api_tools
from r3_synthesis import synthesize_research_bundle
from tools import TOOL_REGISTRY, Tool


SYNTHESIZE_RESEARCH_BUNDLE_TOOL = Tool(
    name="synthesize_research_bundle",
    description="Synthesize a variable list of collected Evidence records for one research question.",
    parameters={
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "evidence_bundle": {
                "type": "array",
                "items": {"type": "object"},
            },
            "reference_date": {"type": "string"},
        },
        "required": ["question", "evidence_bundle", "reference_date"],
        "additionalProperties": False,
    },
    function=synthesize_research_bundle,
    max_retries=0,
    risk="low",
)


def register_r3_tools() -> tuple[str, ...]:
    names = list(register_api_tools())
    existing = TOOL_REGISTRY.get(SYNTHESIZE_RESEARCH_BUNDLE_TOOL.name)
    if existing is not None and existing != SYNTHESIZE_RESEARCH_BUNDLE_TOOL:
        raise ValueError("Tool name collision while loading R3 synthesis tool")
    TOOL_REGISTRY[SYNTHESIZE_RESEARCH_BUNDLE_TOOL.name] = SYNTHESIZE_RESEARCH_BUNDLE_TOOL
    names.append(SYNTHESIZE_RESEARCH_BUNDLE_TOOL.name)
    return tuple(names)
