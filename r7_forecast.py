"""R7 forecast contracts, resolution, and durable local tracking.

R6 creates a grounded decision brief. R7 converts already-grounded signals into
explicit, falsifiable forecast contracts. Forecasts are deterministic teaching
baselines, not calibrated probabilities and not trading recommendations.

The important contract is:

    Evidence -> S1 research synthesis -> D1 domain brief -> F1 forecast pack

F1 cannot fetch new data, invent Evidence IDs, or raise upstream confidence.
Forecast settlement happens later against a fresh S1 research synthesis.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path


PROVIDER_HORIZON_DAYS = {
    "BLS": 45,   # monthly publication cadence + buffer
    "FRED": 7,   # market series: short monitoring horizon
    "EIA": 14,   # weekly series + buffer
}

METRIC_TOLERANCE = {
    "BLS": 0.05,   # percentage points for YoY CPI trend comparison
    "FRED": 0.02,  # percentage points for breakeven level comparison
    "EIA": 0.02,   # dollars/gallon for gasoline level comparison
}

VALID_FORECAST_STATUS = {"OPEN", "ABSTAINED", "RESOLVED"}
PACK_ID_RE = re.compile(r"^FP-[A-F0-9]{12}$")


def create_forecast_pack(
    question: str,
    domain: str,
    research_synthesis: dict,
    domain_brief: dict,
    reference_date: str,
) -> dict:
    """Create falsifiable directional forecasts from a grounded R6 run."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")
    if domain not in {"investment", "policy"}:
        raise ValueError("domain must be investment or policy")
    if not isinstance(research_synthesis, dict) or research_synthesis.get("kind") != "synthesis":
        raise ValueError("research_synthesis must be a grounded synthesis object")
    if not isinstance(domain_brief, dict) or domain_brief.get("kind") != "synthesis":
        raise ValueError("domain_brief must be a grounded domain synthesis object")
    if domain_brief.get("domain") != domain:
        raise ValueError("domain_brief domain must match requested domain")

    created = date.fromisoformat(reference_date)
    evidence_ids = list(research_synthesis.get("evidence_ids") or [])
    if not evidence_ids:
        raise ValueError("research_synthesis must contain evidence_ids")
    if list(domain_brief.get("evidence_ids") or []) != evidence_ids:
        raise ValueError("domain_brief must inherit the same Evidence IDs as research_synthesis")

    upstream_confidence = min(
        float(research_synthesis.get("confidence", 0.0)),
        float(domain_brief.get("confidence", 0.0)),
    )
    confidence_type = research_synthesis.get(
        "confidence_type", "heuristic_support_score_not_probability"
    )
    signals = deepcopy(research_synthesis.get("signals") or [])
    quality = deepcopy(research_synthesis.get("quality") or {})
    freshness = deepcopy(research_synthesis.get("freshness") or {})
    quality_by_id = {
        row.get("evidence_id"): row
        for row in quality.get("evidence_quality") or []
        if isinstance(row, dict) and row.get("evidence_id")
    }
    contradicted_ids = _contradicted_evidence_ids(quality)

    forecasts = []
    for index, signal in enumerate(signals, start=1):
        if not isinstance(signal, dict) or not signal.get("evidence_id"):
            continue
        evidence_id = signal["evidence_id"]
        provider = _provider(evidence_id)
        direction = signal.get("direction", "unknown")
        baseline_metric, target_metric = _baseline_metric(signal)
        baseline_as_of = (freshness.get(evidence_id) or {}).get("as_of")
        quality_score = float((quality_by_id.get(evidence_id) or {}).get("quality_score", 0.60))
        support_score = round(min(upstream_confidence, quality_score), 3)
        horizon_days = PROVIDER_HORIZON_DAYS.get(provider, 30)
        due_date = (created + timedelta(days=horizon_days)).isoformat()
        status = "OPEN"
        abstain_reason = None

        if evidence_id in contradicted_ids:
            status = "ABSTAINED"
            abstain_reason = "same_claim_contradiction"
        elif direction not in {"rising", "falling", "flat"}:
            status = "ABSTAINED"
            abstain_reason = "no_directional_signal"
        elif baseline_metric is None:
            status = "ABSTAINED"
            abstain_reason = "no_comparable_baseline"

        forecast_id = f"FC-{index:02d}"
        forecasts.append(
            {
                "forecast_id": forecast_id,
                "status": status,
                "target_evidence_id": evidence_id,
                "provider": provider,
                "target_metric": target_metric,
                "baseline_metric_value": baseline_metric,
                "baseline_as_of": baseline_as_of,
                "expected_direction": direction if status == "OPEN" else None,
                "tolerance": METRIC_TOLERANCE.get(provider, 0.0),
                "created_at": reference_date,
                "horizon_days": horizon_days,
                "due_date": due_date,
                "method": "directional_persistence_baseline",
                "support_score": support_score,
                "support_score_type": confidence_type,
                "evidence_ids": [evidence_id],
                "claim": (
                    f"By {due_date}, {evidence_id} {target_metric} is expected to be "
                    f"{direction} versus the {baseline_metric!r} baseline."
                    if status == "OPEN"
                    else f"No forecast issued for {evidence_id}: {abstain_reason}."
                ),
                "invalidation_rule": (
                    "Before the due date, a new observation moving opposite the expected direction "
                    "flags the forecast for review; final settlement still waits for the due date."
                    if status == "OPEN"
                    else "Forecast intentionally abstained; collect/reconcile Evidence before issuing one."
                ),
                "abstain_reason": abstain_reason,
                "evaluation": None,
            }
        )

    scenario_state = _scenario_state(signals, quality.get("relation_summary") or {})
    pack_id = _pack_id(question, domain, reference_date)
    scoreboard = _scoreboard(forecasts)
    open_count = scoreboard["open"]
    abstained_count = scoreboard["abstained"]

    return {
        # Scheduler currently verifies citations for synthesis-like downstream artifacts.
        "kind": "synthesis",
        "artifact_type": "forecast_pack",
        "pack_id": pack_id,
        "question": question,
        "domain": domain,
        "answer": (
            f"R7 forecast pack {pack_id}: {open_count} OPEN, {abstained_count} ABSTAINED; "
            f"scenario={scenario_state}. Forecasts are falsifiable directional baselines, not probabilities."
        ),
        "value": float(open_count),
        "unit": "open_forecast_contracts",
        "confidence": upstream_confidence,
        "confidence_type": confidence_type,
        "evidence_ids": evidence_ids,
        "created_at": reference_date,
        "forecast_method": "directional_persistence_baseline",
        "forecasts": forecasts,
        "scenario_tracker": {
            "current_state": scenario_state,
            "initial_state": scenario_state,
            "updated_at": reference_date,
            "definitions": _scenario_definitions(),
            "history": [
                {
                    "as_of": reference_date,
                    "state": scenario_state,
                    "reason": "initial state from grounded S1 directional signals",
                }
            ],
        },
        "scoreboard": scoreboard,
        "revision": {
            "required": False,
            "reasons": [],
        },
        "upstream": {
            "research_confidence": research_synthesis.get("confidence"),
            "domain_decision_status": domain_brief.get("decision_status"),
            "relation_summary": deepcopy(quality.get("relation_summary") or {}),
        },
        "guardrails": {
            "new_data_fetches": 0,
            "new_evidence_ids": 0,
            "confidence_increased": False,
            "forecast_probability": "not_provided",
            "abstention_supported": True,
            "settlement_requires_fresh_research_synthesis": True,
        },
    }


