"""R12 Step 4 depth-aware paper execution model.

This module converts normalized public order books into a conservative execution
quote for the already identity-verified cross-market complement basket. It never
places orders and never assumes that top-of-book size is sufficient.

The model deliberately keeps provider fee inputs explicit. A positive price edge
without an explicit fee model is NOT eligible for a paper signal.
"""

from __future__ import annotations

from hashlib import sha256
from json import dumps
from math import isfinite
from typing import Any


EPS = 1e-9
PROVIDERS = ("kalshi", "polymarket")


def quote_cross_market_execution(
    identity: dict,
    kalshi_contract: dict,
    polymarket_contract: dict,
    *,
    target_contracts: float,
    fee_model: dict | None = None,
    latency_buffer_bps: float = 0.0,
) -> dict:
    """Walk public asks for reciprocal complement baskets at a target quantity.

    `latency_buffer_bps` is an explicit adverse-price buffer applied to each leg.
    It is a teaching risk buffer, not an estimate of realized latency slippage.
    """
    _validate_identity(identity, kalshi_contract, polymarket_contract)
    quantity = _positive(target_contracts, "target_contracts")
    latency_bps = _non_negative(latency_buffer_bps, "latency_buffer_bps")
    fee_contract = _normalize_fee_model(fee_model)

    contracts = {"kalshi": kalshi_contract, "polymarket": polymarket_contract}
    baskets = [
        _execution_basket(
            name="KALSHI_YES_PLUS_POLYMARKET_NO",
            legs=[("kalshi", "YES"), ("polymarket", "NO")],
            contracts=contracts,
            quantity=quantity,
            fee_contract=fee_contract,
            latency_bps=latency_bps,
        ),
        _execution_basket(
            name="POLYMARKET_YES_PLUS_KALSHI_NO",
            legs=[("polymarket", "YES"), ("kalshi", "NO")],
            contracts=contracts,
            quantity=quantity,
            fee_contract=fee_contract,
            latency_bps=latency_bps,
        ),
    ]

    opportunities = []
    for basket in baskets:
        if basket["eligible_for_paper_signal"]:
            opportunities.append(_execution_opportunity(identity, basket, kalshi_contract, polymarket_contract))
    opportunities.sort(key=lambda row: -row["net_edge_per_contract"])

    return {
        "artifact_type": "r12_execution_quality_scan",
        "strategy_id": "cross_market_event_rv",
        "identity_id": identity.get("identity_id"),
        "target_contracts": quantity,
        "fee_model_status": fee_contract["status"],
        "fee_model_source": fee_contract.get("source"),
        "latency_buffer_bps_per_leg": latency_bps,
        "baskets_checked": baskets,
        "opportunity_count": len(opportunities),
        "paper_signal_count": len(opportunities),
        "opportunities": opportunities,
        "execution_policy": "PAPER_SIGNAL_ONLY_NO_AUTO_EXECUTION",
        "guardrails": {
            "full_depth_required_for_target_quantity": True,
            "partial_fill_never_treated_as_locked_basket": True,
            "fees_must_be_explicit_for_signal": True,
            "slippage_derived_from_book_walk": True,
            "latency_buffer_is_user_supplied_not_calibrated": True,
            "automatic_execution": False,
        },
    }


