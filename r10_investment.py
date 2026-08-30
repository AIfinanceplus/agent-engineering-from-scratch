"""R10 deterministic Investment intelligence: numerical target -> market gap -> EV contract.

R10 is intentionally downstream of the accepted research stack:

    Research Evidence -> S1 -> D1 -> F1 -> T1 numerical research target
    Market Evidence   -> M6
                               \
                                -> I1 R10 Investment Decision

T1 is a transparent mechanical teaching baseline, not a calibrated forecast. For
the comparable 5Y inflation-compensation series it persists the latest observed
one-step change for one additional F1 horizon:

    target = latest_value + latest_change

I1 may call the resulting difference a numerical research-vs-market gap only when
target metric, unit, baseline, and horizon are explicitly comparable. A gap in the
underlying market measure is still not a security P&L. R10 therefore builds a
standardized unit-exposure payoff template in basis points; actual instrument P&L
still requires duration/DV01/convexity or another explicit sensitivity model.

The module never treats R5/R7 support scores as probabilities. Expected value is
computed only from an explicit scenario book whose probabilities are supplied or
calibrated elsewhere.
"""

from __future__ import annotations

from copy import deepcopy
from math import isclose


COMPARABLE_MARKET_EVIDENCE_ID = "FRED:T5YIE"
TARGET_METHOD = "one_step_change_persistence_baseline"


def build_numerical_research_target(
    research_synthesis: dict,
    forecast_pack: dict,
    reference_date: str,
) -> dict:
    """Create a reproducible numerical target from an already-grounded S1 signal.

    This is deliberately a simple baseline. It does not claim calibration, fair
    value, or security-specific alpha; it exists so the system can teach the
    contract required before numerical mispricing is even definable.
    """
    if not isinstance(research_synthesis, dict) or research_synthesis.get("kind") != "synthesis":
        raise ValueError("research_synthesis must be a grounded S1 synthesis")
    if not isinstance(forecast_pack, dict) or forecast_pack.get("artifact_type") != "forecast_pack":
        raise ValueError("forecast_pack must be an F1 forecast pack")
    research_ids = list(research_synthesis.get("evidence_ids") or [])
    if list(forecast_pack.get("evidence_ids") or []) != research_ids:
        raise ValueError("F1 must preserve the S1 research Evidence lineage")

    signal = _find_comparable_signal(research_synthesis)
    forecast = _find_comparable_forecast(forecast_pack)
    base = {
        "kind": "synthesis",
        "artifact_type": "r10_numerical_research_target",
        "target_id": "T1-5Y-INFLATION-COMPENSATION",
        "reference_date": reference_date,
        "evidence_ids": [COMPARABLE_MARKET_EVIDENCE_ID] if COMPARABLE_MARKET_EVIDENCE_ID in research_ids else [],
        "target_evidence_id": COMPARABLE_MARKET_EVIDENCE_ID,
        "target_metric": "5y_inflation_compensation_level",
        "unit": "percent",
        "method": TARGET_METHOD,
        "calibration_status": "NOT_CALIBRATED_MECHANICAL_BASELINE",
        "probability": None,
        "guardrails": {
            "support_score_used_as_probability": False,
            "point_target_presented_as_calibrated_forecast": False,
            "security_fair_value_claimed": False,
        },
    }

    reason = None
    if signal is None:
        reason = "missing_comparable_s1_signal"
    elif forecast is None or forecast.get("status") != "OPEN":
        reason = "missing_comparable_open_f1_forecast"
    elif signal.get("kind") != "change":
        reason = "s1_signal_has_no_numeric_one_step_change"
    elif forecast.get("target_metric") != "level":
        reason = "f1_target_metric_not_level"

    latest = _number(signal.get("latest_value")) if signal else None
    previous = _number(signal.get("previous_value")) if signal else None
    change = _number(signal.get("change")) if signal else None
    forecast_baseline = _number(forecast.get("baseline_metric_value")) if forecast else None
    if reason is None and None in {latest, previous, change, forecast_baseline}:
        reason = "numeric_inputs_missing"
    if reason is None and not isclose(latest, forecast_baseline, rel_tol=0.0, abs_tol=1e-9):
        reason = "s1_latest_and_f1_baseline_not_aligned"
    if reason is None and forecast.get("expected_direction") != signal.get("direction"):
        reason = "s1_direction_and_f1_direction_not_aligned"

    if reason is not None:
        return {
            **base,
            "answer": f"T1 abstained: {reason}. No numerical research target is issued.",
            "value": 0.0,
            "confidence": 0.0,
            "confidence_type": "abstained_no_numeric_target",
            "status": "ABSTAINED_NUMERICAL_TARGET_UNAVAILABLE",
            "abstain_reason": reason,
            "baseline_value": latest,
            "previous_value": previous,
            "observed_change_pp": change,
            "target_value": None,
            "target_gap_from_baseline_pp": None,
            "target_gap_from_baseline_bp": None,
            "baseline_as_of": forecast.get("baseline_as_of") if forecast else None,
            "due_date": forecast.get("due_date") if forecast else None,
        }

    target = round(latest + change, 6)
    gap_pp = round(target - latest, 6)
    gap_bp = round(gap_pp * 100.0, 3)
    support = min(
        float(research_synthesis.get("confidence", 0.0)),
        float(forecast.get("support_score", research_synthesis.get("confidence", 0.0)) or 0.0),
    )
    return {
        **base,
        "answer": (
            f"T1 mechanical target for {COMPARABLE_MARKET_EVIDENCE_ID}: {latest:.4f}% -> "
            f"{target:.4f}% by {forecast.get('due_date')} using one-step change persistence. "
            "This is a reproducible baseline, not a calibrated probability or security fair value."
        ),
        "value": target,
        "confidence": support,
        "confidence_type": forecast.get(
            "support_score_type", "heuristic_support_score_not_probability"
        ),
        "status": "NUMERICAL_TARGET_AVAILABLE",
        "abstain_reason": None,
        "previous_value": previous,
        "baseline_value": latest,
        "observed_change_pp": change,
        "observed_direction": signal.get("direction"),
        "target_value": target,
        "target_gap_from_baseline_pp": gap_pp,
        "target_gap_from_baseline_bp": gap_bp,
        "baseline_as_of": forecast.get("baseline_as_of"),
        "due_date": forecast.get("due_date"),
        "horizon_contract": "same_as_f1_due_date",
    }


