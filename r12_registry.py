"""R12 roadmap projection for the currently implemented strategy layers."""

from copy import deepcopy

from r12_strategy import strategy_registry_snapshot


def current_strategy_registry_snapshot() -> dict:
    registry = deepcopy(strategy_registry_snapshot())
    for row in registry.get("strategies") or []:
        if row.get("strategy_id") == "cross_market_event_rv":
            row["status"] = "LIVE_DEPTH_EXECUTION_QUOTE_IDENTITY_GATED"
            row["next_dependency"] = "rules parser + paper-fill accounting + realized paper P&L"
        elif row.get("strategy_id") == "structural_logic_rv":
            row["next_dependency"] = "live market-universe normalizer + liquidity/fee/depth model"
    registry["roadmap_version"] = "R12_STEP4"
    registry["current_boundary"] = (
        "Free-text discovery can find candidate Kalshi and Polymarket markets without raw IDs. Candidate matching is "
        "lexical and never proves settlement identity; exact contracts still require explicit rules attestation before "
        "a depth-aware target quote can emit a paper signal."
    )
    registry["discovery_contract"] = {
        "kalshi": "bounded open-event listing plus local lexical ranking",
        "polymarket": "public-search plus bounded event expansion",
        "candidate_match_is_settlement_proof": False,
    }
    registry["execution_quote_contract"] = {
        "visible_orderbook_depth_walked": True,
        "target_quantity_must_fill_on_both_legs": True,
        "explicit_provider_fee_model_required": True,
        "latency_buffer_is_user_supplied_not_calibrated": True,
        "automatic_execution": False,
    }
    return registry
