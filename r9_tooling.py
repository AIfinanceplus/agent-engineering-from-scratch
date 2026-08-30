"""R9 Tool pack: R8 decision tools plus a deterministic market-pricing snapshot."""

from r8_tooling import register_r8_tools
from r9_market import build_market_pricing_snapshot
from tools import TOOL_REGISTRY, Tool


MARKET_SNAPSHOT_TOOL = Tool(
    name="build_market_pricing_snapshot",
    description=(
        "Build an observed U.S. market-pricing snapshot from fixed grounded FRED Evidence. "
        "This tool does not infer the Fed path, compute mispricing/EV, or recommend a position."
    ),
    parameters={
        "type": "object",
        "properties": {
            "policy_rate": {"type": "object"},
            "treasury_2y": {"type": "object"},
            "treasury_10y": {"type": "object"},
            "real_yield_10y": {"type": "object"},
            "breakeven_10y": {"type": "object"},
            "reference_date": {"type": "string"},
        },
        "required": [
            "policy_rate",
            "treasury_2y",
            "treasury_10y",
            "real_yield_10y",
            "breakeven_10y",
            "reference_date",
        ],
        "additionalProperties": False,
    },
    function=build_market_pricing_snapshot,
    max_retries=0,
    risk="low",
)


def register_r9_tools() -> tuple[str, ...]:
    names = list(register_r8_tools())
    existing = TOOL_REGISTRY.get(MARKET_SNAPSHOT_TOOL.name)
    if existing is not None and existing != MARKET_SNAPSHOT_TOOL:
        raise ValueError("Tool name collision while loading R9 market-pricing tool")
    TOOL_REGISTRY[MARKET_SNAPSHOT_TOOL.name] = MARKET_SNAPSHOT_TOOL
    names.append(MARKET_SNAPSHOT_TOOL.name)
    return tuple(names)