def evaluate_forecast_pack(
    forecast_pack: dict,
    current_research_synthesis: dict,
    as_of_date: str,
) -> dict:
    """Evaluate an existing forecast pack against a later grounded S1 synthesis.

    Forecasts are only RESOLVED after their due date *and* after a newer source
    observation exists. Before that, the system can flag early invalidation but
    must not pretend the forecast has settled.
    """
    if not isinstance(forecast_pack, dict) or forecast_pack.get("artifact_type") != "forecast_pack":
        raise ValueError("forecast_pack must be an R7 forecast_pack artifact")
    if not isinstance(current_research_synthesis, dict) or current_research_synthesis.get("kind") != "synthesis":
        raise ValueError("current_research_synthesis must be a grounded synthesis object")

    checked = date.fromisoformat(as_of_date)
    updated = deepcopy(forecast_pack)
    current_signals = {
        item.get("evidence_id"): item
        for item in current_research_synthesis.get("signals") or []
        if isinstance(item, dict) and item.get("evidence_id")
    }
    current_freshness = current_research_synthesis.get("freshness") or {}
    current_quality = current_research_synthesis.get("quality") or {}

    revision_reasons = []
    for forecast in updated.get("forecasts") or []:
        if forecast.get("status") != "OPEN":
            continue

        evidence_id = forecast.get("target_evidence_id")
        current_signal = current_signals.get(evidence_id)
        if current_signal is None:
            forecast["evaluation"] = {
                "status": "MISSING_CURRENT_SIGNAL",
                "checked_at": as_of_date,
            }
            revision_reasons.append(f"{forecast.get('forecast_id')}: current signal missing")
            continue

        actual_value = _metric_from_signal(current_signal, forecast.get("target_metric"))
        current_as_of = (current_freshness.get(evidence_id) or {}).get("as_of")
        observed_direction = _movement_direction(
            forecast.get("baseline_metric_value"),
            actual_value,
            float(forecast.get("tolerance", 0.0) or 0.0),
        )
        due = date.fromisoformat(forecast["due_date"])
        newer_observation = bool(current_as_of and current_as_of != forecast.get("baseline_as_of"))
        opposite = _opposite(forecast.get("expected_direction"))
        invalidation_triggered = bool(
            newer_observation
            and opposite is not None
            and observed_direction == opposite
        )

        if checked < due:
            forecast["evaluation"] = {
                "status": "PENDING_NOT_DUE",
                "checked_at": as_of_date,
                "current_as_of": current_as_of,
                "actual_metric_value": actual_value,
                "observed_direction": observed_direction,
                "invalidation_triggered": invalidation_triggered,
            }
            if invalidation_triggered:
                revision_reasons.append(
                    f"{forecast.get('forecast_id')}: early invalidation trigger"
                )
            continue

        if not newer_observation:
            forecast["evaluation"] = {
                "status": "AWAITING_NEW_OBSERVATION",
                "checked_at": as_of_date,
                "current_as_of": current_as_of,
                "invalidation_triggered": invalidation_triggered,
            }
            continue

        outcome = "HIT" if observed_direction == forecast.get("expected_direction") else "MISS"
        forecast["status"] = "RESOLVED"
        forecast["evaluation"] = {
            "status": "RESOLVED",
            "outcome": outcome,
            "resolved_at": as_of_date,
            "current_as_of": current_as_of,
            "actual_metric_value": actual_value,
            "movement_from_baseline": _difference(
                actual_value, forecast.get("baseline_metric_value")
            ),
            "observed_direction": observed_direction,
            "expected_direction": forecast.get("expected_direction"),
            "direction_score": 1 if outcome == "HIT" else 0,
            "invalidation_triggered": invalidation_triggered,
        }
        if outcome == "MISS":
            revision_reasons.append(f"{forecast.get('forecast_id')}: forecast MISS")

    relation_summary = current_quality.get("relation_summary") or {}
    new_scenario = _scenario_state(list(current_signals.values()), relation_summary)
    tracker = updated.setdefault("scenario_tracker", {})
    previous_scenario = tracker.get("current_state")
    tracker["current_state"] = new_scenario
    tracker["updated_at"] = as_of_date
    if new_scenario != previous_scenario:
        tracker.setdefault("history", []).append(
            {
                "as_of": as_of_date,
                "state": new_scenario,
                "reason": f"scenario changed from {previous_scenario}",
            }
        )
        revision_reasons.append(
            f"scenario changed: {previous_scenario} -> {new_scenario}"
        )

    if int(relation_summary.get("contradiction", 0) or 0):
        revision_reasons.append("current S1 contains same-claim contradiction")

    updated["scoreboard"] = _scoreboard(updated.get("forecasts") or [])
    updated["revision"] = {
        "required": bool(revision_reasons),
        "reasons": sorted(set(revision_reasons)),
    }
    updated["last_checked_at"] = as_of_date
    updated["latest_research_confidence"] = current_research_synthesis.get("confidence")
    updated["answer"] = (
        f"R7 forecast pack {updated.get('pack_id')} checked {as_of_date}: "
        f"{updated['scoreboard']['resolved']} resolved, {updated['scoreboard']['hits']} hits, "
        f"{updated['scoreboard']['misses']} misses; scenario={new_scenario}."
    )
    return updated


