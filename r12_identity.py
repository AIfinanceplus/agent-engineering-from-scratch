"""R12 Step 2 event identity / settlement validator and same-event RV comparator.

Provider adapters normalize facts. This module decides whether two contracts are
safe to compare as the same binary event. R12 deliberately does not use title
similarity, an LLM, or the deterministic rules parser to auto-approve identity.
The parser prepares fingerprint-bound review material; a human must explicitly
attest the semantic and settlement checks.

Only a verified identity may enter the locked cross-market complement-basket test:

    buy YES at venue A ask + buy NO at venue B ask -> pays 1 if contracts settle identically
    buy YES at venue B ask + buy NO at venue A ask -> same reciprocal basket

A positive margin after explicit costs is a paper signal only. No orders are sent.
"""

from __future__ import annotations

from hashlib import sha256

from r12_rules import validate_rules_analysis_binding


IDENTITY_CHECKS = (
    "same_event_meaning",
    "same_yes_outcome",
    "same_measurement_definition",
    "compatible_resolution_source",
    "compatible_resolution_horizon",
    "edge_cases_reviewed",
)


def validate_event_identity(
    kalshi_contract: dict,
    polymarket_contract: dict,
    *,
    rules_analysis: dict | None = None,
    attestation: dict | None = None,
) -> dict:
    _validate_contract(kalshi_contract, "kalshi")
    _validate_contract(polymarket_contract, "polymarket")

    machine_checks = {
        "providers_are_distinct": kalshi_contract.get("provider") != polymarket_contract.get("provider"),
        "kalshi_is_binary_yes_no": _is_yes_no(kalshi_contract.get("outcomes")),
        "polymarket_is_binary_yes_no": _is_yes_no(polymarket_contract.get("outcomes")),
        "both_have_resolution_metadata": bool(kalshi_contract.get("resolution")) and bool(polymarket_contract.get("resolution")),
        "both_have_time_contract": bool(kalshi_contract.get("time_contract")) and bool(polymarket_contract.get("time_contract")),
    }
    base_machine_ready = all(machine_checks.values())
    rules_binding = validate_rules_analysis_binding(rules_analysis, kalshi_contract, polymarket_contract)
    machine_checks.update(
        {
            "rules_analysis_artifact_valid": rules_binding["artifact_valid"],
            "rules_analysis_contract_ids_match": rules_binding["contract_ids_match"],
            "rules_analysis_fingerprints_current": rules_binding["fingerprints_current"],
            "rules_analysis_matches_current_parser_output": rules_binding["matches_current_parser_output"],
            "rules_analysis_ready_for_human_review": rules_binding["ready_for_human_review"],
            "rules_parser_did_not_auto_approve": rules_binding["parser_did_not_auto_approve"],
        }
    )

    attestation = attestation if isinstance(attestation, dict) else None
    attestation_checks = {key: bool(attestation.get(key)) if attestation else False for key in IDENTITY_CHECKS}
    attestation_source = attestation.get("attestation_source") if attestation else None
    attestation_complete = all(attestation_checks.values()) and isinstance(attestation_source, str) and bool(attestation_source.strip())

    if not base_machine_ready:
        status = "IDENTITY_REJECTED_MACHINE_CONTRACT_INCOMPLETE"
        compatible = False
    elif rules_analysis is None:
        status = "IDENTITY_REJECTED_RULES_ANALYSIS_REQUIRED"
        compatible = False
    elif (
        not rules_binding["artifact_valid"]
        or not rules_binding["contract_ids_match"]
        or not rules_binding["fingerprints_current"]
        or not rules_binding["matches_current_parser_output"]
    ):
        status = "IDENTITY_REJECTED_RULES_ANALYSIS_STALE_OR_INVALID"
        compatible = False
    elif not rules_binding["ready_for_human_review"] or not rules_binding["parser_did_not_auto_approve"]:
        status = "IDENTITY_REJECTED_RULES_ANALYSIS_BLOCKED"
        compatible = False
    elif attestation is None:
        status = "IDENTITY_UNVERIFIED_MANUAL_REVIEW_REQUIRED"
        compatible = False
    elif not attestation_complete:
        status = "IDENTITY_REJECTED_OR_ATTESTATION_INCOMPLETE"
        compatible = False
    else:
        status = "SETTLEMENT_COMPATIBLE_FOR_RV"
        compatible = True

    pair_key = f"{kalshi_contract.get('provider_market_id')}|{polymarket_contract.get('provider_market_id')}"
    identity_id = "ID-" + sha256(pair_key.encode("utf-8")).hexdigest()[:16]
    return {
        "artifact_type": "r12_event_identity",
        "identity_id": identity_id,
        "status": status,
        "settlement_compatible_for_rv": compatible,
        "contracts": {
            "kalshi": _contract_summary(kalshi_contract),
            "polymarket": _contract_summary(polymarket_contract),
        },
        "machine_checks": machine_checks,
        "rules_analysis_gate": {
            **rules_binding,
            "status": rules_analysis.get("status") if isinstance(rules_analysis, dict) else None,
            "blocking_findings": rules_analysis.get("blocking_findings") if isinstance(rules_analysis, dict) else [],
            "comparison_checks": rules_analysis.get("comparison_checks") if isinstance(rules_analysis, dict) else [],
        },
        "manual_attestation": {
            "required_checks": list(IDENTITY_CHECKS),
            "checks": attestation_checks,
            "attestation_source": attestation_source,
            "complete": attestation_complete,
        },
        "review_material": {
            "kalshi_resolution": kalshi_contract.get("resolution"),
            "polymarket_resolution": polymarket_contract.get("resolution"),
            "kalshi_time_contract": kalshi_contract.get("time_contract"),
            "polymarket_time_contract": polymarket_contract.get("time_contract"),
            "kalshi_measurement_contract": kalshi_contract.get("measurement_contract"),
            "polymarket_measurement_contract": polymarket_contract.get("measurement_contract"),
        },
        "guardrails": {
            "title_similarity_used_as_identity": False,
            "llm_auto_approval_used": False,
            "rules_parser_auto_approval_used": False,
            "current_rules_fingerprint_required": True,
            "manual_or_independent_rules_review_required": True,
            "automatic_execution": False,
        },
    }


