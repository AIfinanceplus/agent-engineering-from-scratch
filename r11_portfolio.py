"""R11 Step 1: constrained position sizing from an accepted R10 I2 artifact.

R11 remains post-research and post-instrument-analysis. It does NOT alter S1, T1,
I1, I2, Evidence, or forecasts. It answers a narrower question:

    Given an already-reviewed candidate trade, what is the maximum admissible
    reference-position scale under explicit trade, portfolio, capital, and
    implementation constraints?

The engine deliberately does NOT claim optimality. It is a constraint-intersection
calculator, not Kelly sizing, mean-variance optimization, VaR, or utility
maximization.

Step 1 uses conservative additive risk-budget accounting:

    remaining_portfolio_risk = portfolio_risk_budget - current_risk_used
    max_scale = min(
        I2 risk_budget / reference_worst_loss,
        I2 loss_limit / reference_worst_loss,
        remaining_portfolio_risk / reference_worst_loss,
        max_position_capital / reference_capital_required,
        optional implementation scale cap,
    )

All P&L/risk/capital values must use the same explicit unit. Correlation,
diversification credit, nonlinear margin, liquidity impact, and cross-position
netting are intentionally NOT modeled in this step.
"""

from __future__ import annotations

from math import isclose, isfinite


def compute_position_size(
    instrument_risk_ev: dict,
    portfolio_value: float,
    portfolio_value_unit: str,
    portfolio_risk_budget: float,
    portfolio_current_risk_used: float,
    max_position_nav_fraction: float,
    capital_required_per_reference_position: float,
    capital_source: str,
    *,
    max_reference_scale: float | None = None,
) -> dict:
    """Compute the maximum admissible linear scale for an R10 I2 candidate.

    `reference_position` means the position size implicit in the I2 sensitivity.
    R11 scales the complete I2 scenario P&L linearly. That includes the I2 carry
    and transaction-cost assumptions; this is an explicit teaching approximation,
    not a claim that real-world costs/margin scale perfectly linearly.
    """
    _validate_i2(instrument_risk_ev)

    portfolio_value = _positive_number(portfolio_value, "portfolio_value")
    unit = _required_text(portfolio_value_unit, "portfolio_value_unit")
    portfolio_risk_budget = _positive_number(portfolio_risk_budget, "portfolio_risk_budget")
    current_risk = _non_negative_number(portfolio_current_risk_used, "portfolio_current_risk_used")
    nav_fraction = _fraction(max_position_nav_fraction, "max_position_nav_fraction")
    capital_per_reference = _positive_number(
        capital_required_per_reference_position,
        "capital_required_per_reference_position",
    )
    capital_source = _required_text(capital_source, "capital_source")
    implementation_cap = _optional_positive_number(max_reference_scale, "max_reference_scale")

    instrument = instrument_risk_ev.get("instrument") or {}
    pnl_unit = _required_text(instrument.get("pnl_unit"), "I2 instrument pnl_unit")
    if unit != pnl_unit:
        raise ValueError(
            "portfolio_value_unit must match the I2 P&L unit so risk/capital constraints are comparable"
        )
    if "support" in capital_source.lower():
        raise ValueError("heuristic support score cannot be used as a capital or sizing source")

    reference_ev = _positive_number(
        instrument_risk_ev.get("net_expected_value"),
        "I2 net_expected_value",
    )
    reference_worst_loss = _positive_number(
        instrument_risk_ev.get("worst_scenario_loss"),
        "I2 worst_scenario_loss",
    )
    trade_risk_budget = _positive_number(
        instrument_risk_ev.get("risk_budget"),
        "I2 risk_budget",
    )
    trade_loss_limit = _positive_number(
        instrument_risk_ev.get("loss_limit"),
        "I2 loss_limit",
    )

    remaining_portfolio_risk = max(0.0, portfolio_risk_budget - current_risk)
    max_position_capital = portfolio_value * nav_fraction

    constraints = {
        "trade_risk_budget": trade_risk_budget / reference_worst_loss,
        "trade_loss_limit": trade_loss_limit / reference_worst_loss,
        "portfolio_remaining_risk": remaining_portfolio_risk / reference_worst_loss,
        "capital_allocation": max_position_capital / capital_per_reference,
    }
    if implementation_cap is not None:
        constraints["implementation_scale_cap"] = implementation_cap

    if remaining_portfolio_risk <= 0:
        return _zero_size_artifact(
            instrument_risk_ev,
            unit=unit,
            portfolio_value=portfolio_value,
            portfolio_risk_budget=portfolio_risk_budget,
            current_risk=current_risk,
            nav_fraction=nav_fraction,
            capital_per_reference=capital_per_reference,
            max_position_capital=max_position_capital,
            remaining_portfolio_risk=remaining_portfolio_risk,
            constraints=constraints,
            capital_source=capital_source,
            status="NO_REMAINING_PORTFOLIO_RISK_BUDGET",
            reason="Current portfolio risk usage leaves no remaining additive risk budget.",
        )

    raw_scale = min(constraints.values())
    if not isfinite(raw_scale) or raw_scale <= 0:
        return _zero_size_artifact(
            instrument_risk_ev,
            unit=unit,
            portfolio_value=portfolio_value,
            portfolio_risk_budget=portfolio_risk_budget,
            current_risk=current_risk,
            nav_fraction=nav_fraction,
            capital_per_reference=capital_per_reference,
            max_position_capital=max_position_capital,
            remaining_portfolio_risk=remaining_portfolio_risk,
            constraints=constraints,
            capital_source=capital_source,
            status="NO_ADMISSIBLE_POSITION_SCALE",
            reason="At least one explicit sizing constraint leaves no positive admissible scale.",
        )

    binding = sorted(
        name
        for name, scale in constraints.items()
        if isclose(scale, raw_scale, rel_tol=0.0, abs_tol=1e-9)
    )
    scale = round(raw_scale, 8)

    scaled_ev = reference_ev * raw_scale
    scaled_worst_loss = reference_worst_loss * raw_scale
    scaled_capital = capital_per_reference * raw_scale
    post_trade_risk_used = current_risk + scaled_worst_loss
    risk_utilization = post_trade_risk_used / portfolio_risk_budget
    allocation_fraction = scaled_capital / portfolio_value
    reference_signed_sensitivity = _number(
        instrument.get("signed_pnl_per_bp"),
        "I2 signed_pnl_per_bp",
    )
    scaled_signed_sensitivity = reference_signed_sensitivity * raw_scale
    scenario_ev_on_allocated_capital = scaled_ev / scaled_capital
    risk_efficiency = scaled_ev / scaled_worst_loss

    scaled_scenarios = []
    for row in instrument_risk_ev.get("scenarios") or []:
        scaled_scenarios.append(
            {
                "name": row.get("name"),
                "probability": row.get("probability"),
                "market_move_bp": row.get("market_move_bp"),
                "reference_net_instrument_pnl": row.get("net_instrument_pnl"),
                "scaled_net_instrument_pnl": round(
                    _number(row.get("net_instrument_pnl"), f"{row.get('name')} net P&L") * raw_scale,
                    6,
                ),
            }
        )

    return {
        "artifact_type": "r11_position_sizing",
        "status": "SIZE_AVAILABLE_FOR_REVIEW_NOT_EXECUTION",
        "position": "NONE_AUTOMATICALLY",
        "reference_artifact": "I2",
        "instrument": {
            "name": instrument.get("name"),
            "position_direction": instrument.get("position_direction"),
            "pnl_unit": pnl_unit,
            "reference_signed_pnl_per_bp": reference_signed_sensitivity,
            "scaled_signed_pnl_per_bp": round(scaled_signed_sensitivity, 6),
        },
        "sizing": {
            "method": "max_admissible_scale_constraint_intersection",
            "optimality_claim": "NONE",
            "reference_position_scale": 1.0,
            "max_admissible_scale": scale,
            "binding_constraints": binding,
            "constraint_scales": {name: round(value, 8) for name, value in constraints.items()},
        },
        "portfolio": {
            "portfolio_value": portfolio_value,
            "portfolio_value_unit": unit,
            "portfolio_risk_budget": portfolio_risk_budget,
            "portfolio_current_risk_used": current_risk,
            "portfolio_remaining_risk_before_trade": round(remaining_portfolio_risk, 6),
            "post_trade_risk_used": round(post_trade_risk_used, 6),
            "post_trade_risk_utilization": round(risk_utilization, 8),
            "max_position_nav_fraction": nav_fraction,
            "max_position_capital": round(max_position_capital, 6),
            "capital_required_per_reference_position": capital_per_reference,
            "capital_source": capital_source,
            "scaled_capital_required": round(scaled_capital, 6),
            "scaled_capital_fraction_of_nav": round(allocation_fraction, 8),
        },
        "economics": {
            "reference_net_ev": reference_ev,
            "reference_worst_scenario_loss": reference_worst_loss,
            "scaled_net_ev": round(scaled_ev, 6),
            "scaled_worst_scenario_loss": round(scaled_worst_loss, 6),
            "risk_efficiency_ratio": round(risk_efficiency, 8),
            "risk_efficiency_type": "net_ev_divided_by_worst_scenario_loss_not_sharpe",
            "scenario_ev_on_allocated_capital": round(scenario_ev_on_allocated_capital, 8),
            "scenario_ev_on_allocated_capital_type": "conditional_scenario_ev_not_annualized_return",
        },
        "scaled_scenarios": scaled_scenarios,
        "position_review_gate": {
            "status": "SIZE_AVAILABLE_FOR_REVIEW_NOT_EXECUTION",
            "eligible_for_size_review": True,
            "execution_authorized": False,
            "reason": (
                "A positive scale fits the explicit trade-risk, portfolio-risk, capital-allocation, "
                "and implementation constraints. This is a review ceiling, not an optimal or executable order."
            ),
        },
        "assumptions": {
            "portfolio_risk_accounting": "conservative_additive_worst_scenario_budget",
            "linear_position_scaling": True,
            "i2_carry_and_cost_scaled_linearly_with_reference_position": True,
            "correlation_modeled": False,
            "diversification_credit_taken": False,
            "cross_position_netting_modeled": False,
            "nonlinear_margin_modeled": False,
            "liquidity_impact_modeled": False,
        },
        "guardrails": {
            "kelly_or_optimal_size_claimed": False,
            "var_claimed": False,
            "sharpe_claimed": False,
            "support_score_used_as_sizing_input": False,
            "automatic_trade_execution": False,
            "research_artifacts_mutated": False,
        },
    }


