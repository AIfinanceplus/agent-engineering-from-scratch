"""R12 Step 9 paper-portfolio projection and atomic multi-trade limits.

The append-only per-trade ledger remains the source of truth.  This module
replays every trade into a read model, aggregates unsettled exposure, and wraps
new intents / fills with an atomic preflight.  It has no exchange connection and
does not reinterpret a quote as a fill.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from functools import wraps
from math import isfinite
from threading import RLock
from typing import Any

from r12_paper import EPS, R12PaperLedger, paper_trade_id_for_agent_run


PORTFOLIO_SCHEMA_VERSION = "r12.paper-portfolio.v1"


class R12PortfolioLimitExceeded(ValueError):
    """A proposed paper command would exceed one or more explicit limits."""


@dataclass(frozen=True)
class R12PaperPortfolioLimits:
    max_unsettled_trades: int = 20
    max_unsettled_acquisition_cost: float = 5_000.0
    max_total_leg_risk_quantity: float = 50.0
    max_provider_filled_notional: float = 3_000.0
    max_identity_acquisition_cost: float = 2_000.0

    def __post_init__(self):
        for name, value in self.to_dict().items():
            number = _finite_non_negative(value, name)
            if name == "max_unsettled_trades" and (number < 1 or int(number) != number):
                raise ValueError("max_unsettled_trades must be a positive integer")

    def to_dict(self) -> dict:
        return {
            "max_unsettled_trades": self.max_unsettled_trades,
            "max_unsettled_acquisition_cost": self.max_unsettled_acquisition_cost,
            "max_total_leg_risk_quantity": self.max_total_leg_risk_quantity,
            "max_provider_filled_notional": self.max_provider_filled_notional,
            "max_identity_acquisition_cost": self.max_identity_acquisition_cost,
        }


def _serialized(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class R12PaperPortfolio:
    """Read model plus atomic guard around risk-increasing ledger commands."""

    def __init__(self, ledger: R12PaperLedger, limits: R12PaperPortfolioLimits | None = None):
        if not isinstance(ledger, R12PaperLedger):
            raise TypeError("ledger must be an R12PaperLedger")
        self.ledger = ledger
        self.limits = limits or R12PaperPortfolioLimits()
        self._lock = RLock()

    @_serialized
    def status(self) -> dict:
        return build_r12_paper_portfolio(self.ledger.list_trades(), self.limits)

    @_serialized
    def create_from_agent_run(self, run: dict, opportunity_id: str, idempotency_key: str) -> dict:
        trade_id = paper_trade_id_for_agent_run(run, opportunity_id, idempotency_key)
        if self.ledger.store.load_events(trade_id):
            return self.ledger.create_from_agent_run(run, opportunity_id, idempotency_key)
        current = build_r12_paper_portfolio(self.ledger.list_trades(), self.limits)
        if current["risk_status"] != "WITHIN_LIMITS":
            raise R12PortfolioLimitExceeded(_limit_message(current["violations"]))
        if current["summary"]["unsettled_trade_count"] >= self.limits.max_unsettled_trades:
            raise R12PortfolioLimitExceeded(
                f"paper portfolio limit exceeded: max_unsettled_trades={self.limits.max_unsettled_trades}"
            )
        return self.ledger.create_from_agent_run(run, opportunity_id, idempotency_key)

    @_serialized
    def preflight_fill(
        self,
        paper_trade_id: str,
        *,
        leg_id: str,
        quantity: float,
        price: float,
        fee: float,
    ) -> dict:
        return self._preflight_fill(paper_trade_id, leg_id=leg_id, quantity=quantity, price=price, fee=fee)

    @_serialized
    def record_fill(
        self,
        paper_trade_id: str,
        *,
        leg_id: str,
        quantity: float,
        price: float,
        fee: float,
        idempotency_key: str,
    ) -> dict:
        current = self.ledger.get(paper_trade_id)
        if any(event.get("idempotency_key") == idempotency_key for event in current["events"]):
            return self.ledger.record_fill(
                paper_trade_id,
                leg_id=leg_id,
                quantity=quantity,
                price=price,
                fee=fee,
                idempotency_key=idempotency_key,
            )
        preflight = self._preflight_fill(
            paper_trade_id,
            leg_id=leg_id,
            quantity=quantity,
            price=price,
            fee=fee,
        )
        if not preflight["allowed"]:
            raise R12PortfolioLimitExceeded(_limit_message(preflight["violations"]))
        return self.ledger.record_fill(
            paper_trade_id,
            leg_id=leg_id,
            quantity=quantity,
            price=price,
            fee=fee,
            idempotency_key=idempotency_key,
        )

    def _preflight_fill(self, paper_trade_id: str, *, leg_id: str, quantity: float, price: float, fee: float) -> dict:
        quantity = _positive(quantity, "quantity")
        price = _probability_price(price, "price")
        fee = _finite_non_negative(fee, "fee")
        trades = self.ledger.list_trades()
        trade = next((row for row in trades if row["paper_trade_id"] == paper_trade_id), None)
        if trade is None:
            raise KeyError(f"R12 paper trade not found: {paper_trade_id}")
        if trade.get("settlement") is not None:
            raise ValueError("paper trade is already settled")
        if trade.get("termination") is not None:
            raise ValueError("paper order is cancelled or expired; only marks or settlement remain allowed")
        leg = next((row for row in trade["legs"] if row["leg_id"] == leg_id), None)
        if leg is None:
            raise ValueError(f"unknown paper leg_id: {leg_id}")
        if quantity - float(leg["remaining_quantity"]) > EPS:
            raise ValueError(f"fill exceeds remaining target quantity for {leg_id}")

        projected = deepcopy(trade)
        projected_leg = next(row for row in projected["legs"] if row["leg_id"] == leg_id)
        projected_leg["filled_quantity"] = _rounded(float(projected_leg["filled_quantity"]) + quantity)
        projected_leg["fill_notional"] = _rounded(float(projected_leg["fill_notional"]) + quantity * price)
        projected_leg["fees"] = _rounded(float(projected_leg["fees"]) + fee)
        projected_leg["remaining_quantity"] = _rounded(float(projected_leg["target_quantity"]) - projected_leg["filled_quantity"])
        quantities = [float(row["filled_quantity"]) for row in projected["legs"]]
        projected["risk"]["matched_quantity"] = _rounded(min(quantities))
        projected["risk"]["leg_risk_quantity"] = _rounded(max(quantities) - min(quantities))
        projected["pnl"]["acquisition_cost"] = _rounded(
            sum(float(row["fill_notional"]) + float(row["fees"]) for row in projected["legs"])
        )
        projected["pnl"]["marked_value"] = None
        projected["pnl"]["mark_to_market_pnl"] = None
        projected["status"] = "PROJECTED_FILL"
        projected_trades = [projected if row["paper_trade_id"] == paper_trade_id else row for row in trades]
        portfolio = build_r12_paper_portfolio(projected_trades, self.limits)
        return {
            "artifact_type": "r12_paper_fill_preflight",
            "paper_trade_id": paper_trade_id,
            "leg_id": leg_id,
            "allowed": portfolio["risk_status"] == "WITHIN_LIMITS",
            "violations": portfolio["violations"],
            "projected_portfolio": portfolio,
            "guardrails": {
                "preflight_is_a_fill": False,
                "ledger_mutated": False,
                "automatic_execution": False,
            },
        }


def build_r12_paper_portfolio(trades: list[dict], limits: R12PaperPortfolioLimits | None = None) -> dict:
    if not isinstance(trades, list):
        raise ValueError("trades must be a list")
    limits = limits or R12PaperPortfolioLimits()
    rows = []
    providers: dict[str, dict] = {}
    identities: dict[str, dict] = {}
    unsettled_acquisition = 0.0
    total_leg_risk = 0.0
    known_mtm = 0.0
    mtm_unknown = 0
    realized = 0.0
    unsettled_count = 0
    settled_count = 0

    for trade in sorted(trades, key=lambda row: row.get("paper_trade_id", "")):
        if not isinstance(trade, dict) or trade.get("artifact_type") != "r12_paper_trade":
            raise ValueError("portfolio accepts only replayed r12_paper_trade artifacts")
        acquisition = float((trade.get("pnl") or {}).get("acquisition_cost") or 0.0)
        settled = trade.get("settlement") is not None
        terminal_unfilled = trade.get("status") in {"CANCELLED_UNFILLED", "EXPIRED_UNFILLED"}
        unsettled = not settled and not terminal_unfilled
        if unsettled:
            unsettled_count += 1
            unsettled_acquisition += acquisition
            total_leg_risk += float((trade.get("risk") or {}).get("leg_risk_quantity") or 0.0)
            if acquisition > EPS:
                mtm = (trade.get("pnl") or {}).get("mark_to_market_pnl")
                if mtm is None:
                    mtm_unknown += 1
                else:
                    known_mtm += float(mtm)
            identity = str(trade.get("identity_id") or "UNIDENTIFIED")
            bucket = identities.setdefault(identity, {"trade_count": 0, "acquisition_cost": 0.0})
            bucket["trade_count"] += 1
            bucket["acquisition_cost"] += acquisition
            for leg in trade.get("legs") or []:
                provider = str(leg.get("provider") or "unknown")
                provider_bucket = providers.setdefault(
                    provider,
                    {"filled_quantity": 0.0, "filled_notional": 0.0, "fees": 0.0},
                )
                provider_bucket["filled_quantity"] += float(leg.get("filled_quantity") or 0.0)
                provider_bucket["filled_notional"] += float(leg.get("fill_notional") or 0.0)
                provider_bucket["fees"] += float(leg.get("fees") or 0.0)
        else:
            settled_count += int(settled)
        if settled:
            realized += float((trade.get("pnl") or {}).get("realized_pnl") or 0.0)
        rows.append(
            {
                "paper_trade_id": trade["paper_trade_id"],
                "source_run_id": trade.get("source_run_id"),
                "identity_id": trade.get("identity_id"),
                "status": trade.get("status"),
                "event_count": trade.get("event_count"),
                "unsettled": unsettled,
                "acquisition_cost": _rounded(acquisition),
                "matched_quantity": (trade.get("risk") or {}).get("matched_quantity"),
                "leg_risk_quantity": (trade.get("risk") or {}).get("leg_risk_quantity"),
                "mark_to_market_pnl": (trade.get("pnl") or {}).get("mark_to_market_pnl"),
                "realized_pnl": (trade.get("pnl") or {}).get("realized_pnl"),
            }
        )

    providers = {key: {name: _rounded(value) for name, value in row.items()} for key, row in sorted(providers.items())}
    identities = {
        key: {"trade_count": row["trade_count"], "acquisition_cost": _rounded(row["acquisition_cost"])}
        for key, row in sorted(identities.items())
    }
    summary = {
        "trade_count": len(rows),
        "unsettled_trade_count": unsettled_count,
        "settled_trade_count": settled_count,
        "unsettled_acquisition_cost": _rounded(unsettled_acquisition),
        "total_leg_risk_quantity": _rounded(total_leg_risk),
        "mark_to_market_complete": mtm_unknown == 0,
        "mark_to_market_pnl": _rounded(known_mtm) if mtm_unknown == 0 else None,
        "known_mark_to_market_pnl": _rounded(known_mtm),
        "trades_missing_complete_marks": mtm_unknown,
        "realized_pnl": _rounded(realized),
        "pnl_unit": "settlement_currency",
    }
    violations = _portfolio_violations(summary, providers, identities, limits)
    return {
        "artifact_type": "r12_paper_portfolio",
        "schema_version": PORTFOLIO_SCHEMA_VERSION,
        "risk_status": "LIMIT_BREACH" if violations else "WITHIN_LIMITS",
        "summary": summary,
        "limits": limits.to_dict(),
        "violations": violations,
        "by_provider": providers,
        "by_identity": identities,
        "trades": rows,
        "guardrails": {
            "source_of_truth": "replayed_append_only_trade_ledgers",
            "risk_increasing_commands_require_atomic_preflight": True,
            "settled_exposure_counts_toward_open_limits": False,
            "unknown_marks_are_not_treated_as_zero_pnl": True,
            "cross_trade_netting_credit_applied": False,
            "exchange_connection_present": False,
            "automatic_execution": False,
        },
    }


def evaluate_r12_paper_portfolio(portfolio: dict) -> dict:
    if not isinstance(portfolio, dict) or portfolio.get("artifact_type") != "r12_paper_portfolio":
        raise ValueError("portfolio must be an r12_paper_portfolio")
    violations = portfolio.get("violations") or []
    summary = portfolio.get("summary") or {}
    guardrails = portfolio.get("guardrails") or {}
    checks = {
        "risk_status_matches_violations": portfolio.get("risk_status")
        == ("LIMIT_BREACH" if violations else "WITHIN_LIMITS"),
        "limits_are_explicit": set((portfolio.get("limits") or {}))
        == set(R12PaperPortfolioLimits().to_dict()),
        "unknown_marks_not_zero_filled": summary.get("trades_missing_complete_marks", 0) == 0
        or summary.get("mark_to_market_pnl") is None,
        "source_is_replayed_ledgers": guardrails.get("source_of_truth")
        == "replayed_append_only_trade_ledgers",
        "risk_increase_requires_atomic_preflight": guardrails.get(
            "risk_increasing_commands_require_atomic_preflight"
        )
        is True,
        "cross_trade_netting_credit_disabled": guardrails.get("cross_trade_netting_credit_applied") is False,
        "automatic_execution_disabled": guardrails.get("automatic_execution") is False,
    }
    return {
        "artifact_type": "r12_paper_portfolio_eval",
        "checks": checks,
        "passed": all(checks.values()),
    }


def _portfolio_violations(summary: dict, providers: dict, identities: dict, limits: R12PaperPortfolioLimits) -> list[dict]:
    violations = []
    _append_violation(violations, "max_unsettled_trades", summary["unsettled_trade_count"], limits.max_unsettled_trades)
    _append_violation(
        violations,
        "max_unsettled_acquisition_cost",
        summary["unsettled_acquisition_cost"],
        limits.max_unsettled_acquisition_cost,
    )
    _append_violation(
        violations,
        "max_total_leg_risk_quantity",
        summary["total_leg_risk_quantity"],
        limits.max_total_leg_risk_quantity,
    )
    for provider, row in providers.items():
        _append_violation(
            violations,
            "max_provider_filled_notional",
            row["filled_notional"],
            limits.max_provider_filled_notional,
            scope=provider,
        )
    for identity, row in identities.items():
        _append_violation(
            violations,
            "max_identity_acquisition_cost",
            row["acquisition_cost"],
            limits.max_identity_acquisition_cost,
            scope=identity,
        )
    return violations


def _append_violation(violations: list[dict], limit_name: str, value: float, limit: float, *, scope: str | None = None) -> None:
    if float(value) - float(limit) > EPS:
        violations.append(
            {
                "limit": limit_name,
                "scope": scope,
                "value": _rounded(value),
                "maximum": _rounded(limit),
                "excess": _rounded(float(value) - float(limit)),
            }
        )


def _limit_message(violations: list[dict]) -> str:
    detail = ", ".join(
        f"{row['limit']}{'[' + row['scope'] + ']' if row.get('scope') else ''}={row['value']} > {row['maximum']}"
        for row in violations
    )
    return f"paper portfolio limit exceeded: {detail or 'unknown limit'}"


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


def _finite_non_negative(value: Any, label: str) -> float:
    number = _finite(value, label)
    if number < 0:
        raise ValueError(f"{label} must be non-negative")
    return number


def _positive(value: Any, label: str) -> float:
    number = _finite(value, label)
    if number <= 0:
        raise ValueError(f"{label} must be > 0")
    return number


def _probability_price(value: Any, label: str) -> float:
    number = _finite(value, label)
    if not 0 <= number <= 1:
        raise ValueError(f"{label} must be between 0 and 1")
    return number


def _rounded(value: float) -> float:
    return round(float(value), 8)
