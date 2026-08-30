"""R10 Step 3: explicit instrument sensitivity -> scenario P&L -> risk EV.

This module is intentionally post-research. It consumes an already-completed I1
Investment Decision plus explicit instrument/risk inputs. It never changes S1,
Evidence, T1, M6, or the research-market gap.

The bridge is linear by contract:

    scenario instrument P&L = market_move_bp * signed_pnl_per_bp
    scenario net P&L        = instrument P&L + carry - transaction_cost
    net EV                  = sum(probability * scenario net P&L)
    risk efficiency ratio   = net EV / worst_scenario_loss

The ratio is a simple scenario risk-efficiency diagnostic. It is NOT a Sharpe
ratio, information ratio, VaR, or calibrated probability model.
"""

from __future__ import annotations

from math import isclose


VALID_DIRECTIONS = {"LONG": 1.0, "SHORT": -1.0}


def compute_instrument_risk_ev(
    investment_decision: dict,
    instrument_name: str,
    position_direction: str,
    sensitivity_per_bp: float,
    sensitivity_source: str,
    pnl_unit: str,
    scenario_probabilities: list[dict],
    *,
    transaction_cost: float = 0.0,
    carry: float = 0.0,
    risk_budget: float | None = None,
    loss_limit: float | None = None,
) -> dict:
    """Translate the I1 market-move scenario template into instrument P&L.

    Sensitivity is deliberately supplied explicitly. A future instrument adapter
    may provide it, but R10 does not invent DV01/duration/convexity for a named
    security. Probabilities are also explicit and may never come from heuristic
    research support scores.
    """
    _validate_decision(investment_decision)
    name = _required_text(instrument_name, "instrument_name")
    direction = _required_text(position_direction, "position_direction").upper()
    if direction not in VALID_DIRECTIONS:
        raise ValueError("position_direction must be LONG or SHORT")
    sensitivity = _positive_number(sensitivity_per_bp, "sensitivity_per_bp")
    sensitivity_source = _required_text(sensitivity_source, "sensitivity_source")
    pnl_unit = _required_text(pnl_unit, "pnl_unit")
    transaction_cost = _non_negative_number(transaction_cost, "transaction_cost")
    carry = _number(carry, "carry")
    risk_budget_value = _optional_positive_number(risk_budget, "risk_budget")
    loss_limit_value = _optional_positive_number(loss_limit, "loss_limit")

    if "support" in sensitivity_source.lower():
        raise ValueError("heuristic support score cannot be used as instrument sensitivity")

    template = investment_decision.get("scenario_payoff_template") or {}
    if template.get("status") != "STANDARDIZED_MARKET_MOVE_PAYOFF_TEMPLATE_AVAILABLE":
        raise ValueError("instrument P&L requires an I1 numerical gap and market-move scenario template")
    template_rows = template.get("scenarios") or []
    if len(template_rows) < 2:
        raise ValueError("market-move scenario template must contain at least two scenarios")

    probability_map = _probability_map(scenario_probabilities)
    template_names = {str(row.get("name")) for row in template_rows}
    if set(probability_map) != template_names:
        raise ValueError("scenario probabilities must match the I1 scenario template exactly")

    total_probability = sum(row["probability"] for row in probability_map.values())
    if not isclose(total_probability, 1.0, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError(f"scenario probabilities must sum to 1.0; got {total_probability:.6f}")

    sign = VALID_DIRECTIONS[direction]
    signed_sensitivity = sign * sensitivity
    rows = []
    for source_row in template_rows:
        scenario_name = str(source_row.get("name"))
        move_bp = _number(source_row.get("market_move_bp"), f"{scenario_name}.market_move_bp")
        probability_row = probability_map[scenario_name]
        gross_pnl = move_bp * signed_sensitivity
        net_pnl = gross_pnl + carry - transaction_cost
        rows.append(
            {
                "name": scenario_name,
                "market_move_bp": round(move_bp, 6),
                "probability": probability_row["probability"],
                "probability_source": probability_row["probability_source"],
                "gross_instrument_pnl": round(gross_pnl, 6),
                "carry": round(carry, 6),
                "transaction_cost": round(transaction_cost, 6),
                "net_instrument_pnl": round(net_pnl, 6),
            }
        )

    gross_ev = sum(row["probability"] * row["gross_instrument_pnl"] for row in rows)
    net_ev = sum(row["probability"] * row["net_instrument_pnl"] for row in rows)
    worst_net = min(row["net_instrument_pnl"] for row in rows)
    best_net = max(row["net_instrument_pnl"] for row in rows)
    worst_loss = max(0.0, -worst_net)
    risk_efficiency = None if worst_loss == 0 else net_ev / worst_loss

    within_budget = None if risk_budget_value is None else worst_loss <= risk_budget_value
    within_limit = None if loss_limit_value is None else worst_loss <= loss_limit_value
    gate = _position_review_gate(
        net_ev=net_ev,
        worst_loss=worst_loss,
        risk_budget=risk_budget_value,
        within_budget=within_budget,
        loss_limit=loss_limit_value,
        within_limit=within_limit,
    )

    return {
        "artifact_type": "r10_instrument_risk_ev",
        "status": gate["status"],
        "instrument": {
            "name": name,
            "position_direction": direction,
            "sensitivity_per_bp": sensitivity,
            "signed_pnl_per_bp": round(signed_sensitivity, 6),
            "sensitivity_source": sensitivity_source,
            "pnl_unit": pnl_unit,
            "sensitivity_contract": "linear_local_sensitivity_user_or_adapter_supplied",
        },
        "pricing_gap": {
            "dimension": (investment_decision.get("mispricing") or {}).get("dimension"),
            "gap_magnitude_bp": (investment_decision.get("mispricing") or {}).get("gap_magnitude_bp"),
            "source_artifact": "I1",
        },
        "scenarios": rows,
        "probability_sum": round(total_probability, 8),
        "gross_expected_value": round(gross_ev, 6),
        "net_expected_value": round(net_ev, 6),
        "worst_scenario_net_pnl": round(worst_net, 6),
        "best_scenario_net_pnl": round(best_net, 6),
        "worst_scenario_loss": round(worst_loss, 6),
        "risk_efficiency_ratio": None if risk_efficiency is None else round(risk_efficiency, 6),
        "risk_efficiency_type": "net_ev_divided_by_worst_scenario_loss_not_sharpe",
        "risk_budget": risk_budget_value,
        "loss_limit": loss_limit_value,
        "within_risk_budget": within_budget,
        "within_loss_limit": within_limit,
        "position_review_gate": gate,
        "position": "NONE_AUTOMATICALLY",
        "interpretation": (
            "Instrument P&L is a linear local-sensitivity translation of the I1 market-move scenarios. "
            "The resulting EV and risk-efficiency ratio are conditional on explicit sensitivity, probabilities, "
            "carry, costs, and scenario design; they do not authorize execution."
        ),
        "guardrails": {
            "instrument_sensitivity_explicit": True,
            "support_score_used_as_probability": False,
            "support_score_used_as_sensitivity": False,
            "linear_sensitivity_called_exact_full_repricing": False,
            "risk_efficiency_called_sharpe": False,
            "automatic_trade_execution": False,
            "research_artifacts_mutated": False,
        },
    }


def _validate_decision(decision: dict) -> None:
    if not isinstance(decision, dict) or decision.get("artifact_type") != "r10_investment_decision":
        raise ValueError("investment_decision must be an R10 investment decision artifact")
    mispricing = decision.get("mispricing") or {}
    if mispricing.get("status") != "NUMERIC_GAP_AVAILABLE":
        raise ValueError("instrument bridge requires NUMERIC_GAP_AVAILABLE")
    if not isinstance(mispricing.get("gap_magnitude_bp"), (int, float)):
        raise ValueError("instrument bridge requires a numeric gap_magnitude_bp")


def _probability_map(rows: list[dict]) -> dict[str, dict]:
    if not isinstance(rows, list) or len(rows) < 2:
        raise ValueError("scenario_probabilities must contain at least two rows")
    result: dict[str, dict] = {}
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"scenario probability row {index} must be an object")
        name = _required_text(row.get("name"), f"scenario {index} name")
        if name in result:
            raise ValueError(f"duplicate scenario probability name: {name}")
        probability = _number(row.get("probability"), f"{name} probability")
        if not 0 <= probability <= 1:
            raise ValueError(f"{name} probability must be between 0 and 1")
        source = _required_text(row.get("probability_source"), f"{name} probability_source")
        if "support" in source.lower():
            raise ValueError("heuristic support score cannot be used as scenario probability")
        result[name] = {
            "probability": probability,
            "probability_source": source,
        }
    return result


