"""R12 roadmap projection for the currently implemented strategy layers."""

from copy import deepcopy

from r12_strategy import strategy_registry_snapshot


def current_strategy_registry_snapshot() -> dict:
    registry = deepcopy(strategy_registry_snapshot())
    for row in registry.get("strategies") or []:
        if row.get("strategy_id") == "cross_market_event_rv":
            row["status"] = "LIVE_EXACT_ID_ADAPTER_IDENTITY_GATED"
            row["next_dependency"] = "event discovery + automated rules parser + fee/depth/fill model"
        elif row.get("strategy_id") == "structural_logic_rv":
            row["next_dependency"] = "live market-universe normalizer + liquidity/fee/depth model"
    registry["roadmap_version"] = "R12_STEP2"
    registry["current_boundary"] = (
        "Exact Kalshi ticker and Polymarket market-ID adapters are live-data capable; same-event RV remains "
        "blocked until explicit settlement identity attestation passes."
    )
    return registry
