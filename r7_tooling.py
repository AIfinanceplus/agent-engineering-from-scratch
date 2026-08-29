"""R7 Tool pack: R6 research/domain tools plus falsifiable forecast creation."""

from r6_tooling import register_r6_tools
from r7_forecast import create_forecast_pack
from tools import TOOL_REGISTRY, Tool


CREATE_FORECAST_PACK_TOOL = Tool(
    name="create_forecast_pack",
    description=(
        "Create falsifiable directional forecast contracts and a scenario tracker from "
        "already-grounded S1/D1 artifacts without fetching new data."
    ),
    parameters={
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "domain": {"type": "string", "enum": ["investment", "policy"]},
            "research_synthesis": {"type": "object"},
            "domain_brief": {"type": "object"},
            "reference_date": {"type": "string"},
        },
        "required": [
            "question",
            "domain",
            "research_synthesis",
            "domain_brief",
            "reference_date",
        ],
        "additionalProperties": False,
    },
    function=create_forecast_pack,
    max_retries=0,
    risk="low",
)


def register_r7_tools() -> tuple[str, ...]:
    names = list(register_r6_tools())
    existing = TOOL_REGISTRY.get(CREATE_FORECAST_PACK_TOOL.name)
    if existing is not None and existing != CREATE_FORECAST_PACK_TOOL:
        raise ValueError("Tool name collision while loading R7 forecast tool")
    TOOL_REGISTRY[CREATE_FORECAST_PACK_TOOL.name] = CREATE_FORECAST_PACK_TOOL
    names.append(CREATE_FORECAST_PACK_TOOL.name)
    return tuple(names)
