"""R2 macro Tool Pack.

The core Tool Registry stays generic. R2 explicitly registers domain-specific
macro capabilities at application startup instead of permanently bloating the
Runtime's built-in tool list.
"""

from macro_multisource import fetch_eia_series, fetch_fred_series
from macro_multisource_analysis import synthesize_macro_signals
from tools import TOOL_REGISTRY, Tool


SOURCE_FETCH_PARAMETERS = {
    "type": "object",
    "properties": {
        "series_id": {"type": "string"},
        "label": {"type": "string"},
        "unit": {"type": "string"},
        "mode": {"type": "string", "enum": ["fixture", "live"]},
    },
    "required": ["series_id", "label", "unit", "mode"],
    "additionalProperties": False,
}

MULTI_SOURCE_SYNTHESIS_PARAMETERS = {
    "type": "object",
    "properties": {
        "headline": {"type": "object"},
        "core": {"type": "object"},
        "breakeven": {"type": "object"},
        "gasoline": {"type": "object"},
        "reference_date": {"type": "string"},
    },
    "required": ["headline", "core", "breakeven", "gasoline", "reference_date"],
    "additionalProperties": False,
}

FETCH_FRED_SERIES_TOOL = Tool(
    name="fetch_fred_series",
    description="Fetch and normalize one FRED series; live credentials remain Runtime-owned.",
    parameters=SOURCE_FETCH_PARAMETERS,
    function=fetch_fred_series,
    max_retries=2,
    risk="low",
)

FETCH_EIA_SERIES_TOOL = Tool(
    name="fetch_eia_series",
    description="Fetch and normalize one EIA energy series; live credentials remain Runtime-owned.",
    parameters=SOURCE_FETCH_PARAMETERS,
    function=fetch_eia_series,
    max_retries=2,
    risk="low",
)

SYNTHESIZE_MACRO_SIGNALS_TOOL = Tool(
    name="synthesize_macro_signals",
    description="Combine collected BLS, FRED, and EIA evidence into descriptive macro signals with freshness checks.",
    parameters=MULTI_SOURCE_SYNTHESIS_PARAMETERS,
    function=synthesize_macro_signals,
    max_retries=0,
    risk="low",
)

R2_TOOLS = (
    FETCH_FRED_SERIES_TOOL,
    FETCH_EIA_SERIES_TOOL,
    SYNTHESIZE_MACRO_SIGNALS_TOOL,
)


def register_r2_tools() -> tuple[str, ...]:
    for tool in R2_TOOLS:
        existing = TOOL_REGISTRY.get(tool.name)
        if existing is not None and existing != tool:
            raise ValueError(f"Tool name collision while loading R2 pack: {tool.name}")
        TOOL_REGISTRY[tool.name] = tool
    return tuple(tool.name for tool in R2_TOOLS)
