"""R5 evidence quality and source-relation assessment.

Scores in this module are deterministic teaching heuristics, not calibrated
probabilities of truth. The goal is to make support quality inspectable before
an Agent turns Evidence into a research conclusion.
"""

from __future__ import annotations

import calendar
from datetime import date
from statistics import mean

from r4_source_health import FRESH_DAYS


SOURCE_AUTHORITY = {
    "BLS": 1.0,
    "FRED": 1.0,
    "EIA": 1.0,
}

SERIES_SEMANTICS = {
    "BLS:CUSR0000SA0": {"claim_key": "headline_cpi", "role": "realized_inflation"},
    "BLS:CUSR0000SA0L1E": {"claim_key": "core_cpi", "role": "realized_inflation"},
    "FRED:T5YIE": {"claim_key": "breakeven_5y", "role": "inflation_expectations"},
    "EIA:EMM_EPMR_PTE_NUS_DPG": {"claim_key": "regular_gasoline", "role": "energy_price"},
}

WEIGHTS = {
    "authority": 0.35,
    "freshness": 0.30,
    "completeness": 0.20,
    "relevance": 0.15,
}


def assess_evidence_quality(
    evidence_bundle: list[dict],
    signals: list[dict],
    reference_date: str,
) -> dict:
    """Score Evidence and identify agreement/mixed/contradictory relationships."""
    reference = date.fromisoformat(reference_date)
    signal_by_id = {
        item.get("evidence_id"): item
        for item in signals
        if isinstance(item, dict) and item.get("evidence_id")
    }

    quality_rows = [
        _score_one(item, signal_by_id.get(item.get("evidence_id"), {}), reference)
        for item in evidence_bundle
    ]
    relations = _relations(evidence_bundle, signal_by_id)

    base_score = mean(row["quality_score"] for row in quality_rows) if quality_rows else 0.0
    mixed_count = sum(1 for item in relations if item["relation"] == "MIXED_SIGNAL")
    contradiction_count = sum(1 for item in relations if item["relation"] == "CONTRADICTION")

    mixed_penalty = min(0.12, mixed_count * 0.06)
    contradiction_penalty = min(0.40, contradiction_count * 0.20)
    support_score = round(max(0.0, min(1.0, base_score - mixed_penalty - contradiction_penalty)), 3)

    return {
        "score_type": "heuristic_support_score_not_probability",
        "base_quality_score": round(base_score, 3),
        "support_score": support_score,
        "support_label": _label(support_score),
        "evidence_quality": quality_rows,
        "relations": relations,
        "relation_summary": {
            "agreement": sum(1 for item in relations if item["relation"] == "AGREEMENT"),
            "mixed_signal": mixed_count,
            "contradiction": contradiction_count,
        },
        "penalties": {
            "mixed_signal": round(mixed_penalty, 3),
            "contradiction": round(contradiction_penalty, 3),
        },
        "notes": [
            "Quality/support scores are transparent teaching heuristics, not calibrated truth probabilities.",
            "MIXED_SIGNAL means different indicators point in different directions; it does not mean either source is wrong.",
            "CONTRADICTION requires Evidence addressing the same claim key with opposing directional conclusions.",
        ],
    }


def _score_one(item: dict, signal: dict, reference: date) -> dict:
    if not isinstance(item, dict):
        raise ValueError("quality assessment requires Evidence objects")
    evidence_id = str(item.get("evidence_id") or "")
    provider = _provider(item)
    semantics = SERIES_SEMANTICS.get(evidence_id, {})

    authority = SOURCE_AUTHORITY.get(provider, 0.60)
    freshness, age_days, freshness_status = _freshness_component(
        provider, item.get("as_of"), reference
    )
    history = item.get("history")
    history_count = len(history) if isinstance(history, list) else 0
    required_history = 13 if provider == "BLS" else 2
    completeness = 1.0 if history_count >= required_history else 0.75 if history_count else 0.40
    relevance = 1.0 if semantics else 0.70

    score = round(
        authority * WEIGHTS["authority"]
        + freshness * WEIGHTS["freshness"]
        + completeness * WEIGHTS["completeness"]
        + relevance * WEIGHTS["relevance"],
        3,
    )

    return {
        "evidence_id": evidence_id,
        "provider": provider,
        "claim_key": item.get("claim_key") or semantics.get("claim_key") or evidence_id,
        "role": item.get("role") or semantics.get("role") or "unknown",
        "direction": _direction(item, signal),
        "quality_score": score,
        "quality_label": _label(score),
        "dimensions": {
            "authority": authority,
            "freshness": freshness,
            "completeness": completeness,
            "relevance": relevance,
        },
        "freshness": {
            "status": freshness_status,
            "age_days": age_days,
            "as_of": item.get("as_of"),
        },
        "history_count": history_count,
    }


