"""R12 roadmap projection for the currently implemented strategy layers."""

from copy import deepcopy

from r12_strategy import strategy_registry_snapshot


def current_strategy_registry_snapshot() -> dict:
    registry = deepcopy(strategy_registry_snapshot())
    for row in registry.get("strategies") or []:
        if row.get("strategy_id") == "cross_market_event_rv":
            row["status"] = "LIVE_HITL_AGENT_WITH_APPEND_ONLY_PAPER_LEDGER"
            row["next_dependency"] = "paper portfolio aggregation + multi-trade exposure limits"
        elif row.get("strategy_id") == "structural_logic_rv":
            row["next_dependency"] = "live market-universe normalizer + liquidity/fee/depth model"
    registry["roadmap_version"] = "R12_STEP8"
    registry["current_boundary"] = (
        "Free-text discovery can find candidate Kalshi and Polymarket markets without raw IDs. Candidate matching is "
        "lexical and never proves settlement identity. An exact-pair Tool DAG now persists a human approval pause; "
        "only a rules-analysis-bound six-check attestation can resume identity, RV, and depth-aware paper quoting. "
        "An eligible E1 quote can then create a zero-fill paper intent; explicit idempotent commands append simulated "
        "fills, marks, cancellation/expiry, and settlement to a replayable hash-chained ledger. The operator UI now "
        "separates the default end-to-end Agent Run from the step-by-step Manual Lab and the Strategy Roadmap."
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
    registry["rules_analysis_contract"] = {
        "deterministic_extraction": True,
        "contract_fingerprint_bound": True,
        "required_before_identity_review": True,
        "parser_can_auto_approve_identity": False,
        "human_attestation_still_required": True,
    }
    registry["strategy_agent_contract"] = {
        "shared_agent_runtime_tool_boundary": True,
        "explicit_plan_dag": True,
        "durable_human_approval_pause": True,
        "resume_skips_durably_completed_tasks": True,
        "task_level_trace_and_eval": True,
        "automatic_execution": False,
    }
    registry["paper_ledger_contract"] = {
        "e1_quote_is_a_fill": False,
        "paper_intent_starts_with_zero_fills": True,
        "mutations_require_idempotency_key": True,
        "append_only_hash_chained_events": True,
        "partial_leg_risk_is_explicit": True,
        "mark_to_market_and_settlement_pnl_replayable": True,
        "exchange_connection_present": False,
        "automatic_execution": False,
    }
    registry["operator_workspace_contract"] = {
        "default_workspace": "agent_run",
        "agent_run_is_linear": True,
        "manual_tool_controls_are_separate": True,
        "strategy_roadmap_is_separate": True,
        "backend_risk_and_ledger_contracts_changed": False,
    }
    return registry