def build_r10_investment_decision(
    question: str,
    research_synthesis: dict,
    domain_brief: dict,
    forecast_pack: dict,
    research_target: dict,
    market_snapshot: dict,
    reference_date: str,
) -> dict:
    _validate_upstream(
        research_synthesis,
        domain_brief,
        forecast_pack,
        research_target,
        market_snapshot,
    )

    research_ids = list(research_synthesis.get("evidence_ids") or [])
    market_ids = list(market_snapshot.get("evidence_ids") or [])
    forecast = _find_comparable_forecast(forecast_pack)
    market_view = _build_market_implied_view(forecast, research_target, market_snapshot)
    research_view = _build_research_view(domain_brief, forecast, research_target)
    mispricing = _assess_mispricing(research_view, market_view)
    payoff_template = _build_standardized_payoff_template(mispricing)
    ev = _empty_ev_contract(mispricing, payoff_template)

    if mispricing["status"] == "NUMERIC_GAP_AVAILABLE":
        position_status = "NO_POSITION_EV_NOT_COMPUTED"
    elif mispricing["status"] == "DIRECTIONAL_GAP_ONLY":
        position_status = "NO_POSITION_GAP_NOT_QUANTIFIED"
    elif mispricing["status"] in {"NO_DIRECTIONAL_GAP", "NO_NUMERIC_GAP"}:
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
            "R10 separates Research View from observable Market View, requires an explicit numerical "
            "T1 target before quantifying a gap, then translates that gap only into a standardized "
            "market-move payoff template. Security-specific P&L and EV still require explicit inputs."
        ),
        "value": float(mispricing.get("gap_magnitude_bp") or 0.0),
        "unit": "basis_points_research_market_gap",
        "confidence": min(
            float(research_synthesis.get("confidence", 0.0)),
            float(domain_brief.get("confidence", 0.0)),
            float(research_target.get("confidence", 0.0)),
        ),
        "confidence_type": research_synthesis.get(
            "confidence_type", "heuristic_support_score_not_probability"
        ),
        "reference_date": reference_date,
        "evidence_ids": combined_ids,
        "research_evidence_ids": research_ids,
        "market_evidence_ids": market_ids,
        "shared_pricing_comparator_evidence_ids": [COMPARABLE_MARKET_EVIDENCE_ID],
        "numerical_research_target": deepcopy(research_target),
        "research_view": research_view,
        "market_implied_view": market_view,
        "mispricing": mispricing,
        "scenario_payoff_template": payoff_template,
        "expected_value": ev,
        "position_gate": {
            "status": position_status,
            "position": "NONE",
            "required_before_position": [
                "comparable Research View and Market View",
                "numerical target with explicit method / horizon / unit",
                "scenario probabilities from an explicit source/assumption",
                "scenario payoffs including adverse outcomes",
                "instrument sensitivity if converting market-move bp into security P&L",
                "transaction costs / carry / implementation assumptions",
                "risk budget and loss limit",
            ],
        },
        "guardrails": {
            "support_score_used_as_probability": False,
            "fed_futures_path_inferred_from_treasury_yield": False,
            "directional_gap_called_numeric_mispricing": False,
            "mechanical_target_called_calibrated_forecast": False,
            "market_move_bp_called_security_pnl": False,
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


def _validate_upstream(
    research_synthesis,
    domain_brief,
    forecast_pack,
    research_target,
    market_snapshot,
) -> None:
    if not isinstance(research_synthesis, dict) or research_synthesis.get("kind") != "synthesis":
        raise ValueError("research_synthesis must be a grounded S1 synthesis")
    if not isinstance(domain_brief, dict) or domain_brief.get("domain") != "investment":
        raise ValueError("domain_brief must be an Investment D1 artifact")
    if not isinstance(forecast_pack, dict) or forecast_pack.get("artifact_type") != "forecast_pack":
        raise ValueError("forecast_pack must be an F1 forecast pack")
    if not isinstance(research_target, dict) or research_target.get("artifact_type") != "r10_numerical_research_target":
        raise ValueError("research_target must be an R10 numerical research target")
    if not isinstance(market_snapshot, dict) or market_snapshot.get("artifact_type") != "market_pricing_snapshot":
        raise ValueError("market_snapshot must be an R9 market-pricing snapshot")

    research_ids = list(research_synthesis.get("evidence_ids") or [])
    if list(domain_brief.get("evidence_ids") or []) != research_ids:
        raise ValueError("D1 must preserve the S1 research Evidence lineage")
    if list(forecast_pack.get("evidence_ids") or []) != research_ids:
        raise ValueError("F1 must preserve the S1 research Evidence lineage")
    target_ids = list(research_target.get("evidence_ids") or [])
    if any(item not in research_ids for item in target_ids):
        raise ValueError("T1 may cite only Evidence already present in S1")


def _find_comparable_signal(research_synthesis: dict) -> dict | None:
    for row in research_synthesis.get("signals") or []:
        if row.get("evidence_id") == COMPARABLE_MARKET_EVIDENCE_ID:
            return deepcopy(row)
    return None


def _find_comparable_forecast(forecast_pack: dict) -> dict | None:
    for row in forecast_pack.get("forecasts") or []:
        if row.get("target_evidence_id") == COMPARABLE_MARKET_EVIDENCE_ID:
            return deepcopy(row)
    return None


def _build_research_view(
    domain_brief: dict,
    forecast: dict | None,
    research_target: dict,
) -> dict:
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
        "numerical_target": {
            "status": research_target.get("status"),
            "target_value": research_target.get("target_value"),
            "unit": research_target.get("unit"),
            "method": research_target.get("method"),
            "baseline_value": research_target.get("baseline_value"),
            "baseline_as_of": research_target.get("baseline_as_of"),
            "due_date": research_target.get("due_date"),
            "calibration_status": research_target.get("calibration_status"),
        },
        "semantics": (
            "Research View combines the falsifiable F1 direction with a transparent T1 numerical baseline. "
            "T1 is mechanical and uncalibrated; its support score is not a probability."
        ),
    }