def _execution_basket(
    *,
    name: str,
    legs: list[tuple[str, str]],
    contracts: dict[str, dict],
    quantity: float,
    fee_contract: dict,
    latency_bps: float,
) -> dict:
    leg_quotes = []
    for provider, outcome in legs:
        contract = contracts[provider]
        provider_book = contract.get("orderbook") or {}
        outcome_book = provider_book.get(outcome) or {}
        levels = outcome_book.get("asks") or []
        walked = _walk_asks(levels, quantity)
        provider_fee = fee_contract["providers"].get(provider)
        fee = _fee_for_leg(walked, provider_fee) if provider_fee is not None else None
        leg_quotes.append(
            {
                "provider": provider,
                "outcome": outcome,
                **walked,
                "fee": fee,
                "fee_model": provider_fee,
                "book_snapshot_status": provider_book.get("snapshot_status"),
                "book_snapshot_timestamp": outcome_book.get("snapshot_timestamp"),
                "book_snapshot_hash": outcome_book.get("snapshot_hash"),
            }
        )

    max_complete = min((row["available_depth"] for row in leg_quotes), default=0.0)
    full_fill = all(row["full_fill"] for row in leg_quotes)
    depth_present = all(row["book_level_count"] > 0 for row in leg_quotes)
    explicit_fees = fee_contract["status"] == "EXPLICIT_FEE_MODEL"

    if not depth_present:
        status = "ORDERBOOK_DEPTH_REQUIRED"
        eligible = False
        gross_edge_total = net_edge_total = net_edge_per_contract = None
        fee_total = latency_cost_total = None
    elif not full_fill:
        status = "INSUFFICIENT_DEPTH_FOR_TARGET"
        eligible = False
        gross_edge_total = net_edge_total = net_edge_per_contract = None
        fee_total = latency_cost_total = None
    else:
        notional = sum(float(row["notional"]) for row in leg_quotes)
        gross_edge_total = quantity - notional
        fee_total = sum(float(row["fee"]) for row in leg_quotes) if explicit_fees else None
        latency_cost_total = quantity * len(leg_quotes) * (latency_bps / 10000.0)
        if not explicit_fees:
            status = "EXPLICIT_FEE_MODEL_REQUIRED"
            eligible = False
            net_edge_total = net_edge_per_contract = None
        else:
            net_edge_total = gross_edge_total - fee_total - latency_cost_total
            net_edge_per_contract = net_edge_total / quantity
            eligible = net_edge_total > EPS
            status = "PAPER_SIGNAL_AVAILABLE" if eligible else "NO_EDGE_AFTER_DEPTH_FEES_LATENCY"

    return {
        "name": name,
        "target_contracts": quantity,
        "max_complete_quantity_from_current_depth": round(max_complete, 8),
        "full_fill_at_target": full_fill,
        "legs": leg_quotes,
        "gross_edge_total": _rounded(gross_edge_total),
        "fee_total": _rounded(fee_total),
        "latency_buffer_cost_total": _rounded(latency_cost_total),
        "net_edge_total": _rounded(net_edge_total),
        "net_edge_per_contract": _rounded(net_edge_per_contract),
        "status": status,
        "eligible_for_paper_signal": eligible,
    }


def _walk_asks(levels: list, quantity: float) -> dict:
    normalized = []
    for row in levels:
        if isinstance(row, dict):
            price = _optional_number(row.get("price"))
            size = _optional_number(row.get("size"))
        elif isinstance(row, (list, tuple)) and len(row) >= 2:
            price = _optional_number(row[0])
            size = _optional_number(row[1])
        else:
            continue
        if price is None or size is None or size <= 0 or not 0 <= price <= 1:
            continue
        normalized.append((price, size))
    normalized.sort(key=lambda item: item[0])

    available_depth = sum(size for _, size in normalized)
    remaining = quantity
    filled = 0.0
    notional = 0.0
    fills = []
    for price, size in normalized:
        if remaining <= EPS:
            break
        take = min(size, remaining)
        if take <= EPS:
            continue
        fills.append({"price": round(price, 8), "size": round(take, 8)})
        filled += take
        notional += take * price
        remaining -= take

    full_fill = remaining <= EPS
    vwap = notional / filled if filled > EPS else None
    best_ask = normalized[0][0] if normalized else None
    worst_ask = fills[-1]["price"] if fills else None
    slippage = (vwap - best_ask) if vwap is not None and best_ask is not None else None
    return {
        "book_level_count": len(normalized),
        "available_depth": round(available_depth, 8),
        "requested_quantity": quantity,
        "filled_quantity": round(filled, 8),
        "full_fill": full_fill,
        "best_ask": _rounded(best_ask),
        "worst_ask": _rounded(worst_ask),
        "vwap": _rounded(vwap),
        "notional": _rounded(notional),
        "slippage_vs_best_ask": _rounded(slippage),
        "fills": fills,
    }


def _normalize_fee_model(value: dict | None) -> dict:
    if not isinstance(value, dict):
        return {"status": "MISSING_EXPLICIT_FEE_MODEL", "source": None, "providers": {}}
    source = value.get("source")
    if not isinstance(source, str) or not source.strip():
        return {"status": "MISSING_EXPLICIT_FEE_MODEL", "source": None, "providers": {}}

    providers = {}
    for provider in PROVIDERS:
        row = value.get(provider)
        if not isinstance(row, dict):
            return {"status": "MISSING_EXPLICIT_FEE_MODEL", "source": source.strip(), "providers": providers}
        providers[provider] = {
            "fee_rate_on_notional": _non_negative(row.get("fee_rate_on_notional", 0.0), f"{provider}.fee_rate_on_notional"),
            "fee_per_contract": _non_negative(row.get("fee_per_contract", 0.0), f"{provider}.fee_per_contract"),
            "fixed_fee_per_order": _non_negative(row.get("fixed_fee_per_order", 0.0), f"{provider}.fixed_fee_per_order"),
        }
    return {"status": "EXPLICIT_FEE_MODEL", "source": source.strip(), "providers": providers}


