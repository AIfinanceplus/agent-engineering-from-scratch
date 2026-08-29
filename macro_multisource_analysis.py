"""R2 deterministic cross-source macro synthesis.

This layer combines already-collected BLS, FRED, and EIA evidence. It produces
descriptive signals only; it does not infer causal CPI contributions from price
co-movement.
"""

from __future__ import annotations

from datetime import date, datetime

from macro_analysis import compare_cpi_series


def synthesize_macro_signals(
    headline: dict,
    core: dict,
    breakeven: dict,
    gasoline: dict,
    reference_date: str,
) -> dict:
    cpi = compare_cpi_series(headline, core)
    _require_provider(breakeven, "FRED")
    _require_provider(gasoline, "EIA")
    ref = _parse_date(reference_date)

    breakeven_change = _history_change(breakeven["history"])
    gasoline_change_pct = _history_pct_change(gasoline["history"])
    freshness = {
        headline["evidence_id"]: _freshness(_bls_latest_date(headline), ref),
        core["evidence_id"]: _freshness(_bls_latest_date(core), ref),
        breakeven["evidence_id"]: _freshness(_parse_date(breakeven["as_of"]), ref),
        gasoline["evidence_id"]: _freshness(_parse_date(gasoline["as_of"]), ref),
    }

    cpi_metrics = cpi["metrics"]
    core_gap = float(cpi_metrics["core_minus_headline_pp"])
    price_signal = "rising" if gasoline_change_pct > 2 else "falling" if gasoline_change_pct < -2 else "roughly_flat"
    expectation_signal = "rising" if breakeven_change > 0.05 else "falling" if breakeven_change < -0.05 else "roughly_flat"
    gap_signal = "core_above_headline" if core_gap > 0 else "headline_above_core" if core_gap < 0 else "equal"

    evidence_ids = [
        headline["evidence_id"],
        core["evidence_id"],
        breakeven["evidence_id"],
        gasoline["evidence_id"],
    ]
    confidence = min(float(item.get("confidence", 0)) for item in (headline, core, breakeven, gasoline))
    all_fresh = all(item["status"] != "stale" for item in freshness.values())
    if not all_fresh:
        confidence = min(confidence, 0.7)

    return {
        "kind": "synthesis",
        "answer": (
            f"Headline CPI YoY is {cpi_metrics['headline_yoy_pct']:.2f}% and core CPI YoY is "
            f"{cpi_metrics['core_yoy_pct']:.2f}% for {cpi_metrics['period']}. "
            f"The latest fixture/live gasoline window is {price_signal} ({gasoline_change_pct:+.2f}%), "
            f"while the 5-year breakeven window is {expectation_signal} ({breakeven_change:+.2f} pp). "
            f"This is a descriptive cross-source read, not a causal CPI attribution. "
            + " ".join(f"[{evidence_id}]" for evidence_id in evidence_ids)
        ),
        "confidence": round(confidence, 3),
        "evidence_ids": evidence_ids,
        "reference_date": reference_date,
        "metrics": {
            **cpi_metrics,
            "gasoline_window_change_pct": gasoline_change_pct,
            "breakeven_window_change_pp": breakeven_change,
        },
        "signals": {
            "headline_core_gap": gap_signal,
            "energy_price_pressure": price_signal,
            "market_inflation_expectations": expectation_signal,
        },
        "freshness": freshness,
        "limitations": [
            "Different sources publish at different frequencies and dates.",
            "Gasoline and breakeven movements are descriptive signals, not causal CPI contributions.",
            "Fixture mode is teaching-only and must not be interpreted as current macro data.",
        ],
    }


def _require_provider(payload: dict, provider: str) -> None:
    if not isinstance(payload, dict) or payload.get("kind") != "evidence":
        raise ValueError(f"{provider} input must be an evidence object")
    if payload.get("provider") != provider:
        raise ValueError(f"Expected {provider} evidence")
    if not isinstance(payload.get("history"), list) or not payload["history"]:
        raise ValueError(f"{provider} evidence must include history")


def _history_change(history: list[dict]) -> float:
    if len(history) < 2:
        raise ValueError("Need at least two observations to compute change")
    return round(float(history[-1]["value"]) - float(history[0]["value"]), 3)


def _history_pct_change(history: list[dict]) -> float:
    if len(history) < 2:
        raise ValueError("Need at least two observations to compute percent change")
    first = float(history[0]["value"])
    last = float(history[-1]["value"])
    if first == 0:
        raise ValueError("First observation cannot be zero")
    return round((last / first - 1) * 100, 3)


def _bls_latest_date(evidence: dict) -> date:
    history = evidence.get("history") or []
    if not history:
        raise ValueError("BLS evidence must include history")
    latest = max(history, key=lambda item: (int(item["year"]), int(item["month"])))
    return date(int(latest["year"]), int(latest["month"]), 1)


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Expected YYYY-MM-DD date, got {value!r}") from exc


def _freshness(observation_date: date, reference_date: date) -> dict:
    age_days = (reference_date - observation_date).days
    if age_days < 0:
        status = "future"
    elif age_days <= 45:
        status = "fresh"
    elif age_days <= 90:
        status = "aging"
    else:
        status = "stale"
    return {
        "as_of": observation_date.isoformat(),
        "age_days": age_days,
        "status": status,
    }
