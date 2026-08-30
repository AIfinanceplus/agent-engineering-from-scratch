"""R10 deterministic Investment intelligence: market view -> pricing gap -> EV contract.

R10 is intentionally downstream of the accepted research stack:

    Research Evidence -> S1 -> D1 -> F1
    Market Evidence   -> M6
                         \
                          -> I1 R10 Investment Decision

The module never treats R5 support scores as probabilities. A directional research
forecast may create a *pricing hypothesis*, but numerical mispricing requires a
numerical research target. Expected value is computed only from an explicit
scenario book whose probabilities and payoffs are supplied/calibrated elsewhere.
"""

from __future__ import annotations

from copy import deepcopy
from math import isclose


COMPARABLE_MARKET_EVIDENCE_ID = "FRED:T5YIE"


def build_r10_investment_decision(
    question: str,
    research_synthesis: dict,
    domain_brief: dict,
    forecast_pack: dict,
    market_snapshot: dict,
    reference_date: str,
) -> dict:
    _validate_upstream(research_synthesis, domain_brief, forecast_pack, market_snapshot)

    research_ids = list(research_synthesis.get("evidence_ids") or [])
    market_ids = list(market_snapshot.get("evidence_ids") or [])
    forecast = _find_comparable_forecast(forecast_pack)
    market_view = _build_market_implied_view(forecast, market_snapshot)
    research_view = _build_research_view(domain_brief, forecast)
    mispricing = _assess_mispricing(research_view, market_view)
    ev = _empty_ev_contract(mispricing)

    if mispricing["status"] == "NUMERIC_GAP_AVAILABLE":
        position_status = "NO_POSITION_EV_NOT_COMPUTED"
    elif mispricing["status"] == "DIRECTIONAL_GAP_ONLY":
        position_status = "NO_POSITION_GAP_NOT_QUANTIFIED"
    elif mispricing["status"] == "NO_DIRECTIONAL_GAP":
        position_status = "NO_POSITION_NO_EDGE"
    else:
        position_status = "NO_POSITION_INSUFFICIENT_COMPARABILITY"

    combined_ids = sorted(set(research_ids) | set(market_ids))
    return {
        "kind": "synthesis",
        "artifact_type": "r10_investment_decision",
        "question": question,
        "domain": "investment",
        "answer": (
            "R10 separates Research View from observable Market View, then tests whether a comparable "
            "pricing gap exists. Directional disagreement alone is not a numerical mispricing estimate, "
            "and no EV or position is produced without explicit scenario probabilities and payoffs."
        ),
        "value": 0.0,
        "unit": "decision_gate_not_return",
        "confidence": min(
            float(research_synthesis.get("confidence", 0.0)),
            float(domain_brief.get("confidence", 0.0)),
        ),
        "confidence_type": research_synthesis.get(
            "confidence_type", "heuristic_support_score_not_probability"
        ),
        "reference_date": reference_date,
        "evidence_ids": combined_ids,
        "research_evidence_ids": research_ids,
        "market_evidence_ids": market_ids,
        "research_view": research_view,
        "market_implied_view": market_view,
        "mispricing": mispricing,
        "expected_value": ev,
        "position_gate": {
            "status": position_status,
            "position": "NONE",
            "required_before_position": [
                "comparable Research View and Market View",
                "quantified gap or explicit scenario mapping",
                "scenario probabilities from an explicit source/assumption",
                "scenario payoffs including adverse outcomes",
                "transaction costs / carry / implementation assumptions",
                "risk budget and loss limit",
            ],
        },
        "guardrails": {
            "support_score_used_as_probability": False,
            "fed_futures_path_inferred_from_treasury_yield": False,
            "directional_gap_called_numeric_mispricing": False,
            "ev_computed_without_scenario_book": False,
            "position_recommended_without_ev_and_risk_budget": False,
            "upstream_research_evidence_mutated": False,
        },
    }