def _relations(evidence_bundle: list[dict], signal_by_id: dict[str, dict]) -> list[dict]:
    rows = []
    by_claim: dict[str, list[dict]] = {}
    directional = []

    for item in evidence_bundle:
        evidence_id = str(item.get("evidence_id") or "")
        semantics = SERIES_SEMANTICS.get(evidence_id, {})
        row = {
            "evidence_id": evidence_id,
            "claim_key": item.get("claim_key") or semantics.get("claim_key") or evidence_id,
            "role": item.get("role") or semantics.get("role") or "unknown",
            "direction": _direction(item, signal_by_id.get(evidence_id, {})),
        }
        by_claim.setdefault(row["claim_key"], []).append(row)
        if row["direction"] in {"rising", "falling"}:
            directional.append(row)

    contradictory_pairs = set()
    for claim_key, group in by_claim.items():
        if len(group) < 2:
            continue
        rising = [item for item in group if item["direction"] == "rising"]
        falling = [item for item in group if item["direction"] == "falling"]
        if rising and falling:
            ids = sorted(item["evidence_id"] for item in group)
            contradictory_pairs.update(ids)
            rows.append(
                {
                    "relation": "CONTRADICTION",
                    "claim_key": claim_key,
                    "evidence_ids": ids,
                    "detail": "Comparable Evidence for the same claim key points in opposite directions.",
                }
            )
        else:
            directions = {item["direction"] for item in group if item["direction"] != "unknown"}
            if len(directions) == 1 and directions:
                rows.append(
                    {
                        "relation": "AGREEMENT",
                        "claim_key": claim_key,
                        "evidence_ids": sorted(item["evidence_id"] for item in group),
                        "detail": "Comparable Evidence for the same claim key points in the same direction.",
                    }
                )

    rising_ids = [item["evidence_id"] for item in directional if item["direction"] == "rising"]
    falling_ids = [item["evidence_id"] for item in directional if item["direction"] == "falling"]
    if rising_ids and falling_ids:
        mixed_ids = sorted(set(rising_ids + falling_ids) - contradictory_pairs)
        if len(mixed_ids) >= 2:
            rows.append(
                {
                    "relation": "MIXED_SIGNAL",
                    "claim_key": "cross_indicator_direction",
                    "evidence_ids": mixed_ids,
                    "detail": "Different indicators point in different directions; this is uncertainty, not source contradiction.",
                }
            )

    return rows


def _direction(item: dict, signal: dict) -> str:
    explicit = item.get("direction") or item.get("direction_override")
    if explicit in {"rising", "falling", "flat", "unknown"}:
        return explicit
    direction = signal.get("direction") if isinstance(signal, dict) else None
    return direction if direction in {"rising", "falling", "flat"} else "unknown"


def _provider(item: dict) -> str:
    provider = item.get("provider")
    if isinstance(provider, str) and provider:
        return provider.upper()
    evidence_id = str(item.get("evidence_id") or "")
    return evidence_id.split(":", 1)[0].upper() if ":" in evidence_id else "UNKNOWN"


def _freshness_component(provider: str, as_of, reference: date) -> tuple[float, int | None, str]:
    age_days = _age_days(as_of, reference)
    if age_days is None:
        return 0.50, None, "unknown"
    threshold = FRESH_DAYS.get(provider, 45)
    if age_days <= threshold:
        return 1.0, age_days, "fresh"
    if age_days <= threshold * 2:
        return 0.70, age_days, "aging"
    return 0.35, age_days, "stale"


def _age_days(as_of, reference: date) -> int | None:
    if not isinstance(as_of, str) or not as_of:
        return None
    try:
        if len(as_of) == 7:
            year, month = (int(part) for part in as_of.split("-"))
            observed = date(year, month, calendar.monthrange(year, month)[1])
        else:
            observed = date.fromisoformat(as_of[:10])
    except (TypeError, ValueError):
        return None
    return max(0, (reference - observed).days)


def _label(score: float) -> str:
    if score >= 0.85:
        return "HIGH"
    if score >= 0.65:
        return "MEDIUM"
    return "LOW"
