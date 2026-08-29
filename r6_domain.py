"""R6 domain synthesis: translate grounded research into decision-oriented briefs.

R5 decides what the Evidence supports. R6 applies an explicit domain lens to that
already-grounded synthesis. It must not fetch new data, invent new evidence IDs,
or increase upstream confidence. Scenario framing is qualitative, not a
probability forecast and not individualized investment/policy advice.
"""

from __future__ import annotations

from copy import deepcopy


VALID_DOMAINS = {"investment", "policy"}


def synthesize_domain_brief(
    question: str,
    domain: str,
    research_synthesis: dict,
    reference_date: str,
) -> dict:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")
    if domain not in VALID_DOMAINS:
        raise ValueError(f"domain must be one of: {', '.join(sorted(VALID_DOMAINS))}")
    if not isinstance(research_synthesis, dict) or research_synthesis.get("kind") != "synthesis":
        raise ValueError("research_synthesis must be a grounded synthesis object")

    evidence_ids = list(research_synthesis.get("evidence_ids") or [])
    if not evidence_ids or not all(isinstance(item, str) and item for item in evidence_ids):
        raise ValueError("research_synthesis must contain non-empty evidence_ids")

    upstream_confidence = float(research_synthesis.get("confidence", 0.0))
    quality = deepcopy(research_synthesis.get("quality") or {})
    signals = deepcopy(research_synthesis.get("signals") or [])
    relation_summary = quality.get("relation_summary") or {
        "agreement": 0,
        "mixed_signal": 0,
        "contradiction": 0,
    }

    pressure = _pressure_state(signals)
    decision_status = _decision_status(upstream_confidence, relation_summary)
    counterevidence = _counterevidence(signals, pressure)
    monitoring = _monitoring(signals)

    if domain == "investment":
        brief = _investment_brief(
            question=question,
            pressure=pressure,
            decision_status=decision_status,
            counterevidence=counterevidence,
            monitoring=monitoring,
            relation_summary=relation_summary,
        )
    else:
        brief = _policy_brief(
            question=question,
            pressure=pressure,
            decision_status=decision_status,
            counterevidence=counterevidence,
            monitoring=monitoring,
            relation_summary=relation_summary,
        )

    return {
        "kind": "synthesis",
        "domain": domain,
        "answer": brief["executive_summary"],
        "value": upstream_confidence,
        "unit": "heuristic_support_score",
        "confidence": upstream_confidence,
        "confidence_type": research_synthesis.get(
            "confidence_type", "heuristic_support_score_not_probability"
        ),
        "evidence_ids": evidence_ids,
        "reference_date": reference_date,
        "decision_status": decision_status,
        "pressure_state": pressure,
        "sections": brief,
        "counterevidence": counterevidence,
        "monitoring": monitoring,
        "upstream": {
            "research_answer": research_synthesis.get("answer"),
            "quality": quality,
            "limitations": list(research_synthesis.get("limitations") or []),
        },
        "guardrails": {
            "new_data_fetches": 0,
            "confidence_increased": False,
            "scenario_weighting": "qualitative_not_probability",
            "factual_claims_must_trace_to_upstream_evidence": True,
        },
    }


def _pressure_state(signals: list[dict]) -> str:
    directions = [
        item.get("direction")
        for item in signals
        if isinstance(item, dict) and item.get("direction") in {"rising", "falling"}
    ]
    rising = directions.count("rising")
    falling = directions.count("falling")
    if rising and not falling:
        return "inflation_upside_pressure"
    if falling and not rising:
        return "disinflation_pressure"
    if rising and falling:
        return "mixed_inflation_signals"
    return "insufficient_directional_signal"


def _decision_status(confidence: float, relation_summary: dict) -> str:
    contradiction = int(relation_summary.get("contradiction", 0) or 0)
    mixed = int(relation_summary.get("mixed_signal", 0) or 0)
    if contradiction:
        return "RECONCILE_BEFORE_ACTION"
    if confidence < 0.65:
        return "INSUFFICIENT_SUPPORT"
    if mixed:
        return "MONITOR_MIXED_SIGNAL"
    if confidence >= 0.85:
        return "RESEARCH_READY"
    return "MONITOR_BEFORE_ACTION"


def _counterevidence(signals: list[dict], pressure: str) -> list[dict]:
    if pressure not in {"inflation_upside_pressure", "disinflation_pressure"}:
        return [
            {
                "type": "mixed_or_unknown",
                "detail": "The Evidence bundle does not support a single directional narrative.",
                "evidence_ids": [
                    item.get("evidence_id")
                    for item in signals
                    if isinstance(item, dict) and item.get("evidence_id")
                ],
            }
        ]

    opposing = "falling" if pressure == "inflation_upside_pressure" else "rising"
    rows = [
        {
            "type": "opposing_signal",
            "detail": f"{item.get('evidence_id')} points {opposing} against the dominant direction.",
            "evidence_ids": [item.get("evidence_id")],
        }
        for item in signals
        if isinstance(item, dict) and item.get("direction") == opposing
    ]
    return rows or [
        {
            "type": "missing_counterevidence",
            "detail": "No opposing directional signal exists in the current Evidence bundle; seek independent disconfirming evidence before increasing conviction.",
            "evidence_ids": [],
        }
    ]


