"""R8 professional decision lenses built on the same grounded S1 evidence.

R8 deliberately separates factual research from decision logic:

    Question -> Evidence -> S1 grounded research -> D1 professional decision lens

Investment asks whether the grounded state creates a pricing/valuation asymmetry.
Policy asks which option best serves policy objectives under counterfactual,
distributional, and implementation constraints.

Neither lens may fetch new data, invent Evidence IDs, or convert the R5 heuristic
support score into a probability.
"""

from __future__ import annotations

from copy import deepcopy

from r6_domain import synthesize_domain_brief


VALID_DOMAINS = {"investment", "policy"}


def synthesize_professional_decision_brief(
    question: str,
    domain: str,
    research_synthesis: dict,
    reference_date: str,
) -> dict:
    if domain not in VALID_DOMAINS:
        raise ValueError("domain must be investment or policy")

    base = synthesize_domain_brief(
        question=question,
        domain=domain,
        research_synthesis=research_synthesis,
        reference_date=reference_date,
    )
    evidence_ids = list(base["evidence_ids"])
    signals = deepcopy(research_synthesis.get("signals") or [])
    pressure = base.get("pressure_state")
    relation_summary = (
        (research_synthesis.get("quality") or {}).get("relation_summary") or {}
    )

    if domain == "investment":
        sections = _investment_decision_sections(
            base=base,
            evidence_ids=evidence_ids,
            signals=signals,
            pressure=pressure,
            relation_summary=relation_summary,
        )
        professional_status = sections["position_framework"]["status"]
    else:
        sections = _policy_decision_sections(
            base=base,
            evidence_ids=evidence_ids,
            signals=signals,
            pressure=pressure,
            relation_summary=relation_summary,
        )
        professional_status = sections["policy_actionability"]["status"]

    enriched = deepcopy(base)
    enriched["answer"] = sections["executive_summary"]
    enriched["sections"] = sections
    enriched["professional_decision_status"] = professional_status
    enriched["decision_framework_version"] = "R8"
    enriched["guardrails"] = {
        **dict(base.get("guardrails") or {}),
        "market_pricing_fabrication": "forbidden",
        "expected_value_without_probability_and_payoff": "forbidden",
        "causal_policy_effect_without_causal_evidence": "forbidden",
        "distributional_claim_without_incidence_evidence": "forbidden",
        "professional_lens_changes_upstream_queries": False,
    }
    return enriched


def _investment_decision_sections(*, base, evidence_ids, signals, pressure, relation_summary):
    market_based_ids = [
        item.get("evidence_id")
        for item in signals
        if isinstance(item, dict)
        and isinstance(item.get("evidence_id"), str)
        and item["evidence_id"].startswith("FRED:")
    ]
    thesis = (base.get("sections") or {}).get("thesis") or base.get("answer")
    contradiction = int(relation_summary.get("contradiction", 0) or 0)
    mixed = int(relation_summary.get("mixed_signal", 0) or 0)

    if contradiction:
        position_status = "RECONCILE_BEFORE_POSITION"
    elif mixed:
        position_status = "NO_POSITION_MIXED_SIGNAL"
    else:
        position_status = "NO_POSITION_MISSING_PRICING"

    bias_map = {
        "inflation_upside_pressure": "WATCH_INFLATION_UPSIDE_EXPOSURES",
        "disinflation_pressure": "WATCH_RATE_RELIEF_EXPOSURES",
        "mixed_inflation_signals": "WATCH_DISPERSION_NOT_MACRO_BETA",
        "insufficient_directional_signal": "NO_DIRECTIONAL_BIAS",
    }

    catalysts = [
        {
            "evidence_id": item.get("evidence_id"),
            "trigger": "next materially new observation or direction reversal",
            "why_it_matters": "can confirm, weaken, or invalidate the current macro thesis",
        }
        for item in signals
        if isinstance(item, dict) and item.get("evidence_id")
    ]

    return {
        "brief_type": "investment_professional_decision_brief",
        "executive_summary": (
            f"Investment lens: {thesis} The macro state is grounded, but a trade is not yet justified "
            f"because current research does not establish a measurable market-pricing gap. "
            f"Position status={position_status}."
        ),
        "thesis": thesis,
        "market_pricing": {
            "status": "PRICING_NOT_MODELED",
            "market_based_expectation_evidence_ids": market_based_ids,
            "interpretation": (
                "Market-based inflation expectations may be observed, but that is not sufficient to infer "
                "the price gap of a specific security, rate path, spread, or portfolio expression."
            ),
            "missing_inputs": [
                "instrument price or yield/spread level",
                "consensus or futures-implied expectation relevant to the trade",
                "valuation or historical reference",
            ],
        },
        "expected_value": {
            "status": "EV_NOT_COMPUTABLE",
            "reason": (
                "Expected value requires calibrated scenario probabilities and payoff magnitudes; "
                "R5 support score is explicitly not a probability."
            ),
            "required_inputs": [
                "calibrated scenario probabilities",
                "payoff by scenario",
                "transaction costs and implementation assumptions",
            ],
        },
        "catalysts": catalysts,
        "position_framework": {
            "status": position_status,
            "research_bias": bias_map.get(pressure, "NO_DIRECTIONAL_BIAS"),
            "position": "NONE",
            "conditions_before_position": [
                "identify a measurable gap between research view and market pricing",
                "define the instrument and valuation reference",
                "define payoff asymmetry and loss limit",
                "resolve same-claim contradiction before taking directional risk",
            ],
        },
        "risk_map": {
            "thesis_risk": "new Evidence reverses or contradicts the grounded macro thesis",
            "pricing_risk": "the thesis is correct but already fully reflected in market prices",
            "timing_risk": "repricing occurs outside the intended horizon",
            "implementation_risk": "liquidity, carry, convexity, basis, and transaction costs are not modeled",
        },
        "counterevidence": deepcopy(base.get("counterevidence") or []),
        "falsifiers": list((base.get("sections") or {}).get("what_would_change_the_view") or []),
        "monitoring_signals": deepcopy(base.get("monitoring") or []),
        "limitations": [
            "No security-specific price, valuation, positioning, liquidity, or portfolio constraints are included.",
            "No expected-value number is produced without calibrated probabilities and payoffs.",
            "This is a research decision framework, not an individualized trade recommendation.",
        ],
    }


