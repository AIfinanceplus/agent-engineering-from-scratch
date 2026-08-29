"""R1 deterministic macro analysis functions.

Analysis consumes collected evidence objects instead of reaching around the
EvidenceStore to fetch fresh data. This keeps provenance explicit: source Tasks
collect data; analysis Tasks compute only from those inputs.
"""


def compare_cpi_series(headline: dict, core: dict) -> dict:
    _require_bls_evidence(headline)
    _require_bls_evidence(core)

    headline_yoy, headline_period = _latest_yoy(headline["history"])
    core_yoy, core_period = _latest_yoy(core["history"])
    if headline_period != core_period:
        raise ValueError(
            f"Headline/core latest periods do not match: {headline_period} vs {core_period}"
        )

    gap = round(core_yoy - headline_yoy, 3)
    direction = "above" if gap > 0 else "below" if gap < 0 else "equal to"
    mode = (
        headline.get("source_mode")
        if headline.get("source_mode") == core.get("source_mode")
        else "mixed"
    )
    evidence_ids = [headline["evidence_id"], core["evidence_id"]]
    confidence = min(float(headline.get("confidence", 0)), float(core.get("confidence", 0)))

    return {
        "kind": "synthesis",
        "answer": (
            f"For {headline_period}, headline CPI YoY is {headline_yoy:.2f}% and "
            f"core CPI YoY is {core_yoy:.2f}%. Core is {abs(gap):.2f} percentage "
            f"points {direction} headline. [{evidence_ids[0]}] [{evidence_ids[1]}]"
        ),
        "confidence": confidence,
        "evidence_ids": evidence_ids,
        "source_mode": mode,
        "metrics": {
            "period": headline_period,
            "headline_yoy_pct": headline_yoy,
            "core_yoy_pct": core_yoy,
            "core_minus_headline_pp": gap,
        },
    }


def _require_bls_evidence(payload: dict) -> None:
    if not isinstance(payload, dict) or payload.get("kind") != "evidence":
        raise ValueError("CPI analysis requires evidence objects")
    if not str(payload.get("evidence_id", "")).startswith("BLS:"):
        raise ValueError("CPI analysis requires BLS evidence")
    if not isinstance(payload.get("history"), list):
        raise ValueError("BLS evidence must include history")


def _latest_yoy(history: list[dict]) -> tuple[float, str]:
    monthly = {
        (int(item["year"]), int(item["month"])): float(item["value"])
        for item in history
        if 1 <= int(item["month"]) <= 12
    }
    if not monthly:
        raise ValueError("Cannot compute YoY without monthly history")

    year, month = max(monthly)
    previous_key = (year - 1, month)
    if previous_key not in monthly:
        raise ValueError(
            f"Cannot compute YoY for {year:04d}-{month:02d}: prior-year month is missing"
        )
    previous = monthly[previous_key]
    current = monthly[(year, month)]
    if previous == 0:
        raise ValueError("Prior-year index value cannot be zero")

    yoy = round((current / previous - 1) * 100, 3)
    return yoy, f"{year:04d}-{month:02d}"
