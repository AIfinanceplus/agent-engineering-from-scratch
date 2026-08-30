"""R10 Tool pack: R9 market context plus deterministic Investment decision / EV tools."""

from r10_investment import build_r10_investment_decision, compute_scenario_expected_value
from r9_tooling import register_r9_tools
from tools import TOOL_REGISTRY, Tool


R10_DECISION_TOOL = Tool(
    name="build_r10_investment_decision",
    description=(
        "Compare grounded Research View with observed Market View, create a pricing-gap hypothesis, "
        "and gate EV/position without fabricating probabilities or numerical mispricing."
    ),
    parameters={
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "research_synthesis": {"type": "object"},
            "domain_brief": {"type": "object"},
            "forecast_pack": {"type": "object"},
            "market_snapshot": {"type": "object"},
            "reference_date": {"type": "string"},
        },
        "required": [
            "question",
            "research_synthesis",
            "domain_brief",
            "forecast_pack",
            "market_snapshot",
            "reference_date",
        ],
        "additionalProperties": False,
    },
    function=build_r10_investment_decision,
    max_retries=0,
    risk="low",
)

R10_EV_TOOL = Tool(
    name="compute_r10_scenario_ev",
    description=(
        "Compute expected value from an existing R10 Investment Decision and an explicit scenario book. "
        "Scenario probabilities and payoffs must be supplied; heuristic support scores are forbidden as probabilities."
    ),
    parameters={
        "type": "object",
        "properties": {
            "investment_decision": {"type": "object"},
            "scenarios": {"type": "array"},
            "transaction_cost": {"type": "number"},
            "payoff_unit": {"type": "string"},
        },
        "required": ["investment_decision", "scenarios"],
        "additionalProperties": False,
    },
    function=compute_scenario_expected_value,
    max_retries=0,
    risk="low",
)


def register_r10_tools() -> tuple[str, ...]:
    names = list(register_r9_tools())
    for tool in (R10_DECISION_TOOL, R10_EV_TOOL):
        existing = TOOL_REGISTRY.get(tool.name)
        if existing is not None and existing != tool:
            raise ValueError(f"Tool name collision while loading R10 tool: {tool.name}")
        TOOL_REGISTRY[tool.name] = tool
        names.append(tool.name)
    return tuple(names)
