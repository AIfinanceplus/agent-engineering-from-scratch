"""Deterministic paper execution state machine for the partial-fill lesson.

This module models the facts that matter after a strategy emits an order:
acceptance, fills, cancel intent, a cancel acknowledgement, and duplicate
fills. It is paper-only and has no broker or order-placement integration.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "rate.execution.v1"


class ExecutionError(ValueError):
    pass


@dataclass
class PaperOrder:
    order_id: str
    requested_quantity: int
    state: str = "NEW"
    filled_quantity: int = 0
    canceled_quantity: int = 0
    seen_fill_ids: set[str] = field(default_factory=set)

    @property
    def remaining_quantity(self) -> int:
        return self.requested_quantity - self.filled_quantity - self.canceled_quantity

    def snapshot(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "requested_quantity": self.requested_quantity,
            "filled_quantity": self.filled_quantity,
            "canceled_quantity": self.canceled_quantity,
            "remaining_quantity": self.remaining_quantity,
            "state": self.state,
            "seen_fill_ids": sorted(self.seen_fill_ids),
        }


class PaperExecutionTracker:
    """Append-only, replayable state machine for one paper order."""

    def __init__(self, order_id: str, requested_quantity: int, *, path: str | Path | None = None):
        if not isinstance(order_id, str) or not order_id:
            raise ExecutionError("order_id is required")
        if isinstance(requested_quantity, bool) or not isinstance(requested_quantity, int) or requested_quantity <= 0:
            raise ExecutionError("requested_quantity must be a positive integer")
        self.order = PaperOrder(order_id, requested_quantity)
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._events: list[dict[str, Any]] = []

    @classmethod
    def from_events(cls, events: list[dict[str, Any]], *, path: str | Path | None = None) -> "PaperExecutionTracker":
        if not events or events[0].get("event") != "order_accepted":
            raise ExecutionError("event stream must start with order_accepted")
        first = events[0]
        tracker = cls(first["order_id"], (first.get("payload") or {}).get("requested_quantity"), path=path)
        for event in events:
            tracker._apply(event, persist=False, verify=True)
            tracker._events.append(deepcopy(event))
        return tracker

    def _append(self, event: dict[str, Any]) -> dict[str, Any]:
        event = deepcopy(event)
        event["schema_version"] = SCHEMA_VERSION
        event["sequence"] = len(self._events) + 1
        event["previous_hash"] = self._events[-1]["event_hash"] if self._events else None
        material = {key: event[key] for key in ("schema_version", "sequence", "event", "order_id", "payload", "previous_hash")}
        event["event_hash"] = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if self.path:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush()
        self._events.append(event)
        return deepcopy(event)

    def _emit(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        row = {"event": event, "order_id": self.order.order_id, "payload": payload}
        self._apply(row, persist=False, verify=False)
        return self._append(row)

    def _apply(self, row: dict[str, Any], *, persist: bool, verify: bool) -> None:
        event = row.get("event")
        payload = row.get("payload") or {}
        if row.get("order_id") != self.order.order_id:
            raise ExecutionError("event references another order")
        if event == "order_accepted":
            if self._events:
                raise ExecutionError("order can only be accepted once")
            self.order.state = "WORKING"
        elif event == "fill_recorded":
            fill_id = payload.get("fill_id")
            quantity = payload.get("quantity")
            if not isinstance(fill_id, str) or not fill_id:
                raise ExecutionError("fill_id is required")
            if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
                raise ExecutionError("fill quantity must be a positive integer")
            if fill_id in self.order.seen_fill_ids:
                return
            if quantity > self.order.remaining_quantity:
                raise ExecutionError("fill quantity exceeds remaining order quantity")
            self.order.seen_fill_ids.add(fill_id)
            self.order.filled_quantity += quantity
            self.order.state = "FILLED" if self.order.remaining_quantity == 0 else "PARTIALLY_FILLED"
        elif event == "fill_deduplicated":
            fill_id = payload.get("fill_id")
            if fill_id not in self.order.seen_fill_ids:
                raise ExecutionError("deduplicated fill was never recorded")
        elif event == "cancel_requested":
            if self.order.state not in {"WORKING", "PARTIALLY_FILLED", "CANCEL_PENDING"}:
                raise ExecutionError("cancel request is invalid for terminal order")
            if self.order.remaining_quantity == 0:
                self.order.state = "FILLED"
            else:
                self.order.state = "CANCEL_PENDING"
        elif event == "cancel_confirmed":
            if self.order.state not in {"CANCEL_PENDING", "WORKING", "PARTIALLY_FILLED"}:
                raise ExecutionError("cancel confirmation is invalid for terminal order")
            self.order.canceled_quantity = self.order.remaining_quantity
            self.order.state = "CANCELED" if self.order.canceled_quantity else "FILLED"
        elif event == "cancel_noop":
            if self.order.remaining_quantity != 0:
                raise ExecutionError("cancel_noop requires no remaining quantity")
        else:
            raise ExecutionError(f"unsupported execution event: {event}")

    def accept(self) -> dict[str, Any]:
        if self._events:
            raise ExecutionError("order already accepted")
        return self._emit("order_accepted", {"requested_quantity": self.order.requested_quantity})

    def record_fill(self, fill_id: str, quantity: int) -> dict[str, Any]:
        if self.order.state == "NEW":
            raise ExecutionError("order must be accepted before a fill")
        if fill_id in self.order.seen_fill_ids:
            prior = next((event for event in self._events
                          if event["event"] == "fill_recorded"
                          and event["payload"].get("fill_id") == fill_id), None)
            if prior and prior["payload"].get("quantity") != quantity:
                raise ExecutionError("fill_id is already bound to another quantity")
            return self._emit("fill_deduplicated", {"fill_id": fill_id, "quantity": quantity})
        return self._emit("fill_recorded", {"fill_id": fill_id, "quantity": quantity})

    def request_cancel(self) -> dict[str, Any]:
        if self.order.remaining_quantity == 0:
            return self._emit("cancel_noop", {"reason": "already_filled"})
        return self._emit("cancel_requested", {"remaining_quantity": self.order.remaining_quantity})

    def confirm_cancel(self) -> dict[str, Any]:
        return self._emit("cancel_confirmed", {"remaining_quantity": self.order.remaining_quantity})

    def events(self) -> list[dict[str, Any]]:
        return deepcopy(self._events)

    def snapshot(self) -> dict[str, Any]:
        return {"artifact_type": "paper_execution_projection", "schema_version": SCHEMA_VERSION,
                **self.order.snapshot(), "event_count": len(self._events),
                "last_event_hash": self._events[-1]["event_hash"] if self._events else None,
                "guardrails": {"paper_only": True, "real_orders_created": False,
                                "automatic_execution": False}}


def replay_execution(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise ExecutionError("execution event log not found")
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    previous_hash = None
    for expected_sequence, event in enumerate(events, 1):
        if event.get("sequence") != expected_sequence or event.get("previous_hash") != previous_hash:
            raise ExecutionError("execution sequence or hash chain is invalid")
        material = {key: event[key] for key in ("schema_version", "sequence", "event", "order_id", "payload", "previous_hash")}
        expected_hash = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if event.get("event_hash") != expected_hash:
            raise ExecutionError("execution event hash is invalid")
        previous_hash = event["event_hash"]
    return PaperExecutionTracker.from_events(events, path=path).snapshot()


def partial_fill_cancel_race_demo() -> dict[str, Any]:
    """The canonical lesson: 30 fill, cancel request, late 20 fill, cancel rest."""
    tracker = PaperExecutionTracker("ORDER-RACE-1", 100)
    tracker.accept()
    tracker.record_fill("FILL-1", 30)
    tracker.request_cancel()
    tracker.record_fill("FILL-2", 20)
    tracker.record_fill("FILL-2", 20)
    tracker.confirm_cancel()
    return {"artifact_type": "partial_fill_cancel_race_demo", "events": tracker.events(), "execution": tracker.snapshot()}