def _build_market_implied_view(
    forecast: dict | None,
    research_target: dict,
    market_snapshot: dict,
) -> dict:
    levels = deepcopy(market_snapshot.get("market_levels") or {})
    derived = deepcopy(market_snapshot.get("derived_observations") or {})
    five_year = None
    baseline = _number(research_target.get("baseline_value"))
    if baseline is None and forecast is not None:
        baseline = _number(forecast.get("baseline_metric_value"))
    if baseline is not None:
        five_year = {
            "evidence_id": COMPARABLE_MARKET_EVIDENCE_ID,
            "value": baseline,
            "unit": "percent",
            "as_of": research_target.get("baseline_as_of") or (forecast or {}).get("baseline_as_of"),
            "semantics": "5Y market-based inflation compensation observable used as the comparison anchor",
            "lineage_role": "shared_research_signal_and_market_observable",
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
    target = research_view.get("numerical_target") or {}
    market = market_view.get("five_year_inflation_compensation")
    if forecast.get("status") != "OPEN" or market is None:
        return {
            "status": "ABSTAINED_NO_COMPARABLE_OPEN_FORECAST",
            "dimension": "5Y inflation compensation",
            "gap_magnitude_pp": None,
            "gap_magnitude_bp": None,
            "positionable": False,
        }

    direction = forecast.get("expected_direction")
    target_value = _number(target.get("target_value"))
    market_value = _number(market.get("value"))
    same_unit = target.get("unit") == market.get("unit") == "percent"
    same_horizon_contract = target.get("due_date") == forecast.get("due_date")
    if (
        target.get("status") == "NUMERICAL_TARGET_AVAILABLE"
        and target_value is not None
        and market_value is not None
        and same_unit
        and same_horizon_contract
    ):
        gap_pp = round(target_value - market_value, 6)
        gap_bp = round(gap_pp * 100.0, 3)
        if isclose(gap_pp, 0.0, rel_tol=0.0, abs_tol=1e-9):
            status = "NO_NUMERIC_GAP"
            hypothesis = "RESEARCH_TARGET_EQUALS_CURRENT_MARKET_BASELINE"
        else:
            status = "NUMERIC_GAP_AVAILABLE"
            hypothesis = (
                "RESEARCH_TARGET_ABOVE_CURRENT_5Y_INFLATION_COMPENSATION"
                if gap_pp > 0
                else "RESEARCH_TARGET_BELOW_CURRENT_5Y_INFLATION_COMPENSATION"
            )
        return {
            "status": status,
            "dimension": "5Y inflation compensation",
            "market_baseline": market_value,
            "market_as_of": market.get("as_of"),
            "research_target": target_value,
            "research_target_due_date": target.get("due_date"),
            "research_target_method": target.get("method"),
            "research_target_calibration_status": target.get("calibration_status"),
            "research_expected_direction": direction,
            "pricing_hypothesis": hypothesis,
            "gap_magnitude_pp": gap_pp,
            "gap_magnitude_bp": gap_bp,
            "gap_formula": "research_target - current_market_value",
            "comparable_unit": "percent",
            "positionable": False,
            "interpretation": (
                "This is a numerical gap in the underlying 5Y inflation-compensation measure under the "
                "mechanical T1 baseline. It is not yet a security-specific expected return or fair-value claim."
            ),
        }

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
        "gap_magnitude_bp": None,
        "why_not_numeric": (
            "A numerical gap requires an available T1 target with the same metric, percent unit, and F1 horizon."
        ),
        "positionable": False,
    }


