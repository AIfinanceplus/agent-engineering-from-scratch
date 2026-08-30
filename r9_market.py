"""R9 observed market-pricing context.

R9 adds a second, explicitly separate evidence lane:

    Research Evidence -> S1
    Market Evidence   -> M6 MarketPricingSnapshot

The snapshot reports observable market levels only. Derived spreads use the
latest COMMON observation date across their component series, so a holiday or
missing observation cannot silently create a false curve move. R9 does not infer
a Fed path, compute mispricing/EV, or recommend a position; those belong to R10.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date


MARKET_SERIES = {
    "M1": {"series_id": "DFF", "label": "Effective Federal Funds Rate", "unit": "percent", "role": "policy_rate_anchor"},
    "M2": {"series_id": "DGS2", "label": "Market Yield on U.S. Treasury Securities at 2-Year Constant Maturity", "unit": "percent", "role": "front_end_treasury_yield"},
    "M3": {"series_id": "DGS10", "label": "Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity", "unit": "percent", "role": "long_end_treasury_yield"},
    "M4": {"series_id": "DFII10", "label": "Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity, Inflation-Indexed", "unit": "percent", "role": "ten_year_real_yield"},
    "M5": {"series_id": "T10YIE", "label": "10-Year Breakeven Inflation Rate", "unit": "percent", "role": "ten_year_inflation_compensation"},
}

EXPECTED_IDS = {f"FRED:{row['series_id']}" for row in MARKET_SERIES.values()}


def build_market_pricing_snapshot(
    policy_rate: dict,
    treasury_2y: dict,
    treasury_10y: dict,
    real_yield_10y: dict,
    breakeven_10y: dict,
    reference_date: str,
) -> dict:
    rows = [policy_rate, treasury_2y, treasury_10y, real_yield_10y, breakeven_10y]
    _validate_rows(rows)
    by_id = {row["evidence_id"]: deepcopy(row) for row in rows}

    dff = by_id["FRED:DFF"]
    dgs2 = by_id["FRED:DGS2"]
    dgs10 = by_id["FRED:DGS10"]
    dfii10 = by_id["FRED:DFII10"]
    t10yie = by_id["FRED:T10YIE"]

    term_date, term_values = _latest_common_observation(dgs2, dgs10)
    term_spread = (
        round(term_values[1] - term_values[0], 3)
        if term_values is not None
        else None
    )

    cross_date, cross_values = _latest_common_observation(dgs10, dfii10, t10yie)
    if cross_values is None:
        nominal_real_spread = None
        breakeven_crosscheck_gap = None
    else:
        nominal_real_spread = round(cross_values[0] - cross_values[1], 3)
        breakeven_crosscheck_gap = round(nominal_real_spread - cross_values[2], 3)

    return {
        "kind": "synthesis",
        "artifact_type": "market_pricing_snapshot",
        "answer": (
            "R9 observed market context captures policy-rate, Treasury, real-yield, and breakeven levels. "
            "Derived spreads are synchronized to common observation dates. No implied Fed path, "
            "mispricing, expected value, or position is computed."
        ),
        "value": term_spread,
        "unit": "percentage_points_10y_minus_2y",
        "confidence": 1.0,
        "confidence_type": "observed_market_data_not_forecast_probability",
        "reference_date": reference_date,
        "evidence_ids": sorted(EXPECTED_IDS),
        "market_levels": {
            "effective_fed_funds_rate": _level(dff),
            "treasury_2y": _level(dgs2),
            "treasury_10y": _level(dgs10),
            "real_yield_10y": _level(dfii10),
            "breakeven_10y": _level(t10yie),
        },
        "freshness": {
            row["evidence_id"]: _freshness(row.get("as_of"), reference_date)
            for row in rows
        },
        "derived_observations": {
            "term_spread_10y_minus_2y": term_spread,
            "term_spread_as_of": term_date,
            "term_spread_status": "OBSERVED_COMMON_DATE" if term_date else "NO_COMMON_OBSERVATION",
            "curve_shape": _curve_shape(term_spread),
            "nominal_minus_real_10y_spread": nominal_real_spread,
            "breakeven_crosscheck_gap": breakeven_crosscheck_gap,
            "nominal_real_breakeven_as_of": cross_date,
            "nominal_real_breakeven_status": "OBSERVED_COMMON_DATE" if cross_date else "NO_COMMON_OBSERVATION",
        },
        "semantics": {
            "market_context": "observed_levels",
            "fed_path": "NOT_INFERRED_R9",
            "market_implied_macro_view": "NOT_CONSTRUCTED_R9",
            "mispricing": "NOT_COMPUTED_R9",
            "expected_value": "NOT_COMPUTED_R9",
            "position": "NONE_R9",
        },
        "guardrails": {
            "research_evidence_mutated": False,
            "new_market_evidence_ids": 5,
            "derived_values_use_common_observation_date": True,
            "implied_policy_path_fabricated": False,
            "probabilities_fabricated": False,
            "mispricing_computed": False,
            "expected_value_computed": False,
            "position_recommended": False,
        },
    }


def _validate_rows(rows: list[dict]) -> None:
    if len(rows) != 5 or not all(isinstance(row, dict) for row in rows):
        raise ValueError("R9 market snapshot requires five market Evidence objects")
    ids = {row.get("evidence_id") for row in rows}
    if ids != EXPECTED_IDS:
        raise ValueError(f"R9 market Evidence IDs must be exactly {sorted(EXPECTED_IDS)}")
    for row in rows:
        if row.get("kind") != "evidence" or row.get("provider") != "FRED":
            raise ValueError("R9 market inputs must be grounded FRED Evidence")
        if not isinstance(row.get("value"), (int, float)):
            raise ValueError(f"{row.get('evidence_id')} must contain a numeric value")
        if not row.get("as_of"):
            raise ValueError(f"{row.get('evidence_id')} must contain as_of")


def _history_map(row: dict) -> dict[str, float]:
    points: dict[str, float] = {}
    for item in row.get("history") or []:
        if not isinstance(item, dict) or not item.get("period"):
            continue
        try:
            points[str(item["period"])] = float(item["value"])
        except (KeyError, TypeError, ValueError):
            continue
    try:
        points.setdefault(str(row["as_of"]), float(row["value"]))
    except (KeyError, TypeError, ValueError):
        pass
    return points


def _latest_common_observation(*rows: dict) -> tuple[str | None, list[float] | None]:
    maps = [_history_map(row) for row in rows]
    if not maps:
        return None, None
    common = set(maps[0])
    for mapping in maps[1:]:
        common &= set(mapping)
    if not common:
        return None, None
    period = max(common)
    return period, [mapping[period] for mapping in maps]


def _freshness(as_of: str | None, reference_date: str) -> dict:
    try:
        age_days = max(0, (date.fromisoformat(reference_date) - date.fromisoformat(str(as_of))).days)
    except (TypeError, ValueError):
        return {"as_of": as_of, "age_days": None, "status": "UNKNOWN"}
    return {
        "as_of": as_of,
        "age_days": age_days,
        "status": "FRESH" if age_days <= 7 else "STALE",
    }


def _level(row: dict) -> dict:
    return {
        "evidence_id": row["evidence_id"],
        "value": float(row["value"]),
        "unit": row.get("unit"),
        "as_of": row.get("as_of"),
        "title": (row.get("source") or {}).get("title"),
    }


def _curve_shape(spread: float | None) -> str:
    if spread is None:
        return "UNRESOLVED"
    if spread > 0.10:
        return "POSITIVE"
    if spread < -0.10:
        return "INVERTED"
    return "FLAT"