def _validate_i2(artifact: dict) -> None:
    if not isinstance(artifact, dict) or artifact.get("artifact_type") != "r10_instrument_risk_ev":
        raise ValueError("instrument_risk_ev must be an R10 I2 instrument-risk artifact")
    gate = artifact.get("position_review_gate") or {}
    if gate.get("status") != "ELIGIBLE_FOR_POSITION_REVIEW_NOT_EXECUTION" or not gate.get("eligible_for_review"):
        raise ValueError("position sizing requires an I2 candidate eligible for position review")
    if artifact.get("position") != "NONE_AUTOMATICALLY":
        raise ValueError("I2 artifact must preserve the no-automatic-position contract")


def _zero_size_artifact(
    artifact: dict,
    *,
    unit: str,
    portfolio_value: float,
    portfolio_risk_budget: float,
    current_risk: float,
    nav_fraction: float,
    capital_per_reference: float,
    max_position_capital: float,
    remaining_portfolio_risk: float,
    constraints: dict,
    capital_source: str,
    status: str,
    reason: str,
) -> dict:
    instrument = artifact.get("instrument") or {}
    return {
        "artifact_type": "r11_position_sizing",
        "status": status,
        "position": "NONE_AUTOMATICALLY",
        "reference_artifact": "I2",
        "instrument": {
            "name": instrument.get("name"),
            "position_direction": instrument.get("position_direction"),
            "pnl_unit": unit,
            "reference_signed_pnl_per_bp": instrument.get("signed_pnl_per_bp"),
            "scaled_signed_pnl_per_bp": 0.0,
        },
        "sizing": {
            "method": "max_admissible_scale_constraint_intersection",
            "optimality_claim": "NONE",
            "reference_position_scale": 1.0,
            "max_admissible_scale": 0.0,
            "binding_constraints": [],
            "constraint_scales": {name: round(value, 8) for name, value in constraints.items()},
        },
        "portfolio": {
            "portfolio_value": portfolio_value,
            "portfolio_value_unit": unit,
            "portfolio_risk_budget": portfolio_risk_budget,
            "portfolio_current_risk_used": current_risk,
            "portfolio_remaining_risk_before_trade": round(remaining_portfolio_risk, 6),
            "post_trade_risk_used": current_risk,
            "post_trade_risk_utilization": round(current_risk / portfolio_risk_budget, 8),
            "max_position_nav_fraction": nav_fraction,
            "max_position_capital": round(max_position_capital, 6),
            "capital_required_per_reference_position": capital_per_reference,
            "capital_source": capital_source,
            "scaled_capital_required": 0.0,
            "scaled_capital_fraction_of_nav": 0.0,
        },
        "economics": {
            "scaled_net_ev": 0.0,
            "scaled_worst_scenario_loss": 0.0,
            "risk_efficiency_ratio": None,
            "risk_efficiency_type": "not_computed_no_position_scale",
        },
        "scaled_scenarios": [],
        "position_review_gate": {
            "status": status,
            "eligible_for_size_review": False,
            "execution_authorized": False,
            "reason": reason,
        },
        "assumptions": {
            "portfolio_risk_accounting": "conservative_additive_worst_scenario_budget",
            "correlation_modeled": False,
            "diversification_credit_taken": False,
        },
        "guardrails": {
            "kelly_or_optimal_size_claimed": False,
            "var_claimed": False,
            "sharpe_claimed": False,
            "automatic_trade_execution": False,
            "research_artifacts_mutated": False,
        },
    }


def _required_text(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value.strip()


def _number(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    return float(value)


def _positive_number(value, label: str) -> float:
    number = _number(value, label)
    if number <= 0:
        raise ValueError(f"{label} must be > 0")
    return number


def _non_negative_number(value, label: str) -> float:
    number = _number(value, label)
    if number < 0:
        raise ValueError(f"{label} must be >= 0")
    return number


def _optional_positive_number(value, label: str) -> float | None:
    if value is None:
        return None
    return _positive_number(value, label)


def _fraction(value, label: str) -> float:
    number = _number(value, label)
    if not 0 < number <= 1:
        raise ValueError(f"{label} must be in (0, 1]")
    return number