def _monitoring(signals: list[dict]) -> list[dict]:
    rows = []
    for item in signals:
        if not isinstance(item, dict) or not item.get("evidence_id"):
            continue
        rows.append(
            {
                "evidence_id": item["evidence_id"],
                "current_direction": item.get("direction", "unknown"),
                "watch_for": "direction reversal, persistence, or a materially different next observation",
            }
        )
    return rows


def _investment_brief(
    *, question, pressure, decision_status, counterevidence, monitoring, relation_summary
) -> dict:
    channel_map = {
        "inflation_upside_pressure": [
            "rate-sensitive valuation risk",
            "duration sensitivity",
            "pricing-power dispersion",
        ],
        "disinflation_pressure": [
            "rate-relief sensitivity",
            "duration sensitivity",
            "margin-versus-demand differentiation",
        ],
        "mixed_inflation_signals": [
            "cross-asset dispersion",
            "rate-path uncertainty",
            "sector-specific sensitivity rather than one macro beta",
        ],
        "insufficient_directional_signal": [
            "avoid forcing a directional macro exposure from this Evidence bundle",
        ],
    }
    thesis = {
        "inflation_upside_pressure": "The current grounded indicators lean toward renewed inflation pressure.",
        "disinflation_pressure": "The current grounded indicators lean toward continued disinflation pressure.",
        "mixed_inflation_signals": "The current grounded indicators are mixed and do not support one clean inflation trade narrative.",
        "insufficient_directional_signal": "The current grounded indicators do not provide enough directional information for a macro thesis.",
    }[pressure]
    return {
        "brief_type": "investment_research_brief",
        "executive_summary": (
            f"Investment research lens: {thesis} Decision status={decision_status}. "
            "Use this as a macro risk framework, not an individualized trade recommendation."
        ),
        "thesis": thesis,
        "market_channels": channel_map[pressure],
        "base_case": {
            "description": "Current directional mix persists until the next meaningful data update.",
            "weighting": "qualitative",
        },
        "upside_inflation_scenario": {
            "trigger": "realized inflation and/or expectations turn persistently higher across subsequent Evidence updates",
            "implication": "treat inflation-sensitive rate and valuation channels as the dominant macro risk",
            "weighting": "qualitative",
        },
        "downside_inflation_scenario": {
            "trigger": "realized inflation and high-frequency/expectations signals turn persistently lower",
            "implication": "treat disinflation and rate-relief channels as the dominant macro risk",
            "weighting": "qualitative",
        },
        "counterevidence": counterevidence,
        "what_would_change_the_view": [
            "a persistent reversal in the directional signals currently driving the thesis",
            "a new contradiction on the same comparable claim",
            "material deterioration in Evidence freshness or quality",
        ],
        "monitoring_signals": monitoring,
        "relation_summary": dict(relation_summary),
        "limitations": [
            "No security-specific valuation, positioning, liquidity, or portfolio constraints are modeled.",
            "Scenario weighting is qualitative and is not a calibrated probability forecast.",
        ],
    }


def _policy_brief(
    *, question, pressure, decision_status, counterevidence, monitoring, relation_summary
) -> dict:
    posture = {
        "inflation_upside_pressure": "inflation_risk_watch",
        "disinflation_pressure": "disinflation_watch",
        "mixed_inflation_signals": "wait_for_cross-signal_confirmation",
        "insufficient_directional_signal": "insufficient_evidence_for_directional_posture",
    }[pressure]
    return {
        "brief_type": "policy_research_brief",
        "executive_summary": (
            f"Policy research lens: posture={posture}; decision status={decision_status}. "
            "The brief frames evidence and tradeoffs rather than issuing a policy directive."
        ),
        "policy_problem": "How should the observed inflation signal change the intensity of policy monitoring?",
        "evidence_posture": posture,
        "options": [
            {
                "option": "hold_current_posture_and_monitor",
                "when": "signals are mixed, confidence is limited, or confirmation is still needed",
            },
            {
                "option": "increase_inflation_risk_attention",
                "when": "realized inflation and expectations/energy signals persistently strengthen",
            },
            {
                "option": "increase_disinflation_risk_attention",
                "when": "realized inflation and complementary signals persistently weaken",
            },
        ],
        "tradeoffs": [
            "reacting too quickly to a noisy signal versus reacting too slowly to a persistent shift",
            "placing weight on realized inflation versus forward-looking and high-frequency indicators",
        ],
        "counterevidence": counterevidence,
        "what_would_change_the_view": [
            "persistent cross-source confirmation in the opposite direction",
            "a contradiction on the same comparable claim that requires reconciliation",
            "material change in Evidence freshness, coverage, or source quality",
        ],
        "monitoring_signals": monitoring,
        "relation_summary": dict(relation_summary),
        "limitations": [
            "This brief does not model a full policy reaction function, labor-market slack, fiscal transmission, or distributional incidence.",
            "Scenario framing is qualitative and is not a calibrated probability forecast.",
        ],
    }
