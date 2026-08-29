"""R3 synthesis for a variable set of approved source queries.

This module consumes collected Evidence outputs, not source names hardcoded into
one four-input function. It emits descriptive signals only and preserves the
Evidence IDs required for citation verification.
"""

from __future__ import annotations

import calendar
from datetime import date


def synthesize_research_bundle(question: str, evidence_bundle: list[dict], reference_date: str) -> dict:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")
    if not isinstance(evidence_bundle, list) or not evidence_bundle:
        raise ValueError("evidence_bundle must be a non-empty list")
    reference = date.fromisoformat(reference_date)

    evidence_ids = []
    signals = []
    freshness = {}
    confidences = []

    for item in evidence_bundle:
        if not isinstance(item, dict) or item.get("kind") != "evidence":
            raise ValueError("every evidence_bundle item must be an Evidence record")
        evidence_id = item.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id:
            raise ValueError("Evidence record is missing evidence_id")
        evidence_ids.append(evidence_id)
        confidences.append(float(item.get("confidence", 1.0)))
        freshness[evidence_id] = _freshness(item.get("as_of"), reference)
        signals.append(_signal(item))

    summary_parts = []
    for signal in signals:
        if signal["kind"] == "yoy":
            summary_parts.append(
                f"{signal['evidence_id']} YoY={signal['yoy_pct']:.2f}%"
            )
        elif signal["kind"] == "change":
            summary_parts.append(
                f"{signal['evidence_id']} change={signal['change']:+.4f} ({signal['direction']})"
            )
        else:
            summary_parts.append(
                f"{signal['evidence_id']} latest={signal.get('latest_value')}"
            )

    answer = (
        f"Research question: {question} "
        + " | ".join(summary_parts)
        + ". These are descriptive cross-source signals and not causal attribution."
    )

    return {
        "kind": "synthesis",
        "answer": answer,
        "value": float(len(evidence_ids)),
        "unit": "evidence_records",
        "confidence": min(confidences) if confidences else 0.0,
        "evidence_ids": evidence_ids,
        "signals": signals,
        "freshness": freshness,
        "limitations": [
            "Different sources publish on different calendars and frequencies.",
            "Cross-source co-movement is descriptive and not causal attribution.",
            "This R3 teaching synthesizer does not estimate causal contribution or forecast error bands.",
        ],
    }


def _signal(item: dict) -> dict:
    evidence_id = item["evidence_id"]
    history = item.get("history") or []
    latest_value = item.get("value")

    if evidence_id.startswith("BLS:"):
        yoy = _bls_yoy(history)
        if yoy is not None:
            return {
                "evidence_id": evidence_id,
                "kind": "yoy",
                "latest_value": latest_value,
                "yoy_pct": yoy,
            }

    if len(history) >= 2:
        previous = _history_value(history[-2])
        latest = _history_value(history[-1])
        if previous is not None and latest is not None:
            change = round(latest - previous, 6)
            return {
                "evidence_id": evidence_id,
                "kind": "change",
                "latest_value": latest,
                "previous_value": previous,
                "change": change,
                "direction": "rising" if change > 0 else "falling" if change < 0 else "flat",
            }

    return {
        "evidence_id": evidence_id,
        "kind": "level",
        "latest_value": latest_value,
    }


def _bls_yoy(history: list[dict]) -> float | None:
    if not history:
        return None
    latest = history[-1]
    year = latest.get("year")
    month = latest.get("month")
    latest_value = _history_value(latest)
    if not isinstance(year, int) or not isinstance(month, int) or latest_value is None:
        return None
    prior = next(
        (
            row
            for row in history
            if row.get("year") == year - 1 and row.get("month") == month
        ),
        None,
    )
    prior_value = _history_value(prior) if prior else None
    if prior_value in {None, 0}:
        return None
    return round((latest_value / prior_value - 1) * 100, 4)


def _history_value(row) -> float | None:
    if not isinstance(row, dict):
        return None
    try:
        return float(row.get("value"))
    except (TypeError, ValueError):
        return None


def _freshness(as_of, reference: date) -> dict:
    if not isinstance(as_of, str) or not as_of:
        return {"status": "unknown", "age_days": None, "as_of": as_of}
    try:
        if len(as_of) == 7:
            year, month = [int(part) for part in as_of.split("-")]
            observed = date(year, month, calendar.monthrange(year, month)[1])
        else:
            observed = date.fromisoformat(as_of[:10])
    except (ValueError, TypeError):
        return {"status": "unknown", "age_days": None, "as_of": as_of}

    age = max((reference - observed).days, 0)
    status = "fresh" if age <= 45 else "aging" if age <= 90 else "stale"
    return {"status": status, "age_days": age, "as_of": as_of}
