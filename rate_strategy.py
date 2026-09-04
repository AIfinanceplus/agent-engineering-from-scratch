"""Pure 2s10s curve signal and one completed paper-trade simulation."""

from __future__ import annotations

from datetime import date
from math import isfinite
from statistics import fmean, pstdev
from typing import Any


RATE_STRATEGY_SCHEMA_VERSION = "rates.curve-mean-reversion.v1"


def simulate_one_curve_trade(
    history: dict,
    *,
    lookback_days: int = 60,
    entry_z: float = 1.0,
    holding_days: int = 20,
    dv01_usd_per_bp: float = 100.0,
    round_trip_cost_bps: float = 1.0,
) -> dict:
    """Find the latest historically completed signal and simulate exactly one trade.

    The entry signal uses only the rolling window ending on the entry date.  The
    exit is the observation exactly ``holding_days`` later.  This is a teaching
    approximation of a DV01-neutral curve trade, not executable bond pricing.
    """
    rows = _validated_rows(history)
    lookback_days = _positive_int(lookback_days, "lookback_days", minimum=20)
    holding_days = _positive_int(holding_days, "holding_days", minimum=1)
    entry_z = _positive(entry_z, "entry_z")
    dv01_usd_per_bp = _positive(dv01_usd_per_bp, "dv01_usd_per_bp")
    round_trip_cost_bps = _non_negative(round_trip_cost_bps, "round_trip_cost_bps")
    minimum = lookback_days + holding_days
    if len(rows) < minimum:
        raise ValueError(
            f"rate history needs at least {minimum} aligned observations; received {len(rows)}"
        )

    latest_context = _signal_at(rows, len(rows) - 1, lookback_days, entry_z)
    completed = None
    for entry_index in range(len(rows) - holding_days - 1, lookback_days - 2, -1):
        signal = _signal_at(rows, entry_index, lookback_days, entry_z)
        if signal["action"] == "NO_TRADE":
            continue
        exit_row = rows[entry_index + holding_days]
        spread_change = round(exit_row["spread_bps"] - signal["entry_spread_bps"], 6)
        gross_curve_pnl_bps = spread_change if signal["action"] == "STEEPENER" else -spread_change
        gross_pnl = round(gross_curve_pnl_bps * dv01_usd_per_bp, 2)
        cost = round(round_trip_cost_bps * dv01_usd_per_bp, 2)
        completed = {
            "paper_trade_id": (
                f"RATE-{signal['entry_date'].replace('-', '')}-{signal['action']}"
            ),
            "status": "SIMULATED_CLOSED",
            "action": signal["action"],
            "entry_date": signal["entry_date"],
            "exit_date": exit_row["date"],
            "holding_observations": holding_days,
            "entry_z_score": signal["z_score"],
            "entry_spread_bps": signal["entry_spread_bps"],
            "exit_spread_bps": exit_row["spread_bps"],
            "spread_change_bps": spread_change,
            "gross_curve_pnl_bps": round(gross_curve_pnl_bps, 6),
            "dv01_usd_per_bp": dv01_usd_per_bp,
            "gross_pnl_usd": gross_pnl,
            "round_trip_cost_bps": round_trip_cost_bps,
            "cost_usd": cost,
            "net_pnl_usd": round(gross_pnl - cost, 2),
            "profitable_after_cost": gross_pnl - cost > 0,
        }
        break
    if completed is None:
        raise ValueError("no completed historical signal crossed the configured entry_z threshold")

    result = {
        "artifact_type": "rate_strategy_simulation",
        "schema_version": RATE_STRATEGY_SCHEMA_VERSION,
        "strategy_id": "treasury_2s10s_mean_reversion",
        "strategy_name": "U.S. Treasury 2s10s Curve Mean Reversion",
        "configuration": {
            "lookback_days": lookback_days,
            "entry_z": entry_z,
            "holding_days": holding_days,
            "dv01_usd_per_bp": dv01_usd_per_bp,
            "round_trip_cost_bps": round_trip_cost_bps,
        },
        "latest_market_context": latest_context,
        "completed_trade": completed,
        "data_summary": {
            "provider": history.get("provider"),
            "series_ids": ["DGS2", "DGS10"],
            "first_date": rows[0]["date"],
            "last_date": rows[-1]["date"],
            "observation_count": len(rows),
        },
        "method": {
            "spread": "(DGS10 - DGS2) * 100 basis points",
            "signal": "rolling population z-score using only data known on entry date",
            "steepener": "z <= -entry_z; profits when 10y-minus-2y spread rises",
            "flattener": "z >= entry_z; profits when 10y-minus-2y spread falls",
            "pnl": "directional spread change * configured DV01 - explicit round-trip cost",
        },
        "guardrails": {
            "paper_simulation_only": True,
            "real_orders_created": False,
            "lookahead_used_for_entry_signal": False,
            "bond_price_model": "DV01_CURVE_APPROXIMATION_ONLY",
            "investment_recommendation": False,
        },
    }
    result["eval"] = evaluate_rate_simulation(result)
    return result