class JsonForecastStore:
    """Tiny durable local store for forecast packs used by the teaching workbench."""

    def __init__(self, directory: str | os.PathLike = ".forecasts"):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, pack: dict) -> Path:
        pack_id = _validate_pack_id(pack.get("pack_id"))
        path = self.directory / f"{pack_id}.json"
        temp_path = path.with_suffix(".tmp")
        payload = json.dumps(pack, indent=2, ensure_ascii=False, sort_keys=True)
        with temp_path.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        return path

    def load(self, pack_id: str) -> dict | None:
        pack_id = _validate_pack_id(pack_id)
        path = self.directory / f"{pack_id}.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def list_ids(self) -> list[str]:
        return sorted(path.stem for path in self.directory.glob("FP-*.json"))


def _pack_id(question: str, domain: str, reference_date: str) -> str:
    digest = hashlib.sha256(
        f"{reference_date}|{domain}|{question.strip()}".encode("utf-8")
    ).hexdigest()[:12].upper()
    return f"FP-{digest}"


def _validate_pack_id(pack_id) -> str:
    if not isinstance(pack_id, str) or not PACK_ID_RE.match(pack_id):
        raise ValueError("invalid forecast pack id")
    return pack_id


def _contradicted_evidence_ids(quality: dict) -> set[str]:
    ids: set[str] = set()
    for relation in quality.get("relations") or []:
        if isinstance(relation, dict) and relation.get("relation") == "CONTRADICTION":
            ids.update(
                item
                for item in relation.get("evidence_ids") or []
                if isinstance(item, str) and item
            )
    return ids


