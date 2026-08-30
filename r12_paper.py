"""R12 Step 7 append-only paper-fill ledger and deterministic P&L replay.

E1 produces an execution quote, not a fill.  This module creates a paper order
intent that is lineage-bound to one completed Strategy Agent run, then records
explicit simulated fill commands as tamper-evident JSONL events.

There are no exchange credentials and no order-placement functions here.  Every
mutation requires an idempotency key because command retries are a different
engineering problem from retrying the read/compute Tools used by the Agent DAG.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from copy import deepcopy
from datetime import datetime, timezone
from functools import wraps
from math import isfinite
from pathlib import Path
from threading import RLock
from typing import Any


SCHEMA_VERSION = "r12.paper-ledger.v1"
EPS = 1e-9
TRADE_ID_RE = re.compile(r"^R12P-[0-9a-f]{16}$")
TERMINAL_EVENTS = {"paper_order_cancelled", "paper_order_expired", "paper_trade_settled"}


def _serialized(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class JsonlR12PaperLedgerStore:
    """One append-only, fsync'd JSONL event stream per paper trade."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def load_events(self, paper_trade_id: str) -> list[dict]:
        path = self._path(paper_trade_id)
        if not path.exists():
            return []
        events = []
        for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid paper ledger JSON at line {line_number}") from exc
            if not isinstance(event, dict):
                raise ValueError(f"invalid paper ledger event at line {line_number}")
            events.append(event)
        return events

    def append(self, event: dict) -> Path:
        paper_trade_id = event.get("paper_trade_id")
        path = self._path(paper_trade_id)
        encoded = json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
        descriptor = os.open(path, flags, 0o600)
        try:
            os.write(descriptor, encoded.encode("utf-8"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return path

    def _path(self, paper_trade_id: str) -> Path:
        if not isinstance(paper_trade_id, str) or not TRADE_ID_RE.fullmatch(paper_trade_id):
            raise ValueError("paper_trade_id must match R12P-<16 lowercase hex chars>")
        return self.directory / f"{paper_trade_id}.jsonl"


class R12PaperLedger:
    """Command boundary for creating, filling, marking, and settling paper trades."""

    def __init__(self, store: JsonlR12PaperLedgerStore):
        self.store = store
        self._lock = RLock()

    @_serialized
    def create_from_agent_run(self, run: dict, opportunity_id: str, idempotency_key: str) -> dict:
        key = _required_text(idempotency_key, "idempotency_key")
        payload = _paper_intent_payload(run, opportunity_id)
        paper_trade_id = "R12P-" + _fingerprint(
            {"run_id": payload["source_run_id"], "opportunity_id": opportunity_id, "idempotency_key": key}
        )[:16]
        events = self.store.load_events(paper_trade_id)
        replayed = _idempotent_replay(events, "paper_intent_created", payload, key)
        if replayed is not None:
            return replayed
        if events:
            raise ValueError("paper trade already exists with different creation command")
        event = _new_event(paper_trade_id, "paper_intent_created", payload, key, events)
        self.store.append(event)
        return replay_paper_events([event])

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
        payload = {
            "leg_id": _required_text(leg_id, "leg_id"),
            "quantity": _positive_number(quantity, "quantity"),
            "price": _probability_price(price, "price"),
            "fee": _non_negative_number(fee, "fee"),
        }
        return self._mutate(paper_trade_id, "paper_fill_recorded", payload, idempotency_key)

    @_serialized
    def mark_to_market(self, paper_trade_id: str, *, marks: dict, idempotency_key: str) -> dict:
        if not isinstance(marks, dict) or not marks:
            raise ValueError("marks must be a non-empty object keyed by leg_id")
        payload = {
            "marks": {
                _required_text(leg_id, "marks leg_id"): _probability_price(price, f"mark {leg_id}")
                for leg_id, price in sorted(marks.items())
            }
        }
        return self._mutate(paper_trade_id, "paper_marks_updated", payload, idempotency_key)

    @_serialized
    def cancel(self, paper_trade_id: str, *, reason: str, idempotency_key: str) -> dict:
        return self._mutate(
            paper_trade_id,
            "paper_order_cancelled",
            {"reason": _required_text(reason, "reason")},
            idempotency_key,
        )

    @_serialized
    def expire(self, paper_trade_id: str, *, reason: str, idempotency_key: str) -> dict:
        return self._mutate(
            paper_trade_id,
            "paper_order_expired",
            {"reason": _required_text(reason, "reason")},
            idempotency_key,
        )

    @_serialized
    def settle(self, paper_trade_id: str, *, winning_outcome: str, idempotency_key: str) -> dict:
        outcome = _required_text(winning_outcome, "winning_outcome").upper()
        if outcome not in {"YES", "NO"}:
            raise ValueError("winning_outcome must be YES or NO")
        return self._mutate(
            paper_trade_id,
            "paper_trade_settled",
            {"winning_outcome": outcome},
            idempotency_key,
        )

    @_serialized
    def get(self, paper_trade_id: str) -> dict:
        events = self.store.load_events(paper_trade_id)
        if not events:
            raise KeyError(f"R12 paper trade not found: {paper_trade_id}")
        return replay_paper_events(events)

    def _mutate(self, paper_trade_id: str, event_type: str, payload: dict, idempotency_key: str) -> dict:
        key = _required_text(idempotency_key, "idempotency_key")
        events = self.store.load_events(paper_trade_id)
        if not events:
            raise KeyError(f"R12 paper trade not found: {paper_trade_id}")
        replayed = _idempotent_replay(events, event_type, payload, key)
        if replayed is not None:
            return replayed
        trade = replay_paper_events(events)
        _validate_command_against_trade(trade, event_type, payload)
        event = _new_event(paper_trade_id, event_type, payload, key, events)
        self.store.append(event)
        return replay_paper_events([*events, event])


def replay_paper_events(events: list[dict]) -> dict:
    """Verify the hash chain and rebuild the complete trade projection."""
    if not isinstance(events, list) or not events:
        raise ValueError("paper ledger requires at least one event")
    previous_hash = None
    paper_trade_id = None
    projection = None
    termination = None
    settlement = None
    marks: dict[str, float] = {}

    for expected_sequence, event in enumerate(events, start=1):
        _validate_event(event, expected_sequence, previous_hash)
        if paper_trade_id is None:
            paper_trade_id = event["paper_trade_id"]
        elif event.get("paper_trade_id") != paper_trade_id:
            raise ValueError("paper ledger mixes multiple paper_trade_id values")
        previous_hash = event["event_hash"]
        event_type = event["event_type"]
        payload = event["payload"]

        if expected_sequence == 1:
            if event_type != "paper_intent_created":
                raise ValueError("first paper ledger event must be paper_intent_created")
            projection = _initial_projection(event)
            continue
        if event_type == "paper_intent_created":
            raise ValueError("paper_intent_created can only be the first event")
        if projection is None:
            raise ValueError("paper projection missing creation event")

        if event_type == "paper_fill_recorded":
            leg = _projection_leg(projection, payload.get("leg_id"))
            leg["fills"].append(
                {
                    "event_id": event["event_id"],
                    "quantity": payload["quantity"],
                    "price": payload["price"],
                    "fee": payload["fee"],
                }
            )
        elif event_type == "paper_marks_updated":
            marks.update(payload["marks"])
        elif event_type in {"paper_order_cancelled", "paper_order_expired"}:
            termination = {"type": event_type, "reason": payload["reason"], "event_id": event["event_id"]}
        elif event_type == "paper_trade_settled":
            settlement = {"winning_outcome": payload["winning_outcome"], "event_id": event["event_id"]}
        else:
            raise ValueError(f"unsupported paper ledger event_type: {event_type}")

    if projection is None:
        raise ValueError("paper projection missing creation event")
    _derive_projection(projection, events, marks, termination, settlement)
    return projection


def evaluate_r12_paper_trade(trade: dict) -> dict:
    events = trade.get("events") if isinstance(trade, dict) else None
    replayed = replay_paper_events(events)
    pnl = replayed["pnl"]
    expected_realized = None
    if replayed.get("settlement"):
        expected_realized = _rounded(pnl["settlement_payoff"] - pnl["acquisition_cost"])
    checks = {
        "append_only_hash_chain_valid": replayed["event_count"] == len(events),
        "agent_run_and_e1_lineage_present": bool(replayed.get("source_run_id"))
        and bool(replayed.get("execution_quote_fingerprint")),
        "creation_has_no_automatic_fill": events[0]["event_type"] == "paper_intent_created"
        and all(not leg["fills"] for leg in _initial_projection(events[0])["legs"]),
        "partial_fill_not_treated_as_locked": not (
            replayed["risk"]["leg_risk_quantity"] > EPS and replayed["risk"]["fully_hedged"]
        ),
        "realized_pnl_is_settlement_payoff_minus_cost": expected_realized is None
        or replayed["pnl"]["realized_pnl"] == expected_realized,
        "automatic_execution_disabled": replayed["guardrails"]["automatic_execution"] is False,
    }
    return {
        "artifact_type": "r12_paper_trade_eval",
        "paper_trade_id": replayed["paper_trade_id"],
        "checks": checks,
        "passed": all(checks.values()),
    }


def _paper_intent_payload(run: dict, opportunity_id: str) -> dict:
    if not isinstance(run, dict) or run.get("artifact_type") != "r12_strategy_agent_run":
        raise ValueError("run must be an r12_strategy_agent_run")
    if run.get("status") != "COMPLETED_PAPER_QUOTE":
        raise ValueError("paper intent requires COMPLETED_PAPER_QUOTE")
    opportunity_id = _required_text(opportunity_id, "opportunity_id")
    quote = (run.get("results") or {}).get("E1")
    if not isinstance(quote, dict) or quote.get("artifact_type") != "r12_execution_quality_scan":
        raise ValueError("completed run is missing E1 execution quote")
    opportunities = quote.get("opportunities") or []
    opportunity = next((row for row in opportunities if row.get("opportunity_id") == opportunity_id), None)
    if opportunity is None:
        raise ValueError("opportunity_id is not an eligible E1 paper signal in this run")
    if not opportunity.get("eligible_for_paper_signal"):
        raise ValueError("opportunity is not eligible for a paper intent")
    basket = ((opportunity.get("market_view") or {}).get("execution_quote") or {})
    legs = basket.get("legs") or []
    target = _positive_number(basket.get("target_contracts"), "quoted target_contracts")
    if len(legs) != 2 or {row.get("provider") for row in legs} != {"kalshi", "polymarket"}:
        raise ValueError("paper complement intent requires exactly one Kalshi and one Polymarket leg")
    if {str(row.get("outcome")).upper() for row in legs} != {"YES", "NO"}:
        raise ValueError("paper complement intent requires reciprocal YES and NO legs")
    if not basket.get("full_fill_at_target") or not basket.get("eligible_for_paper_signal"):
        raise ValueError("paper intent requires a fully quoted eligible basket")

    intent_legs = []
    for row in legs:
        provider = row["provider"]
        outcome = str(row["outcome"]).upper()
        if not row.get("full_fill") or abs(_positive_number(row.get("filled_quantity"), f"{provider} quoted fill") - target) > EPS:
            raise ValueError("paper intent requires each quoted leg to fill the complete target")
        intent_legs.append(
            {
                "leg_id": f"{provider}:{outcome}",
                "provider": provider,
                "outcome": outcome,
                "target_quantity": target,
                "quoted_vwap": _probability_price(row.get("vwap"), f"{provider} quoted_vwap"),
                "quoted_notional": _non_negative_number(row.get("notional"), f"{provider} quoted_notional"),
                "quoted_fee": _non_negative_number(row.get("fee"), f"{provider} quoted_fee"),
            }
        )
    intent_legs.sort(key=lambda row: row["leg_id"])
    return {
        "source_run_id": run["run_id"],
        "opportunity_id": opportunity_id,
        "identity_id": quote.get("identity_id"),
        "execution_quote_fingerprint": _fingerprint(quote),
        "opportunity_fingerprint": _fingerprint(opportunity),
        "target_quantity": target,
        "quoted_net_edge_total": basket.get("net_edge_total"),
        "legs": intent_legs,
        "execution_policy": "MANUAL_PAPER_FILLS_ONLY_NO_AUTO_EXECUTION",
    }


def _initial_projection(event: dict) -> dict:
    payload = event["payload"]
    return {
        "artifact_type": "r12_paper_trade",
        "schema_version": SCHEMA_VERSION,
        "paper_trade_id": event["paper_trade_id"],
        "source_run_id": payload["source_run_id"],
        "opportunity_id": payload["opportunity_id"],
        "identity_id": payload.get("identity_id"),
        "execution_quote_fingerprint": payload["execution_quote_fingerprint"],
        "opportunity_fingerprint": payload["opportunity_fingerprint"],
        "target_quantity": payload["target_quantity"],
        "quoted_net_edge_total": payload.get("quoted_net_edge_total"),
        "legs": [
            {**deepcopy(row), "fills": [], "filled_quantity": 0.0, "average_fill_price": None, "fill_notional": 0.0, "fees": 0.0, "mark": None}
            for row in payload["legs"]
        ],
        "status": "PENDING_PAPER_FILL",
        "risk": {},
        "pnl": {},
        "settlement": None,
        "termination": None,
        "events": [],
        "event_count": 0,
        "guardrails": {
            "automatic_execution": False,
            "exchange_credentials_present": False,
            "fills_are_explicit_simulated_commands": True,
            "partial_fill_is_locked_arbitrage": False,
            "idempotency_key_required_for_mutations": True,
            "append_only_hash_chain": True,
        },
    }


def _derive_projection(projection: dict, events: list[dict], marks: dict, termination: dict | None, settlement: dict | None) -> None:
    quantities = []
    acquisition_cost = 0.0
    marked_value = 0.0
    marks_complete = True
    settlement_payoff = 0.0

    for leg in projection["legs"]:
        quantity = sum(float(fill["quantity"]) for fill in leg["fills"])
        notional = sum(float(fill["quantity"]) * float(fill["price"]) for fill in leg["fills"])
        fees = sum(float(fill["fee"]) for fill in leg["fills"])
        leg["filled_quantity"] = _rounded(quantity)
        leg["fill_notional"] = _rounded(notional)
        leg["fees"] = _rounded(fees)
        leg["average_fill_price"] = _rounded(notional / quantity) if quantity > EPS else None
        leg["remaining_quantity"] = _rounded(max(0.0, float(leg["target_quantity"]) - quantity))
        leg["mark"] = marks.get(leg["leg_id"])
        leg["unrealized_pnl"] = None
        quantities.append(quantity)
        acquisition_cost += notional + fees
        if quantity > EPS:
            if leg["mark"] is None:
                marks_complete = False
            else:
                marked_value += quantity * float(leg["mark"])
                leg["unrealized_pnl"] = _rounded(quantity * float(leg["mark"]) - notional - fees)
        if settlement and leg["outcome"] == settlement["winning_outcome"]:
            settlement_payoff += quantity

    matched = min(quantities)
    leg_risk = max(quantities) - matched
    fully_matched = all(abs(quantity - float(projection["target_quantity"])) <= EPS for quantity in quantities)
    fully_hedged = leg_risk <= EPS and matched > EPS
    projection["risk"] = {
        "matched_quantity": _rounded(matched),
        "leg_risk_quantity": _rounded(leg_risk),
        "fully_hedged": fully_hedged,
        "fully_matched_target": fully_matched,
        "remaining_unfilled_by_leg": {
            leg["leg_id"]: leg["remaining_quantity"] for leg in projection["legs"]
        },
    }
    projection["pnl"] = {
        "acquisition_cost": _rounded(acquisition_cost),
        "marked_value": _rounded(marked_value) if marks_complete else None,
        "mark_to_market_pnl": _rounded(marked_value - acquisition_cost) if marks_complete else None,
        "settlement_payoff": _rounded(settlement_payoff) if settlement else None,
        "realized_pnl": _rounded(settlement_payoff - acquisition_cost) if settlement else None,
        "pnl_unit": "settlement_currency",
    }
    projection["termination"] = deepcopy(termination)
    projection["settlement"] = deepcopy(settlement)
    projection["status"] = _projection_status(quantities, projection["target_quantity"], termination, settlement)
    projection["events"] = deepcopy(events)
    projection["event_count"] = len(events)
    projection["last_event_hash"] = events[-1]["event_hash"]
    projection["last_event_id"] = events[-1]["event_id"]


def _projection_status(quantities: list[float], target: float, termination: dict | None, settlement: dict | None) -> str:
    matched = min(quantities)
    leg_risk = max(quantities) - matched
    if settlement:
        return "SETTLED"
    if termination:
        prefix = "CANCELLED" if termination["type"] == "paper_order_cancelled" else "EXPIRED"
        if max(quantities) <= EPS:
            return f"{prefix}_UNFILLED"
        if leg_risk > EPS:
            return f"{prefix}_WITH_LEG_RISK"
        return f"{prefix}_MATCHED"
    if max(quantities) <= EPS:
        return "PENDING_PAPER_FILL"
    if leg_risk > EPS:
        return "PARTIALLY_FILLED_LEG_RISK"
    if all(abs(quantity - float(target)) <= EPS for quantity in quantities):
        return "FULLY_MATCHED"
    return "MATCHED_PARTIAL"


def _validate_command_against_trade(trade: dict, event_type: str, payload: dict) -> None:
    settled = trade.get("settlement") is not None
    terminated = trade.get("termination") is not None
    if settled:
        raise ValueError("paper trade is already settled")
    if event_type == "paper_trade_settled":
        return
    if terminated and event_type != "paper_marks_updated":
        raise ValueError("paper order is cancelled or expired; only marks or settlement remain allowed")
    if event_type == "paper_fill_recorded":
        leg = _projection_leg(trade, payload["leg_id"])
        remaining = float(leg["target_quantity"]) - float(leg["filled_quantity"])
        if float(payload["quantity"]) - remaining > EPS:
            raise ValueError(f"fill exceeds remaining target quantity for {payload['leg_id']}")
    elif event_type == "paper_marks_updated":
        known = {leg["leg_id"] for leg in trade["legs"]}
        unknown = set(payload["marks"]) - known
        if unknown:
            raise ValueError(f"marks contain unknown leg_id: {sorted(unknown)}")
    elif event_type in {"paper_order_cancelled", "paper_order_expired"}:
        if all(float(leg["remaining_quantity"]) <= EPS for leg in trade["legs"]):
            raise ValueError("paper order has no remaining quantity to cancel or expire")
    elif event_type not in {"paper_order_cancelled", "paper_order_expired"}:
        raise ValueError(f"unsupported paper command: {event_type}")


def _idempotent_replay(events: list[dict], event_type: str, payload: dict, key: str) -> dict | None:
    fingerprint = _command_fingerprint(event_type, payload)
    matches = [event for event in events if event.get("idempotency_key") == key]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("duplicate idempotency key found in paper ledger")
    existing = matches[0]
    if existing.get("command_fingerprint") != fingerprint:
        raise ValueError("idempotency key was already used for a different paper command")
    return replay_paper_events(events)


def _new_event(paper_trade_id: str, event_type: str, payload: dict, key: str, events: list[dict]) -> dict:
    sequence = len(events) + 1
    event = {
        "schema_version": SCHEMA_VERSION,
        "event_id": f"{paper_trade_id}-E{sequence:04d}",
        "paper_trade_id": paper_trade_id,
        "sequence": sequence,
        "event_type": event_type,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "idempotency_key": key,
        "command_fingerprint": _command_fingerprint(event_type, payload),
        "previous_event_hash": events[-1]["event_hash"] if events else None,
        "payload": deepcopy(payload),
    }
    event["event_hash"] = _fingerprint(event)
    return event


def _validate_event(event: dict, expected_sequence: int, previous_hash: str | None) -> None:
    if not isinstance(event.get("paper_trade_id"), str) or not TRADE_ID_RE.fullmatch(event["paper_trade_id"]):
        raise ValueError("invalid paper_trade_id in ledger event")
    if not isinstance(event.get("payload"), dict):
        raise ValueError("paper ledger event payload must be an object")
    _required_text(event.get("idempotency_key"), "paper ledger idempotency_key")
    if event.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported paper ledger schema_version")
    if event.get("sequence") != expected_sequence:
        raise ValueError("paper ledger sequence is not contiguous")
    if event.get("previous_event_hash") != previous_hash:
        raise ValueError("paper ledger previous_event_hash mismatch")
    expected_id = f"{event.get('paper_trade_id')}-E{expected_sequence:04d}"
    if event.get("event_id") != expected_id:
        raise ValueError("paper ledger event_id mismatch")
    unsigned = {key: value for key, value in event.items() if key != "event_hash"}
    if event.get("event_hash") != _fingerprint(unsigned):
        raise ValueError("paper ledger event hash mismatch")
    if event.get("command_fingerprint") != _command_fingerprint(event.get("event_type"), event.get("payload")):
        raise ValueError("paper ledger command fingerprint mismatch")


def _projection_leg(trade: dict, leg_id: str) -> dict:
    for leg in trade.get("legs") or []:
        if leg.get("leg_id") == leg_id:
            return leg
    raise ValueError(f"unknown paper leg_id: {leg_id}")


def _command_fingerprint(event_type: str, payload: dict) -> str:
    return _fingerprint({"event_type": event_type, "payload": payload})


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be finite")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _positive_number(value: Any, label: str) -> float:
    number = _number(value, label)
    if number <= 0:
        raise ValueError(f"{label} must be > 0")
    return _rounded(number)


def _non_negative_number(value: Any, label: str) -> float:
    number = _number(value, label)
    if number < 0:
        raise ValueError(f"{label} must be non-negative")
    return _rounded(number)


def _probability_price(value: Any, label: str) -> float:
    number = _number(value, label)
    if not 0 <= number <= 1:
        raise ValueError(f"{label} must be between 0 and 1")
    return _rounded(number)


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(float(value), 8)
