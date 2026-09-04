"""Minimal Tool pack for the first end-to-end rate strategy."""

from rate_sources import FredCurveHistorySource
from rate_strategy import simulate_one_curve_trade
from tools import TOOL_REGISTRY, Tool


def fetch_public_rate_history(start_date: str) -> dict:
    return FredCurveHistorySource().fetch(start_date)


RATE_HISTORY_TOOL = Tool(
    name="fetch_public_rate_history",
    description=(
        "Fetch credential-free DGS2 and DGS10 history through the FRED -> official "
        "U.S. Treasury -> disclosed snapshot source ladder."
    ),
    parameters={
        "type": "object",
        "properties": {"start_date": {"type": "string"}},
        "required": ["start_date"],
        "additionalProperties": False,
    },
    function=fetch_public_rate_history,
    max_retries=2,
    risk="low",
)


RATE_SIMULATION_TOOL = Tool(
    name="simulate_one_curve_trade",
    description=(
        "Apply the explicit 2s10s rolling-z rule and close exactly one historical "
        "paper trade using a transparent DV01 approximation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "history": {"type": "object"},
            "lookback_days": {"type": "number"},
            "entry_z": {"type": "number"},
            "holding_days": {"type": "number"},
            "dv01_usd_per_bp": {"type": "number"},
            "round_trip_cost_bps": {"type": "number"},
        },
        "required": [
            "history",
            "lookback_days",
            "entry_z",
            "holding_days",
            "dv01_usd_per_bp",
            "round_trip_cost_bps",
        ],
        "additionalProperties": False,
    },
    function=simulate_one_curve_trade,
    max_retries=0,
    risk="low",
)


def register_rate_tools() -> None:
    for tool in (RATE_HISTORY_TOOL, RATE_SIMULATION_TOOL):
        existing = TOOL_REGISTRY.get(tool.name)
        if existing is not None and existing != tool:
            raise RuntimeError(f"Tool Registry collision for {tool.name}")
        TOOL_REGISTRY[tool.name] = tool