def _position_review_gate(
    *,
    net_ev: float,
    worst_loss: float,
    risk_budget: float | None,
    within_budget: bool | None,
    loss_limit: float | None,
    within_limit: bool | None,
) -> dict:
    if net_ev <= 0:
        return {
            "status": "REJECT_NON_POSITIVE_NET_EV",
            "eligible_for_review": False,
            "reason": "Net expected value is not positive under the supplied assumptions.",
        }
    if worst_loss <= 0:
        return {
            "status": "REVIEW_SCENARIO_BOOK_HAS_NO_LOSS_CASE",
            "eligible_for_review": False,
            "reason": "A position review requires at least one adverse-loss scenario.",
        }
    if risk_budget is None or loss_limit is None:
        return {
            "status": "REVIEW_MISSING_RISK_LIMITS",
            "eligible_for_review": False,
            "reason": "Positive EV is insufficient; risk_budget and loss_limit are both required.",
        }
    if not within_budget or not within_limit:
        return {
            "status": "REJECT_RISK_LIMIT",
            "eligible_for_review": False,
            "reason": "Worst scenario loss exceeds the supplied risk budget or loss limit.",
        }
    return {
        "status": "ELIGIBLE_FOR_POSITION_REVIEW_NOT_EXECUTION",
        "eligible_for_review": True,
        "reason": "Positive net EV and supplied scenario loss are within explicit risk limits; execution is still not authorized.",
    }


def _required_text(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value.strip()


def _number(value, label: str) -> float:
    if not isinstance(value, (int, float)):
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