def _build_standardized_payoff_template(mispricing: dict) -> dict:
    gap_bp = _number(mispricing.get("gap_magnitude_bp"))
    if mispricing.get("status") != "NUMERIC_GAP_AVAILABLE" or gap_bp is None:
        return {
            "status": "PAYOFF_TEMPLATE_UNAVAILABLE_NO_NUMERIC_GAP",
            "payoff_unit": "bp_on_unit_directional_exposure",
            "probabilities": "NOT_ASSIGNED",
            "instrument_pnl_status": "NOT_MODELED",
            "scenarios": [],
        }

    magnitude = round(abs(gap_bp), 3)
    exposure = "LONG_5Y_INFLATION_COMPENSATION" if gap_bp > 0 else "SHORT_5Y_INFLATION_COMPENSATION"
    return {
        "status": "STANDARDIZED_MARKET_MOVE_PAYOFF_TEMPLATE_AVAILABLE",
        "exposure": exposure,
        "payoff_unit": "bp_on_unit_directional_exposure",
        "probabilities": "NOT_ASSIGNED",
        "instrument_pnl_status": "NOT_MODELED_REQUIRES_SENSITIVITY",
        "scenarios": [
            {
                "name": "research_target_realized",
                "market_move_bp": gap_bp,
                "payoff": magnitude,
                "probability": None,
                "probability_source": None,
                "meaning": "market converges from current level to the T1 research target",
            },
            {
                "name": "no_repricing",
                "market_move_bp": 0.0,
                "payoff": 0.0,
                "probability": None,
                "probability_source": None,
                "meaning": "market remains at the current comparison baseline",
            },
            {
                "name": "equal_opposite_move",
                "market_move_bp": round(-gap_bp, 3),
                "payoff": round(-magnitude, 3),
                "probability": None,
                "probability_source": None,
                "meaning": "stress case: market moves the same magnitude opposite the research target",
            },
        ],
        "guardrails": {
            "scenario_probabilities_fabricated": False,
            "standardized_bp_payoff_called_security_pnl": False,
            "actual_trade_requires_instrument_sensitivity": True,
        },
    }


def _empty_ev_contract(mispricing: dict, payoff_template: dict) -> dict:
    return {
        "status": "EV_NOT_COMPUTABLE_MISSING_SCENARIO_PROBABILITIES",
        "mispricing_status": mispricing.get("status"),
        "payoff_template_status": payoff_template.get("status"),
        "formula": "EV = sum(probability_i * payoff_i) - transaction_cost",
        "required_inputs": [
            "explicit probability for every scenario summing to 1",
            "probability_source for every scenario",
            "transaction cost / carry assumption",
            "instrument sensitivity if payoff unit must be converted from market-move bp to security P&L",
        ],
        "available_without_probabilities": "standardized scenario payoff template when numerical gap exists",
        "forbidden_input": "R5/R7 heuristic support score as probability",
    }


def _number(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