def compute_scenario_expected_value(
    investment_decision: dict,
    scenarios: list[dict],
    *,
    transaction_cost: float = 0.0,
    payoff_unit: str = "user_defined_payoff_unit",
) -> dict:
    """Compute scenario EV only from explicit probability/payoff inputs.

    `probability_source` must be declared for every scenario. The caller may use
    `user_assumption` or a separately calibrated model, but may not relabel the
    R5/R7 heuristic support score as a probability.
    """
    if not isinstance(investment_decision, dict) or investment_decision.get("artifact_type") != "r10_investment_decision":
        raise ValueError("investment_decision must be an R10 investment decision artifact")
    if not isinstance(scenarios, list) or len(scenarios) < 2:
        raise ValueError("scenario book must contain at least two scenarios")
    if not isinstance(transaction_cost, (int, float)) or transaction_cost < 0:
        raise ValueError("transaction_cost must be a non-negative number")
    if not isinstance(payoff_unit, str) or not payoff_unit.strip():
        raise ValueError("payoff_unit must be a non-empty string")

    normalized = []
    for index, row in enumerate(scenarios, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"scenario {index} must be an object")
        name = row.get("name") or f"scenario_{index}"
        probability = row.get("probability")
        payoff = row.get("payoff")
        source = row.get("probability_source")
        if not isinstance(probability, (int, float)) or not 0 <= float(probability) <= 1:
            raise ValueError(f"{name} probability must be between 0 and 1")
        if not isinstance(payoff, (int, float)):
            raise ValueError(f"{name} payoff must be numeric")
        if not isinstance(source, str) or not source.strip():
            raise ValueError(f"{name} probability_source is required")
        if "support" in source.lower():
            raise ValueError("heuristic support score cannot be used as scenario probability")
        normalized.append(
            {
                "name": str(name),
                "probability": float(probability),
                "payoff": float(payoff),
                "probability_source": source,
            }
        )

    total_probability = sum(row["probability"] for row in normalized)
    if not isclose(total_probability, 1.0, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError(f"scenario probabilities must sum to 1.0; got {total_probability:.6f}")

    gross_ev = sum(row["probability"] * row["payoff"] for row in normalized)
    net_ev = gross_ev - float(transaction_cost)
    downside = min(row["payoff"] for row in normalized)
    upside = max(row["payoff"] for row in normalized)

    if net_ev > 0:
        status = "POSITIVE_EV_UNDER_INPUT_ASSUMPTIONS"
    elif net_ev < 0:
        status = "NEGATIVE_EV_UNDER_INPUT_ASSUMPTIONS"
    else:
        status = "ZERO_EV_UNDER_INPUT_ASSUMPTIONS"

    return {
        "artifact_type": "r10_scenario_ev",
        "status": status,
        "payoff_unit": payoff_unit,
        "scenarios": normalized,
        "probability_sum": round(total_probability, 8),
        "gross_expected_value": round(gross_ev, 6),
        "transaction_cost": float(transaction_cost),
        "net_expected_value": round(net_ev, 6),
        "worst_scenario_payoff": downside,
        "best_scenario_payoff": upside,
        "position": "NONE_UNTIL_RISK_BUDGET_AND_IMPLEMENTATION",
        "interpretation": (
            "This EV is conditional on the supplied scenario probabilities/payoffs. "
            "Positive EV does not by itself authorize a position."
        ),
        "guardrails": {
            "probabilities_explicit": True,
            "probability_sum_valid": True,
            "support_score_used_as_probability": False,
            "automatic_position_from_positive_ev": False,
        },
    }


def _validate_upstream(research_synthesis, domain_brief, forecast_pack, market_snapshot) -> None:
    if not isinstance(research_synthesis, dict) or research_synthesis.get("kind") != "synthesis":
        raise ValueError("research_synthesis must be a grounded S1 synthesis")
    if not isinstance(domain_brief, dict) or domain_brief.get("domain") != "investment":
        raise ValueError("domain_brief must be an Investment D1 artifact")
    if not isinstance(forecast_pack, dict) or forecast_pack.get("artifact_type") != "forecast_pack":
        raise ValueError("forecast_pack must be an F1 forecast pack")
    if not isinstance(market_snapshot, dict) or market_snapshot.get("artifact_type") != "market_pricing_snapshot":
        raise ValueError("market_snapshot must be an R9 market-pricing snapshot")

    research_ids = list(research_synthesis.get("evidence_ids") or [])
    if list(domain_brief.get("evidence_ids") or []) != research_ids:
        raise ValueError("D1 must preserve the S1 research Evidence lineage")
    if list(forecast_pack.get("evidence_ids") or []) != research_ids:
        raise ValueError("F1 must preserve the S1 research Evidence lineage")


def _find_comparable_forecast(forecast_pack: dict) -> dict | None:
    for row in forecast_pack.get("forecasts") or []:
        if row.get("target_evidence_id") == COMPARABLE_MARKET_EVIDENCE_ID:
            return deepcopy(row)
    return None


def _build_research_view(domain_brief: dict, forecast: dict | None) -> dict:
    pressure = domain_brief.get("pressure_state")
    if forecast is None:
        comparable = {
            "status": "NO_COMPARABLE_MARKET_FORECAST",
            "target_evidence_id": COMPARABLE_MARKET_EVIDENCE_ID,
        }
    else:
        comparable = {
            "status": forecast.get("status"),
            "target_evidence_id": forecast.get("target_evidence_id"),
            "target_metric": forecast.get("target_metric"),
            "baseline_metric_value": forecast.get("baseline_metric_value"),
            "baseline_as_of": forecast.get("baseline_as_of"),
            "expected_direction": forecast.get("expected_direction"),
            "due_date": forecast.get("due_date"),
            "support_score": forecast.get("support_score"),
            "support_score_type": forecast.get("support_score_type"),
        }
    return {
        "macro_pressure_state": pressure,
        "comparable_market_forecast": comparable,
        "semantics": (
            "Research View is a falsifiable directional forecast. Its support score is evidence support, "
            "not a calibrated market probability."
        ),
    }


def _build_market_implied_view(forecast: dict | None, market_snapshot: dict) -> dict:
    levels = deepcopy(market_snapshot.get("market_levels") or {})
    derived = deepcopy(market_snapshot.get("derived_observations") or {})
    five_year = None
    if forecast is not None and isinstance(forecast.get("baseline_metric_value"), (int, float)):
        five_year = {
            "evidence_id": COMPARABLE_MARKET_EVIDENCE_ID,
            "value": float(forecast["baseline_metric_value"]),
            "as_of": forecast.get("baseline_as_of"),
            "semantics": "5Y market-based inflation expectation / compensation measure",
        }
    return {
        "status": "OBSERVED_MARKET_VIEW",
        "five_year_inflation_compensation": five_year,
        "ten_year_inflation_compensation": levels.get("breakeven_10y"),
        "effective_fed_funds_rate": levels.get("effective_fed_funds_rate"),
        "treasury_2y": levels.get("treasury_2y"),
        "treasury_10y": levels.get("treasury_10y"),
        "real_yield_10y": levels.get("real_yield_10y"),
        "term_structure": {
            "curve_shape": derived.get("curve_shape"),
            "term_spread_10y_minus_2y": derived.get("term_spread_10y_minus_2y"),
            "as_of": derived.get("term_spread_as_of"),
        },
        "semantics": {
            "breakeven_is_pure_expected_inflation": False,
            "treasury_2y_is_fed_futures_path": False,
            "observed_market_levels_only": True,
        },
    }


def _assess_mispricing(research_view: dict, market_view: dict) -> dict:
    forecast = research_view.get("comparable_market_forecast") or {}
    market = market_view.get("five_year_inflation_compensation")
    if forecast.get("status") != "OPEN" or market is None:
        return {
            "status": "ABSTAINED_NO_COMPARABLE_OPEN_FORECAST",
            "dimension": "5Y inflation compensation",
            "gap_magnitude_pp": None,
            "positionable": False,
        }

    direction = forecast.get("expected_direction")
    if direction == "rising":
        hypothesis = "RESEARCH_EXPECTS_HIGHER_5Y_INFLATION_COMPENSATION_THAN_CURRENT_BASELINE"
        status = "DIRECTIONAL_GAP_ONLY"
    elif direction == "falling":
        hypothesis = "RESEARCH_EXPECTS_LOWER_5Y_INFLATION_COMPENSATION_THAN_CURRENT_BASELINE"
        status = "DIRECTIONAL_GAP_ONLY"
    elif direction == "flat":
        hypothesis = "RESEARCH_DIRECTIONALLY_ALIGNED_WITH_CURRENT_BASELINE"
        status = "NO_DIRECTIONAL_GAP"
    else:
        hypothesis = "UNRESOLVED"
        status = "ABSTAINED_NO_COMPARABLE_OPEN_FORECAST"

    return {
        "status": status,
        "dimension": "5Y inflation compensation",
        "market_baseline": market.get("value"),
        "market_as_of": market.get("as_of"),
        "research_expected_direction": direction,
        "pricing_hypothesis": hypothesis,
        "gap_magnitude_pp": None,
        "why_not_numeric": (
            "F1 currently forecasts direction, not a numerical terminal level. A numerical mispricing gap "
            "requires a research target level comparable to the market baseline."
        ),
        "positionable": False,
    }


def _empty_ev_contract(mispricing: dict) -> dict:
    return {
        "status": "EV_NOT_COMPUTABLE_MISSING_SCENARIO_BOOK",
        "mispricing_status": mispricing.get("status"),
        "formula": "EV = sum(probability_i * payoff_i) - transaction_cost",
        "required_inputs": [
            "at least two mutually exclusive scenarios",
            "explicit probability for every scenario summing to 1",
            "probability_source for every scenario",
            "payoff for every scenario in one common unit",
            "transaction cost / carry assumption",
        ],
        "forbidden_input": "R5/R7 heuristic support score as probability",
    }