def _provider(evidence_id: str) -> str:
    return evidence_id.split(":", 1)[0].upper() if ":" in evidence_id else "UNKNOWN"


def _baseline_metric(signal: dict) -> tuple[float | None, str]:
    if signal.get("kind") == "yoy":
        return _number(signal.get("yoy_pct")), "yoy_pct"
    return _number(signal.get("latest_value")), "level"


def _metric_from_signal(signal: dict, target_metric: str) -> float | None:
    if target_metric == "yoy_pct":
        return _number(signal.get("yoy_pct"))
    return _number(signal.get("latest_value"))


def _number(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _difference(a, b) -> float | None:
    a_num = _number(a)
    b_num = _number(b)
    if a_num is None or b_num is None:
        return None
    return round(a_num - b_num, 6)


def _movement_direction(baseline, actual, tolerance: float) -> str:
    diff = _difference(actual, baseline)
    if diff is None:
        return "unknown"
    if diff > tolerance:
        return "rising"
    if diff < -tolerance:
        return "falling"
    return "flat"


def _opposite(direction: str | None) -> str | None:
    if direction == "rising":
        return "falling"
    if direction == "falling":
        return "rising"
    return None


def _scenario_state(signals: list[dict], relation_summary: dict) -> str:
    if int(relation_summary.get("contradiction", 0) or 0):
        return "RECONCILE"
    directions = [
        item.get("direction")
        for item in signals
        if isinstance(item, dict) and item.get("direction") in {"rising", "falling", "flat"}
    ]
    rising = directions.count("rising")
    falling = directions.count("falling")
    flat = directions.count("flat")
    if rising >= 2 and falling == 0:
        return "UPSIDE_INFLATION"
    if falling >= 2 and rising == 0:
        return "DOWNSIDE_INFLATION"
    if rising and falling:
        return "MIXED"
    if flat and not rising and not falling:
        return "STABLE"
    return "UNRESOLVED"


def _scenario_definitions() -> list[dict]:
    return [
        {
            "state": "UPSIDE_INFLATION",
            "trigger": "at least two tracked signals are rising and none are falling",
        },
        {
            "state": "DOWNSIDE_INFLATION",
            "trigger": "at least two tracked signals are falling and none are rising",
        },
        {
            "state": "MIXED",
            "trigger": "at least one tracked signal is rising and at least one is falling",
        },
        {
            "state": "RECONCILE",
            "trigger": "S1 contains at least one same-claim contradiction",
        },
        {
            "state": "STABLE",
            "trigger": "tracked directional signals are flat without rising/falling signals",
        },
        {
            "state": "UNRESOLVED",
            "trigger": "insufficient directional information",
        },
    ]


def _scoreboard(forecasts: list[dict]) -> dict:
    open_count = sum(1 for item in forecasts if item.get("status") == "OPEN")
    abstained = sum(1 for item in forecasts if item.get("status") == "ABSTAINED")
    resolved_rows = [item for item in forecasts if item.get("status") == "RESOLVED"]
    hits = sum(
        1
        for item in resolved_rows
        if (item.get("evaluation") or {}).get("outcome") == "HIT"
    )
    misses = sum(
        1
        for item in resolved_rows
        if (item.get("evaluation") or {}).get("outcome") == "MISS"
    )
    resolved = len(resolved_rows)
    return {
        "open": open_count,
        "abstained": abstained,
        "resolved": resolved,
        "hits": hits,
        "misses": misses,
        "directional_accuracy": round(hits / resolved, 3) if resolved else None,
        "accuracy_type": "historical_direction_hit_rate_not_probability",
    }