def evaluate_rate_simulation(result: dict) -> dict:
    if not isinstance(result, dict) or result.get("artifact_type") != "rate_strategy_simulation":
        raise ValueError("result must be a rate_strategy_simulation")
    trade = result.get("completed_trade") or {}
    config = result.get("configuration") or {}
    guardrails = result.get("guardrails") or {}
    expected_net = round(
        float(trade.get("gross_curve_pnl_bps", 0)) * float(config.get("dv01_usd_per_bp", 0))
        - float(config.get("round_trip_cost_bps", 0)) * float(config.get("dv01_usd_per_bp", 0)),
        2,
    )
    checks = {
        "exactly_one_completed_trade": trade.get("status") == "SIMULATED_CLOSED",
        "entry_precedes_exit": str(trade.get("entry_date", "")) < str(trade.get("exit_date", "")),
        "pnl_reconciles": abs(float(trade.get("net_pnl_usd", 0)) - expected_net) < 1e-8,
        "no_lookahead_at_entry": guardrails.get("lookahead_used_for_entry_signal") is False,
        "paper_only": guardrails.get("paper_simulation_only") is True,
        "no_real_orders": guardrails.get("real_orders_created") is False,
    }
    return {
        "artifact_type": "rate_strategy_eval",
        "checks": checks,
        "passed": all(checks.values()),
    }


def _signal_at(rows: list[dict], index: int, lookback_days: int, entry_z: float) -> dict:
    if index < lookback_days - 1:
        raise ValueError("signal index does not have enough lookback observations")
    window = [row["spread_bps"] for row in rows[index - lookback_days + 1 : index + 1]]
    center = fmean(window)
    deviation = pstdev(window)
    if deviation <= 1e-12:
        z_score = 0.0
    else:
        z_score = (rows[index]["spread_bps"] - center) / deviation
    action = "STEEPENER" if z_score <= -entry_z else "FLATTENER" if z_score >= entry_z else "NO_TRADE"
    return {
        "as_of": rows[index]["date"],
        "action": action,
        "z_score": round(z_score, 6),
        "entry_date": rows[index]["date"],
        "entry_spread_bps": rows[index]["spread_bps"],
        "rolling_mean_bps": round(center, 6),
        "rolling_std_bps": round(deviation, 6),
        "threshold": entry_z,
    }


def _validated_rows(history: dict) -> list[dict]:
    if not isinstance(history, dict) or history.get("artifact_type") != "rate_curve_history":
        raise ValueError("history must be a rate_curve_history artifact")
    rows = history.get("observations")
    if not isinstance(rows, list):
        raise ValueError("history observations must be a list")
    clean = []
    previous_date = ""
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("date"), str):
            raise ValueError("each rate observation must contain a date")
        try:
            date.fromisoformat(row["date"])
        except ValueError as exc:
            raise ValueError("each rate observation date must be YYYY-MM-DD") from exc
        if row["date"] <= previous_date:
            raise ValueError("rate observations must be strictly increasing by date")
        dgs2 = _finite(row.get("dgs2"), "dgs2")
        dgs10 = _finite(row.get("dgs10"), "dgs10")
        spread = _finite(row.get("spread_bps"), "spread_bps")
        expected = (dgs10 - dgs2) * 100
        if abs(spread - expected) > 1e-5:
            raise ValueError("spread_bps must equal (dgs10 - dgs2) * 100")
        clean.append({"date": row["date"], "dgs2": dgs2, "dgs10": dgs10, "spread_bps": spread})
        previous_date = row["date"]
    return clean


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be finite")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _positive(value: Any, label: str) -> float:
    number = _finite(value, label)
    if number <= 0:
        raise ValueError(f"{label} must be > 0")
    return number


def _non_negative(value: Any, label: str) -> float:
    number = _finite(value, label)
    if number < 0:
        raise ValueError(f"{label} must be >= 0")
    return number


def _positive_int(value: Any, label: str, *, minimum: int) -> int:
    number = _finite(value, label)
    if int(number) != number or number < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return int(number)