def compare_cross_market_locked_rv(
    identity: dict,
    kalshi_contract: dict,
    polymarket_contract: dict,
    *,
    estimated_total_cost_per_basket: float = 0.0,
) -> dict:
    """Compare reciprocal cross-venue YES/NO baskets only after identity approval."""
    _validate_contract(kalshi_contract, "kalshi")
    _validate_contract(polymarket_contract, "polymarket")
    if not isinstance(identity, dict) or identity.get("artifact_type") != "r12_event_identity":
        raise ValueError("identity must be an r12_event_identity artifact")
    if not identity.get("settlement_compatible_for_rv") or identity.get("status") != "SETTLEMENT_COMPATIBLE_FOR_RV":
        raise ValueError("cross-market RV requires SETTLEMENT_COMPATIBLE_FOR_RV")

    expected_ids = {
        "kalshi": kalshi_contract.get("provider_market_id"),
        "polymarket": polymarket_contract.get("provider_market_id"),
    }
    actual_ids = {
        key: (identity.get("contracts") or {}).get(key, {}).get("provider_market_id")
        for key in ("kalshi", "polymarket")
    }
    if expected_ids != actual_ids:
        raise ValueError("identity artifact does not belong to the supplied market contracts")

    cost = _non_negative(estimated_total_cost_per_basket, "estimated_total_cost_per_basket")
    kq = kalshi_contract.get("quotes") or {}
    pq = polymarket_contract.get("quotes") or {}
    executable = (
        kq.get("quote_status") in {"EXECUTABLE_TOP_OF_BOOK_FIELDS", "EXECUTABLE_CLOB_TOP_OF_BOOK"}
        and pq.get("quote_status") in {"EXECUTABLE_TOP_OF_BOOK_FIELDS", "EXECUTABLE_CLOB_TOP_OF_BOOK"}
    )

    baskets = [
        _basket(
            name="KALSHI_YES_PLUS_POLYMARKET_NO",
            legs=[
                {"provider": "kalshi", "outcome": "YES", "ask": _price(kq.get("yes_ask"))},
                {"provider": "polymarket", "outcome": "NO", "ask": _price(pq.get("no_ask"))},
            ],
            cost=cost,
            executable=executable,
        ),
        _basket(
            name="POLYMARKET_YES_PLUS_KALSHI_NO",
            legs=[
                {"provider": "polymarket", "outcome": "YES", "ask": _price(pq.get("yes_ask"))},
                {"provider": "kalshi", "outcome": "NO", "ask": _price(kq.get("no_ask"))},
            ],
            cost=cost,
            executable=executable,
        ),
    ]

    opportunities = []
    for basket in baskets:
        if basket["net_edge"] is None or basket["net_edge"] <= 0:
            continue
        opportunities.append(_cross_market_opportunity(identity, basket, kalshi_contract, polymarket_contract))

    opportunities.sort(key=lambda row: -row["net_edge"])
    return {
        "artifact_type": "r12_cross_market_rv_scan",
        "strategy_id": "cross_market_event_rv",
        "identity_id": identity.get("identity_id"),
        "identity_status": identity.get("status"),
        "quote_mode": "EXECUTABLE_TOP_OF_BOOK" if executable else "PARTIAL_OR_INDICATIVE",
        "baskets_checked": baskets,
        "opportunity_count": len(opportunities),
        "paper_signal_count": sum(1 for row in opportunities if row["eligible_for_paper_signal"]),
        "opportunities": opportunities,
        "execution_policy": "PAPER_SIGNAL_ONLY_NO_AUTO_EXECUTION",
        "guardrails": {
            "settlement_identity_required": True,
            "last_trade_used_as_executable_price": False,
            "indicative_price_used_as_executable_price": False,
            "costs_subtracted": True,
            "automatic_execution": False,
        },
    }


