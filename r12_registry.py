"""R12 roadmap projection for the currently implemented strategy layers."""

from copy import deepcopy

from r12_strategy import strategy_registry_snapshot


def current_strategy_registry_snapshot() -> dict:
    registry = deepcopy(strategy_registry_snapshot())
    for row in registry.get("strategies") or []:
        if row.get("strategy_id") == "cross_market_event_rv":
            row["status"] = "LIVE_DISCOVERY_IDENTITY_GATED"
            row["next_dependency"] = "rules parser + full depth/fees/partial-fill/latency model"
        elif row.get("strategy_id") == "structural_logic_rv":
            row["next_dependency"] = "live market-universe normalizer + liquidity/fee/depth model"
    registry["roadmap_version"] = "R12_STEP3"
    registry["current_boundary"] = (
        "Free-text discovery can find candidate Kalshi and Polymarket markets without raw IDs. Candidate matching is "
        "lexical and never proves settlement identity; exact contracts still require explicit rules attestation before RV."
    )
    registry["discovery_contract"] = {
        "kalshi": "bounded open-event listing plus local lexical ranking",
        "polymarket": "public-search plus bounded event expansion",
        "candidate_match_is_settlement_proof": False,
    }
    return registry
