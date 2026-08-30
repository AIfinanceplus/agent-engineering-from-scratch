"""R10 Tool pack: market context plus numerical target, decision, EV, and instrument-risk tools."""

from r10_instrument import compute_instrument_risk_ev
from r10_investment import (
    build_numerical_research_target,
    build_r10_investment_decision,
    compute_scenario_expected_value,
)
from r9_tooling import register_r9_tools
from tools import TOOL_REGISTRY, Tool


R10_TARGET_TOOL = Tool(
    name="build_r10_numerical_research_target",
    description=(
        "Build a transparent numerical 5Y inflation-compensation research target from grounded S1/F1 inputs. "
        "The target is a mechanical one-step persistence baseline, not a calibrated probability or security fair value."
    ),
    parameters={
        "type": "object",
        "properties": {
            "research_synthesis": {"type": "object"},
            "forecast_pack": {"type": "object"},
            "reference_date": {"type": "string"},
        },
        "required": ["research_synthesis", "forecast_pack", "reference_date"],
        "additionalProperties": False,
    },
    function=build_numerical_research_target,
    max_retries=0,
    risk="low",
)

R10_DECISION_TOOL = Tool(
    name="build_r10_investment_decision",
    description=(
        "Compare grounded Research View plus T1 numerical target with observed Market View, quantify only "
        "a truly comparable research-market gap, build a standardized payoff template, and gate EV/position."
    ),
    parameters={
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "research_synthesis": {"type": "object"},
            "domain_brief": {"type": "object"},
            "forecast_pack": {"type": "object"},
            "research_target": {"type": "object"},
            "market_snapshot": {"type": "object"},
            "reference_date": {"type": "string"},
        },
        "required": [
            "question",
            "research_synthesis",
            "domain_brief",
            "forecast_pack",
            "research_target",
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

R10_INSTRUMENT_RISK_TOOL = Tool(
    name="compute_r10_instrument_risk_ev",
    description=(
        "Translate I1 market-move scenarios into instrument P&L using explicit P&L-per-bp sensitivity, "
        "then compute conditional EV, worst-scenario loss, risk efficiency, and a non-execution position-review gate."
    ),
    parameters={
        "type": "object",
        "properties": {
            "investment_decision": {"type": "object"},
            "instrument_name": {"type": "string"},
            "position_direction": {"type": "string"},
            "sensitivity_per_bp": {"type": "number"},
            "sensitivity_source": {"type": "string"},
            "pnl_unit": {"type": "string"},
            "scenario_probabilities": {"type": "array"},
            "transaction_cost": {"type": "number"},
            "carry": {"type": "number"},
            "risk_budget": {"type": "number"},
            "loss_limit": {"type": "number"},
        },
        "required": [
            "investment_decision",
            "instrument_name",
            "position_direction",
            "sensitivity_per_bp",
            "sensitivity_source",
            "pnl_unit",
            "scenario_probabilities",
        ],
        "additionalProperties": False,
    },
    function=compute_instrument_risk_ev,
    max_retries=0,
    risk="low",
)


def register_r10_tools() -> tuple[str, ...]:
    names = list(register_r9_tools())
    for tool in (R10_TARGET_TOOL, R10_DECISION_TOOL, R10_EV_TOOL, R10_INSTRUMENT_RISK_TOOL):
        existing = TOOL_REGISTRY.get(tool.name)
        if existing is not None and existing != tool:
            raise ValueError(f"Tool name collision while loading R10 tool: {tool.name}")
        TOOL_REGISTRY[tool.name] = tool
        names.append(tool.name)
    return tuple(names)