def _policy_decision_sections(*, base, evidence_ids, signals, pressure, relation_summary):
    contradiction = int(relation_summary.get("contradiction", 0) or 0)
    posture = (base.get("sections") or {}).get("evidence_posture") or "monitor"
    if contradiction:
        actionability = "RECONCILE_BEFORE_POLICY_ANALYSIS"
    else:
        actionability = "MONITOR_ONLY_MISSING_CAUSAL_AND_IMPLEMENTATION_EVIDENCE"

    option_analysis = [
        {
            "option": "maintain_current_policy_posture",
            "objective": "avoid overreacting to noisy or incomplete inflation signals",
            "potential_benefit": "preserves optionality while new Evidence arrives",
            "potential_cost": "persistent inflation or disinflation may be recognized too slowly",
            "causal_effect_estimate": "NOT_MODELED",
            "reversibility": "high",
        },
        {
            "option": "increase_inflation_risk_attention",
            "objective": "respond faster if inflation pressure becomes persistent",
            "potential_benefit": "reduces risk of underreacting to renewed inflation pressure",
            "potential_cost": "may overweight temporary or energy-driven inflation noise",
            "causal_effect_estimate": "NOT_MODELED",
            "reversibility": "medium",
        },
        {
            "option": "increase_disinflation_risk_attention",
            "objective": "respond faster if restrictive conditions are becoming unnecessarily costly",
            "potential_benefit": "reduces risk of staying restrictive after inflation pressure fades",
            "potential_cost": "may loosen attention before underlying inflation persistence is resolved",
            "causal_effect_estimate": "NOT_MODELED",
            "reversibility": "medium",
        },
    ]

    counterfactuals = [
        {
            "counterfactual": "NO_ACTION_BASELINE",
            "question": "What happens if the current policy posture is maintained while the next Evidence arrives?",
            "outcome_estimate": "NOT_MODELED",
        },
        {
            "counterfactual": "MORE_INFLATION_ATTENTION",
            "question": "How would inflation, activity, employment, and financial conditions differ under a more restrictive posture?",
            "outcome_estimate": "NOT_MODELED",
        },
        {
            "counterfactual": "MORE_DISINFLATION_ATTENTION",
            "question": "How would inflation, activity, employment, and financial conditions differ under an earlier easing posture?",
            "outcome_estimate": "NOT_MODELED",
        },
    ]

    return {
        "brief_type": "policy_professional_decision_brief",
        "executive_summary": (
            f"Policy lens: evidence posture={posture}. The current Evidence can frame monitoring and options, "
            f"but it cannot support a causal policy directive without labor-market, financial-condition, "
            f"distributional, and implementation evidence. Actionability={actionability}."
        ),
        "policy_problem": (base.get("sections") or {}).get("policy_problem"),
        "evidence_posture": posture,
        "no_action_baseline": {
            "posture": "maintain_current_policy_posture_and_monitor",
            "rationale": "preserve optionality until cross-source confirmation or contradiction resolution",
            "causal_outcome_estimate": "NOT_MODELED",
        },
        "option_analysis": option_analysis,
        "counterfactual_analysis": {
            "status": "COUNTERFACTUAL_EFFECTS_NOT_ESTIMATED",
            "scenarios": counterfactuals,
            "required_for_causal_comparison": [
                "policy reaction function or identified causal model",
                "labor-market and output-gap conditions",
                "financial conditions / credit transmission",
                "relevant fiscal and supply-side conditions",
            ],
        },
        "distributional_analysis": {
            "status": "INCIDENCE_NOT_MODELED",
            "dimensions_to_analyze": [
                "households by income and balance-sheet exposure",
                "borrowers versus savers",
                "labor-market groups with different unemployment sensitivity",
                "firms by financing dependence and pricing power",
            ],
            "claim_rule": "do not claim who gains or loses without incidence evidence",
        },
        "implementation": {
            "status": "NOT_READY_FOR_DIRECTIVE",
            "missing_inputs": [
                "specific policy instrument and authority",
                "implementation lag and operational constraints",
                "legal / institutional constraints where relevant",
                "exit and reversal conditions",
            ],
        },
        "policy_actionability": {
            "status": actionability,
            "current_action": "MONITOR_AND_UPDATE_EVIDENCE",
        },
        "counterevidence": deepcopy(base.get("counterevidence") or []),
        "falsifiers": list((base.get("sections") or {}).get("what_would_change_the_view") or []),
        "monitoring_signals": deepcopy(base.get("monitoring") or []),
        "limitations": [
            "No causal policy effect is estimated from the current descriptive Evidence bundle.",
            "No distributional incidence claim is made without dedicated evidence.",
            "No direct policy instruction is issued without implementation and institutional analysis.",
        ],
    }
