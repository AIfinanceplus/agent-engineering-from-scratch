"""R11 Tool pack: accepted R10 tools plus constrained post-research position sizing."""

from r10_tooling import register_r10_tools
from r11_portfolio import compute_position_size
from tools import TOOL_REGISTRY, Tool


R11_POSITION_SIZE_TOOL = Tool(
    name="compute_r11_position_size",
    description=(
        "Compute the maximum admissible reference-position scale for an R10 I2 candidate under explicit "
        "trade risk, remaining portfolio risk, capital allocation, and implementation constraints. "
        "This is constraint intersection, not Kelly sizing or portfolio optimization, and it never executes a trade."
    ),
    parameters={
        "type": "object",
        "properties": {
            "instrument_risk_ev": {"type": "object"},
            "portfolio_value": {"type": "number"},
            "portfolio_value_unit": {"type": "string"},
            "portfolio_risk_budget": {"type": "number"},
            "portfolio_current_risk_used": {"type": "number"},
            "max_position_nav_fraction": {"type": "number"},
            "capital_required_per_reference_position": {"type": "number"},
            "capital_source": {"type": "string"},
            "max_reference_scale": {"type": ["number", "null"]},
        },
        "required": [
            "instrument_risk_ev",
            "portfolio_value",
            "portfolio_value_unit",
            "portfolio_risk_budget",
            "portfolio_current_risk_used",
            "max_position_nav_fraction",
            "capital_required_per_reference_position",
            "capital_source",
        ],
        "additionalProperties": False,
    },
    function=compute_position_size,
    max_retries=0,
    risk="low",
)


def register_r11_tools() -> tuple[str, ...]:
    names = list(register_r10_tools())
    existing = TOOL_REGISTRY.get(R11_POSITION_SIZE_TOOL.name)
    if existing is not None and existing != R11_POSITION_SIZE_TOOL:
        raise ValueError(f"Tool name collision while loading R11 tool: {R11_POSITION_SIZE_TOOL.name}")
    TOOL_REGISTRY[R11_POSITION_SIZE_TOOL.name] = R11_POSITION_SIZE_TOOL
    names.append(R11_POSITION_SIZE_TOOL.name)
    return tuple(names)
