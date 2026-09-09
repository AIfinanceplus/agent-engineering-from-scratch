"""R12 strategy layer: unified Opportunity Contract + deterministic structural scanner.

R12 sits downstream of research/market data and upstream of EV/risk/sizing. It does
not execute trades. Step 1 focuses on structural/logic relative value because the
reference is a mathematical contract rather than an uncalibrated forecast.

Supported deterministic checks:
- Binary complement: YES + NO = 1 for the same verified settlement contract.
- Threshold monotonicity: for events X > K, probability cannot increase as K rises.
- Mutually-exclusive exhaustive baskets: sum(probabilities) = 1 when the outcome
  set is explicitly verified as both mutually exclusive and exhaustive.

Every detected edge is normalized into the same r12_strategy_opportunity artifact.
Later cross-market, FOMC, CPI and options adapters can emit the same contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any


EPS = 1e-9


@dataclass(frozen=True)
class StrategyStatus:
    strategy_id: str
    name: str
    status: str
    reference_type: str
    next_dependency: str


STRATEGY_REGISTRY = (
    StrategyStatus(
        "structural_logic_rv",
        "Structural / Logic Arbitrage",
        "ACTIVE_DETERMINISTIC",
        "exact_logical_constraint",
        "live prediction-market adapters + liquidity/fee model",
    ),
    StrategyStatus(
        "cross_market_event_rv",
        "Same-event Cross-market RV",
        "CONTRACT_READY_DATA_ADAPTER_PENDING",
        "same_event_other_market",
        "event identity + settlement parser + market adapters",
    ),
    StrategyStatus(
        "fomc_probability_rv",
        "FOMC Probability RV",
        "PLANNED",
        "rates_market_distribution",
        "SOFR/OIS/Fed Funds + event-market adapters",
    ),
    StrategyStatus(
        "cpi_macro_rv",
        "CPI / Macro Data RV",
        "RESEARCH_ENGINE_AVAILABLE_CALIBRATION_PENDING",
        "calibrated_macro_probability_model",
        "probability calibration + event-market adapter",
    ),
    StrategyStatus(
        "options_event_rv",
        "Options vs Event-market RV",
        "PLANNED",
        "options_implied_distribution",
        "options surface adapter + risk-neutral/real-world bridge",
    ),
)


def strategy_registry_snapshot() -> dict:
    return {
        "artifact_type": "r12_strategy_registry",
        "strategies": [row.__dict__ for row in STRATEGY_REGISTRY],
        "execution_policy": "PAPER_SIGNAL_ONLY_NO_AUTO_EXECUTION",
    }


def scan_structural_opportunities(snapshot: dict) -> dict:
    """Scan a supplied market snapshot for exact logical inconsistencies.

    This function intentionally does not fetch data. A future source adapter owns
    live market retrieval and normalization. The scanner owns only mathematical
    constraints and the StrategyOpportunity contract.
    """
    if not isinstance(snapshot, dict):
        raise ValueError("snapshot must be an object")
    as_of = _required_text(snapshot.get("as_of"), "as_of")
    source = _required_text(snapshot.get("source"), "source")

    opportunities: list[dict] = []
    observations = 0

    for row in snapshot.get("binary_markets") or []:
        observations += 1
        opportunities.extend(_scan_binary_complement(row, as_of=as_of, source=source))

    for group in snapshot.get("threshold_groups") or []:
        contracts = group.get("contracts") or []
        observations += max(0, len(contracts) - 1)
        opportunities.extend(_scan_threshold_group(group, as_of=as_of, source=source))

    for group in snapshot.get("exclusive_groups") or []:
        observations += 1
        opportunities.extend(_scan_exclusive_group(group, as_of=as_of, source=source))

    opportunities.sort(key=lambda row: (not row["eligible_for_paper_signal"], -abs(row["net_edge"])))
    return {
        "artifact_type": "r12_structural_scan",
        "strategy_id": "structural_logic_rv",
        "as_of": as_of,
        "source": source,
        "observations_checked": observations,
        "opportunity_count": len(opportunities),
        "paper_signal_count": sum(1 for row in opportunities if row["eligible_for_paper_signal"]),
        "opportunities": opportunities,
        "execution_policy": "PAPER_SIGNAL_ONLY_NO_AUTO_EXECUTION",
        "guardrails": {
            "prediction_model_required": False,
            "logical_reference_exact_when_contract_verified": True,
            "settlement_compatibility_required": True,
            "transaction_costs_subtracted_before_paper_signal": True,
            "shortability_never_assumed": True,
            "automatic_execution": False,
        },
    }


def _scan_binary_complement(row: dict, *, as_of: str, source: str) -> list[dict]:
    if not isinstance(row, dict):
        raise ValueError("binary market row must be an object")
    event_id = _required_text(row.get("event_id"), "binary event_id")
    yes = _prob(row.get("yes_price"), f"{event_id}.yes_price")
    no = _prob(row.get("no_price"), f"{event_id}.no_price")
    cost = _non_negative(row.get("estimated_total_cost", 0.0), f"{event_id}.estimated_total_cost")
    settlement_verified = bool(row.get("settlement_compatibility_verified", False))
    shortability = bool(row.get("shortability_verified", False))
    total = yes + no
    deviation = total - 1.0
    if abs(deviation) <= EPS:
        return []

    if total < 1.0:
        gross_edge = 1.0 - total
        action = "BUY_YES_AND_NO_BASKET"
        implementation_verified = settlement_verified
        why = "Verified complement basket pays 1.0 at settlement if both legs share the same binary contract."
        payoff_status = "LOCKED_PAYOFF_MARGIN_IF_CONTRACT_ASSUMPTIONS_HOLD"
    else:
        gross_edge = total - 1.0
        action = "SHORT_OR_SELL_YES_AND_NO_BASKET"
        implementation_verified = settlement_verified and shortability
        why = "Complement prices exceed 1.0; monetization requires verified ability to short/sell both legs."
        payoff_status = "OVERROUND_REQUIRES_SHORTABILITY"

    return [_opportunity(
        strategy_id="structural_logic_rv",
        opportunity_key=f"binary:{event_id}:{as_of}",
        subtype="binary_complement",
        as_of=as_of,
        source=source,
        reference_view={"constraint": "YES + NO = 1.0", "reference_type": "exact_logical_constraint"},
        market_view={"event_id": event_id, "yes_price": yes, "no_price": no, "sum": round(total, 8)},
        gross_edge=gross_edge,
        estimated_cost=cost,
        candidate_action=action,
        settlement_verified=settlement_verified,
        implementation_verified=implementation_verified,
        calibration_status="EXACT_LOGICAL_REFERENCE_NOT_PROBABILITY_MODEL",
        payoff_status=payoff_status,
        rationale=why,
    )]


def _scan_threshold_group(group: dict, *, as_of: str, source: str) -> list[dict]:
    if not isinstance(group, dict):
        raise ValueError("threshold group must be an object")
    group_id = _required_text(group.get("group_id"), "threshold group_id")
    relation = _required_text(group.get("relation"), f"{group_id}.relation").lower()
    if relation != "greater_than":
        raise ValueError("R12 Step 1 supports threshold relation=greater_than only")
    settlement_verified = bool(group.get("settlement_compatibility_verified", False))
    pair_trade_verified = bool(group.get("pair_trade_capability_verified", False))
    cost = _non_negative(group.get("estimated_pair_cost", 0.0), f"{group_id}.estimated_pair_cost")
    contracts = group.get("contracts")
    if not isinstance(contracts, list) or len(contracts) < 2:
        raise ValueError(f"{group_id}.contracts must contain at least two thresholds")

    normalized = []
    for row in contracts:
        threshold = _number(row.get("threshold"), f"{group_id}.threshold")
        probability = _prob(row.get("yes_price"), f"{group_id}.{threshold}.yes_price")
        contract_id = _required_text(row.get("contract_id"), f"{group_id}.{threshold}.contract_id")
        normalized.append((threshold, probability, contract_id))
    normalized.sort(key=lambda item: item[0])

    results = []
    for lower, higher in zip(normalized, normalized[1:]):
        lower_k, lower_p, lower_id = lower
        higher_k, higher_p, higher_id = higher
        # For X>K, P(X>higher) must be <= P(X>lower).
        violation = higher_p - lower_p
        if violation <= EPS:
            continue
        results.append(_opportunity(
            strategy_id="structural_logic_rv",
            opportunity_key=f"threshold:{group_id}:{lower_id}:{higher_id}:{as_of}",
            subtype="threshold_monotonicity",
            as_of=as_of,
            source=source,
            reference_view={
                "constraint": "P(X > K_high) <= P(X > K_low)",
                "reference_type": "exact_probability_set_inclusion",
                "lower_threshold": lower_k,
                "higher_threshold": higher_k,
            },
            market_view={
                "group_id": group_id,
                "lower_contract_id": lower_id,
                "lower_yes_price": lower_p,
                "higher_contract_id": higher_id,
                "higher_yes_price": higher_p,
            },
            gross_edge=violation,
            estimated_cost=cost,
            candidate_action="LONG_LOWER_THRESHOLD_YES_AND_SHORT_HIGHER_THRESHOLD_YES",
            settlement_verified=settlement_verified,
            implementation_verified=settlement_verified and pair_trade_verified,
            calibration_status="EXACT_SET_INCLUSION_REFERENCE_NOT_PROBABILITY_MODEL",
            payoff_status="STRUCTURAL_PAIR_EDGE_NOT_FULL_TRADE_EV",
            rationale="Higher threshold is priced more likely than the nested lower threshold, violating monotonicity.",
        ))
    return results


def _scan_exclusive_group(group: dict, *, as_of: str, source: str) -> list[dict]:
    if not isinstance(group, dict):
        raise ValueError("exclusive group must be an object")
    group_id = _required_text(group.get("group_id"), "exclusive group_id")
    mutually_exclusive = bool(group.get("mutually_exclusive_verified", False))
    exhaustive = bool(group.get("exhaustive_verified", False))
    settlement_verified = bool(group.get("settlement_compatibility_verified", False))
    shortability = bool(group.get("shortability_verified", False))
    cost = _non_negative(group.get("estimated_total_cost", 0.0), f"{group_id}.estimated_total_cost")
    contracts = group.get("contracts")
    if not isinstance(contracts, list) or len(contracts) < 2:
        raise ValueError(f"{group_id}.contracts must contain at least two outcomes")
    normalized = []
    for row in contracts:
        contract_id = _required_text(row.get("contract_id"), f"{group_id}.contract_id")
        price = _prob(row.get("yes_price"), f"{group_id}.{contract_id}.yes_price")
        normalized.append({"contract_id": contract_id, "yes_price": price})
    total = sum(row["yes_price"] for row in normalized)
    deviation = total - 1.0
    if abs(deviation) <= EPS:
        return []

    logical_verified = mutually_exclusive and exhaustive and settlement_verified
    if total < 1.0:
        action = "BUY_ALL_EXHAUSTIVE_OUTCOMES"
        implementation_verified = logical_verified
        gross_edge = 1.0 - total
        payoff_status = "LOCKED_BASKET_MARGIN_IF_OUTCOME_SET_VERIFIED"
    else:
        action = "SHORT_OR_SELL_ALL_EXHAUSTIVE_OUTCOMES"
        implementation_verified = logical_verified and shortability
        gross_edge = total - 1.0
        payoff_status = "OVERROUND_REQUIRES_SHORTABILITY"

    return [_opportunity(
        strategy_id="structural_logic_rv",
        opportunity_key=f"exclusive:{group_id}:{as_of}",
        subtype="mutually_exclusive_exhaustive_sum",
        as_of=as_of,
        source=source,
        reference_view={
            "constraint": "sum(P(outcome_i)) = 1.0",
            "reference_type": "exact_partition_constraint",
            "mutually_exclusive_verified": mutually_exclusive,
            "exhaustive_verified": exhaustive,
        },
        market_view={"group_id": group_id, "contracts": normalized, "sum": round(total, 8)},
        gross_edge=gross_edge,
        estimated_cost=cost,
        candidate_action=action,
        settlement_verified=settlement_verified,
        implementation_verified=implementation_verified,
        calibration_status="EXACT_PARTITION_REFERENCE_NOT_PROBABILITY_MODEL",
        payoff_status=payoff_status,
        rationale="Verified mutually-exclusive exhaustive outcomes should sum to one before implementation costs.",
    )]


def _opportunity(
    *,
    strategy_id: str,
    opportunity_key: str,
    subtype: str,
    as_of: str,
    source: str,
    reference_view: dict,
    market_view: dict,
    gross_edge: float,
    estimated_cost: float,
    candidate_action: str,
    settlement_verified: bool,
    implementation_verified: bool,
    calibration_status: str,
    payoff_status: str,
    rationale: str,
) -> dict:
    gross = round(float(gross_edge), 8)
    cost = round(float(estimated_cost), 8)
    net = round(gross - cost, 8)
    positive_after_cost = net > EPS
    eligible = bool(settlement_verified and implementation_verified and positive_after_cost)
    if not settlement_verified:
        status = "BLOCKED_SETTLEMENT_NOT_VERIFIED"
    elif not implementation_verified:
        status = "OBSERVED_EDGE_IMPLEMENTATION_NOT_VERIFIED"
    elif not positive_after_cost:
        status = "NO_EDGE_AFTER_COST"
    else:
        status = "PAPER_SIGNAL_AVAILABLE"

    digest = sha256(opportunity_key.encode("utf-8")).hexdigest()[:16]
    return {
        "artifact_type": "r12_strategy_opportunity",
        "opportunity_id": f"OPP-{digest}",
        "strategy_id": strategy_id,
        "subtype": subtype,
        "as_of": as_of,
        "source": source,
        "status": status,
        "reference_view": reference_view,
        "market_view": market_view,
        "gross_edge": gross,
        "estimated_cost": cost,
        "net_edge": net,
        "edge_unit": "probability_price_points",
        "candidate_action": candidate_action,
        "settlement_compatibility_verified": bool(settlement_verified),
        "implementation_verified": bool(implementation_verified),
        "calibration_status": calibration_status,
        "payoff_status": payoff_status,
        "liquidity_status": "NOT_MODELED_STEP1",
        "eligible_for_paper_signal": eligible,
        "execution_status": "PAPER_SIGNAL_ONLY_NO_AUTO_EXECUTION",
        "rationale": rationale,
        "downstream_contract": {
            "ev": "USE_STRATEGY_SPECIFIC_PAYOFF_MODEL_OR_R10_EV_BEFORE_POSITIONING",
            "risk": "REQUIRED_BEFORE_POSITION_REVIEW",
            "position_sizing": "R11_CONSTRAINT_ENGINE_ONLY_AFTER_EV_AND_RISK",
        },
        "guardrails": {
            "edge_called_probability_forecast": False,
            "shortability_assumed": False,
            "settlement_equivalence_assumed": False,
            "liquidity_assumed": False,
            "automatic_execution": False,
        },
    }


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value.strip()


def _number(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    return float(value)


def _prob(value: Any, label: str) -> float:
    number = _number(value, label)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{label} must be between 0 and 1")
    return number


def _non_negative(value: Any, label: str) -> float:
    number = _number(value, label)
    if number < 0:
        raise ValueError(f"{label} must be >= 0")
    return number