def _fee_for_leg(walked: dict, fee: dict | None) -> float | None:
    if fee is None or not walked.get("full_fill"):
        return None
    return (
        float(walked["notional"]) * float(fee["fee_rate_on_notional"])
        + float(walked["filled_quantity"]) * float(fee["fee_per_contract"])
        + float(fee["fixed_fee_per_order"])
    )


def _execution_opportunity(identity: dict, basket: dict, kalshi: dict, polymarket: dict) -> dict:
    key = dumps(
        {
            "identity_id": identity.get("identity_id"),
            "basket": basket,
            "kalshi_market_id": kalshi.get("provider_market_id"),
            "polymarket_market_id": polymarket.get("provider_market_id"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    opportunity_id = "OPP-" + sha256(key.encode("utf-8")).hexdigest()[:16]
    return {
        "artifact_type": "r12_strategy_opportunity",
        "opportunity_id": opportunity_id,
        "strategy_id": "cross_market_event_rv",
        "subtype": "same_event_cross_market_depth_aware_complement_basket",
        "as_of": "LIVE_PUBLIC_ORDERBOOK_DATA",
        "source": "kalshi+polymarket",
        "status": "PAPER_SIGNAL_AVAILABLE",
        "reference_view": {
            "constraint": "verified identical binary settlement => complete YES+NO basket pays 1.0 per matched contract",
            "reference_type": "verified_same_event_complement_constraint",
            "identity_id": identity.get("identity_id"),
        },
        "market_view": {
            "kalshi_market_id": kalshi.get("provider_market_id"),
            "polymarket_market_id": polymarket.get("provider_market_id"),
            "execution_quote": basket,
        },
        "gross_edge": basket["gross_edge_total"],
        "estimated_cost": round(float(basket["fee_total"]) + float(basket["latency_buffer_cost_total"]), 8),
        "net_edge": basket["net_edge_total"],
        "net_edge_per_contract": basket["net_edge_per_contract"],
        "edge_unit": "settlement_currency_per_target_basket",
        "candidate_action": "PAPER_BUY_MATCHED_COMPLEMENT_LEGS_USING_DEPTH_AWARE_QUOTE",
        "settlement_compatibility_verified": True,
        "implementation_verified": True,
        "calibration_status": "EXACT_VERIFIED_COMPLEMENT_REFERENCE_NOT_PROBABILITY_MODEL",
        "payoff_status": "LOCKED_BINARY_PAYOFF_IF_VERIFIED_SETTLEMENT_AND_MODELED_FILLS_HOLD",
        "liquidity_status": "TARGET_QUANTITY_FULLY_COVERED_BY_VISIBLE_BOOK_DEPTH",
        "eligible_for_paper_signal": True,
        "execution_status": "PAPER_SIGNAL_ONLY_NO_AUTO_EXECUTION",
        "guardrails": {
            "top_of_book_size_assumed_sufficient": False,
            "partial_fill_treated_as_locked": False,
            "fees_assumed": False,
            "latency_buffer_calibrated": False,
            "automatic_execution": False,
        },
    }


def _validate_identity(identity: dict, kalshi: dict, polymarket: dict) -> None:
    for provider, contract in (("kalshi", kalshi), ("polymarket", polymarket)):
        if not isinstance(contract, dict) or contract.get("artifact_type") != "r12_market_contract":
            raise ValueError(f"{provider}_contract must be an r12_market_contract")
        if contract.get("provider") != provider:
            raise ValueError(f"expected provider={provider}")
    if not isinstance(identity, dict) or identity.get("artifact_type") != "r12_event_identity":
        raise ValueError("identity must be an r12_event_identity artifact")
    if identity.get("status") != "SETTLEMENT_COMPATIBLE_FOR_RV" or not identity.get("settlement_compatible_for_rv"):
        raise ValueError("depth-aware execution requires SETTLEMENT_COMPATIBLE_FOR_RV")
    expected = {
        "kalshi": kalshi.get("provider_market_id") if isinstance(kalshi, dict) else None,
        "polymarket": polymarket.get("provider_market_id") if isinstance(polymarket, dict) else None,
    }
    actual = {
        key: ((identity.get("contracts") or {}).get(key) or {}).get("provider_market_id")
        for key in PROVIDERS
    }
    if expected != actual:
        raise ValueError("identity artifact does not belong to supplied market contracts")


def _optional_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _positive(value: Any, label: str) -> float:
    number = _non_negative(value, label)
    if number <= 0:
        raise ValueError(f"{label} must be > 0")
    return number


def _non_negative(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not isfinite(number) or number < 0:
        raise ValueError(f"{label} must be finite and >= 0")
    return number


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(float(value), 8)