def _basket(*, name: str, legs: list[dict], cost: float, executable: bool) -> dict:
    asks = [row.get("ask") for row in legs]
    if not executable or any(value is None for value in asks):
        return {
            "name": name,
            "legs": legs,
            "gross_cost": None,
            "gross_edge": None,
            "estimated_total_cost": cost,
            "net_edge": None,
            "status": "EXECUTABLE_QUOTES_REQUIRED",
        }
    gross_cost = sum(asks)
    gross_edge = 1.0 - gross_cost
    net_edge = gross_edge - cost
    return {
        "name": name,
        "legs": legs,
        "gross_cost": round(gross_cost, 8),
        "gross_edge": round(gross_edge, 8),
        "estimated_total_cost": round(cost, 8),
        "net_edge": round(net_edge, 8),
        "status": "POSITIVE_LOCKED_MARGIN_AFTER_COST" if net_edge > 0 else "NO_LOCKED_MARGIN_AFTER_COST",
    }


def _cross_market_opportunity(identity: dict, basket: dict, kalshi: dict, polymarket: dict) -> dict:
    key = f"{identity.get('identity_id')}|{basket.get('name')}"
    opportunity_id = "OPP-" + sha256(key.encode("utf-8")).hexdigest()[:16]
    net = float(basket["net_edge"])
    executable = basket.get("status") == "POSITIVE_LOCKED_MARGIN_AFTER_COST"
    return {
        "artifact_type": "r12_strategy_opportunity",
        "opportunity_id": opportunity_id,
        "strategy_id": "cross_market_event_rv",
        "subtype": "same_event_cross_market_complement_basket",
        "as_of": "LIVE_PUBLIC_MARKET_DATA",
        "source": "kalshi+polymarket",
        "status": "PAPER_SIGNAL_AVAILABLE" if executable else "NO_EDGE_AFTER_COST",
        "reference_view": {
            "constraint": "verified identical binary settlement => cross-venue YES + NO basket pays 1.0",
            "reference_type": "verified_same_event_complement_constraint",
            "identity_id": identity.get("identity_id"),
        },
        "market_view": {
            "kalshi_market_id": kalshi.get("provider_market_id"),
            "polymarket_market_id": polymarket.get("provider_market_id"),
            "basket": basket,
        },
        "gross_edge": float(basket["gross_edge"]),
        "estimated_cost": float(basket["estimated_total_cost"]),
        "net_edge": net,
        "edge_unit": "probability_price_points",
        "candidate_action": "BUY_BOTH_COMPLEMENT_LEGS_AT_CURRENT_ASKS",
        "settlement_compatibility_verified": True,
        "implementation_verified": True,
        "calibration_status": "EXACT_VERIFIED_COMPLEMENT_REFERENCE_NOT_PROBABILITY_MODEL",
        "payoff_status": "LOCKED_BINARY_PAYOFF_IF_VERIFIED_SETTLEMENT_ASSUMPTIONS_HOLD",
        "liquidity_status": "TOP_OF_BOOK_ONLY_DEPTH_NOT_YET_MODELED",
        "eligible_for_paper_signal": executable,
        "execution_status": "PAPER_SIGNAL_ONLY_NO_AUTO_EXECUTION",
        "rationale": "Two verified same-event complement legs cost less than the $1 binary settlement payoff after explicit estimated costs.",
        "downstream_contract": {
            "ev": "LOCKED_MARGIN_CONTRACT_AT_QUOTED_TOP_OF_BOOK_ONLY",
            "risk": "SETTLEMENT_BASIS_LIQUIDITY_AND_FILL_RISK_REVIEW_REQUIRED",
            "position_sizing": "R11_CONSTRAINT_ENGINE_ONLY_AFTER_IMPLEMENTATION_RISK_MODEL",
        },
        "guardrails": {
            "edge_called_probability_forecast": False,
            "settlement_equivalence_assumed": False,
            "last_trade_used_as_executable_price": False,
            "depth_or_fill_assumed": False,
            "automatic_execution": False,
        },
    }


def _contract_summary(contract: dict) -> dict:
    return {
        "provider": contract.get("provider"),
        "provider_market_id": contract.get("provider_market_id"),
        "provider_event_id": contract.get("provider_event_id"),
        "question": contract.get("question"),
        "outcomes": contract.get("outcomes"),
        "quote_status": (contract.get("quotes") or {}).get("quote_status"),
    }


def _validate_contract(contract: dict, expected_provider: str) -> None:
    if not isinstance(contract, dict) or contract.get("artifact_type") != "r12_market_contract":
        raise ValueError(f"{expected_provider}_contract must be an r12_market_contract")
    if contract.get("provider") != expected_provider:
        raise ValueError(f"expected provider={expected_provider}")


def _is_yes_no(outcomes) -> bool:
    if not isinstance(outcomes, list):
        return False
    return {str(value).upper() for value in outcomes} == {"YES", "NO"}


def _price(value) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError("executable quote must be numeric")
    value = float(value)
    if not 0 <= value <= 1:
        raise ValueError("executable quote must be between 0 and 1")
    return value


def _non_negative(value, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    value = float(value)
    if value < 0:
        raise ValueError(f"{label} must be >= 0")
    return value
