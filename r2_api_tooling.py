"""Tool pack for the active API-only R2 application."""

from api_sources_native import fetch_bls_api_series, fetch_eia_api_series, fetch_fred_api_series
from macro_multisource_analysis import synthesize_macro_signals
from tools import TOOL_REGISTRY, Tool


BLS_PARAMS = {
    "type": "object",
    "properties": {"series_id": {"type": "string"}, "label": {"type": "string"}},
    "required": ["series_id", "label"],
    "additionalProperties": False,
}

POINT_SOURCE_PARAMS = {
    "type": "object",
    "properties": {
        "series_id": {"type": "string"},
        "label": {"type": "string"},
        "unit": {"type": "string"},
    },
    "required": ["series_id", "label", "unit"],
    "additionalProperties": False,
}

SYNTHESIS_PARAMS = {
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

API_TOOLS = (
    Tool(
        name="fetch_bls_api_series",
        description="Fetch one BLS series from the public API using native OS TLS trust.",
        parameters=BLS_PARAMS,
        function=fetch_bls_api_series,
        max_retries=2,
        risk="low",
    ),
    Tool(
        name="fetch_fred_api_series",
        description="Fetch recent FRED observations using Runtime-owned FRED_API_KEY and native OS TLS trust.",
        parameters=POINT_SOURCE_PARAMS,
        function=fetch_fred_api_series,
        max_retries=2,
        risk="low",
    ),
    Tool(
        name="fetch_eia_api_series",
        description="Fetch weekly EIA gasoline observations using Runtime-owned EIA_API_KEY and native OS TLS trust.",
        parameters=POINT_SOURCE_PARAMS,
        function=fetch_eia_api_series,
        max_retries=2,
        risk="low",
    ),
    Tool(
        name="synthesize_macro_signals",
        description="Synthesize collected BLS, FRED, and EIA evidence with freshness checks.",
        parameters=SYNTHESIS_PARAMS,
        function=synthesize_macro_signals,
        max_retries=0,
        risk="low",
    ),
)


def register_api_tools() -> tuple[str, ...]:
    for tool in API_TOOLS:
        existing = TOOL_REGISTRY.get(tool.name)
        if existing is not None and existing != tool:
            raise ValueError(f"Tool name collision while loading API pack: {tool.name}")
        TOOL_REGISTRY[tool.name] = tool
    return tuple(tool.name for tool in API_TOOLS)
