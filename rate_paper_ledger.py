"""Small append-only paper ledger used by the reconciliation lesson.

The strategy result is not treated as the source of truth.  LG1 writes a
paper intent, fill and close event, then rebuilds a projection from those
events and compares it with S1.  This is deliberately paper-only: there is no
broker client, account, or order-placement method in this module.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "rate.paper-ledger.v1"


class PaperLedger:
    """Durable JSONL ledger with idempotent event keys and a hash chain."""

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def events(self) -> list[dict]:
        if not self.path.exists():
            return []
        rows = []
        for line_number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid paper ledger JSON at line {line_number}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"invalid paper ledger event at line {line_number}")
            rows.append(row)
        return rows

    def append(self, event_type: str, payload: dict, *, idempotency_key: str) -> dict:
        if not event_type or not isinstance(payload, dict) or not idempotency_key:
            raise ValueError("event_type, payload and idempotency_key are required")
        existing = self.events()
        for row in existing:
            if row.get("idempotency_key") == idempotency_key:
                if row.get("event_type") != event_type or row.get("payload") != payload:
                    raise ValueError("idempotency key was reused with a different paper command")
                return deepcopy(row)
        previous_hash = existing[-1]["event_hash"] if existing else None
        row = {
            "sequence": len(existing) + 1,
            "event_type": event_type,
            "idempotency_key": idempotency_key,
            "payload": deepcopy(payload),
            "previous_hash": previous_hash,
        }
        row["event_hash"] = hashlib.sha256(
            json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        encoded = json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
        descriptor = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(descriptor, encoded.encode("utf-8"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return deepcopy(row)

    def replay(self) -> dict:
        rows = self.events()
        if not rows:
            raise ValueError("paper ledger is empty")
        previous_hash = None
        projection: dict[str, Any] = {"paper_trade_id": None, "status": "UNKNOWN"}
        for expected_sequence, row in enumerate(rows, 1):
            if row.get("sequence") != expected_sequence or row.get("previous_hash") != previous_hash:
                raise ValueError("paper ledger sequence or hash chain is invalid")
            material = {key: row[key] for key in ("sequence", "event_type", "idempotency_key", "payload", "previous_hash")}
            expected_hash = hashlib.sha256(
                json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            if row.get("event_hash") != expected_hash:
                raise ValueError("paper ledger event hash is invalid")
            previous_hash = row["event_hash"]
            payload = row.get("payload") or {}
            if projection.get("paper_trade_id") and payload.get("paper_trade_id") not in {None, projection["paper_trade_id"]}:
                raise ValueError("paper ledger event references a different paper_trade_id")
            if row["event_type"] == "paper_intent_created":
                projection.update({"paper_trade_id": payload["paper_trade_id"], "action": payload["action"], "status": "INTENT_CREATED"})
            elif row["event_type"] == "paper_fill_recorded":
                projection.update({"entry_spread_bps": payload["entry_spread_bps"], "exit_spread_bps": payload["exit_spread_bps"], "gross_pnl_usd": payload["gross_pnl_usd"], "cost_usd": payload["cost_usd"], "status": "FILLED"})
            elif row["event_type"] == "paper_trade_closed":
                projection.update({"net_pnl_usd": payload["net_pnl_usd"], "status": "CLOSED"})
            else:
                raise ValueError(f"unsupported paper ledger event_type: {row['event_type']}")
        projection.update({"event_count": len(rows), "last_event_hash": previous_hash, "schema_version": SCHEMA_VERSION})
        return projection

    def reconcile(self, simulation: dict, *, tamper: bool = False, on_append=None) -> dict:
        trade = simulation.get("completed_trade") or {}
        if not trade.get("paper_trade_id"):
            raise ValueError("simulation is missing completed paper trade")
        trade_id = trade["paper_trade_id"]
        row = self.append("paper_intent_created", {
            "paper_trade_id": trade_id, "action": trade["action"],
            "source": "S1.completed_trade", "automatic_execution": False,
        }, idempotency_key=f"{trade_id}:intent")
        if on_append:
            on_append(row)
        row = self.append("paper_fill_recorded", {
            "paper_trade_id": trade_id, "entry_spread_bps": trade["entry_spread_bps"],
            "exit_spread_bps": trade["exit_spread_bps"], "gross_pnl_usd": trade["gross_pnl_usd"],
            "cost_usd": trade["cost_usd"],
        }, idempotency_key=f"{trade_id}:fill")
        if on_append:
            on_append(row)
        closed_net = round(float(trade["net_pnl_usd"]) + (1.0 if tamper else 0.0), 2)
        row = self.append("paper_trade_closed", {"paper_trade_id": trade_id, "net_pnl_usd": closed_net}, idempotency_key=f"{trade_id}:close")
        if on_append:
            on_append(row)
        replayed = self.replay()
        differences = []
        for field in ("paper_trade_id", "action", "entry_spread_bps", "exit_spread_bps", "gross_pnl_usd", "cost_usd", "net_pnl_usd"):
            expected = trade.get(field)
            actual = replayed.get(field)
            if expected != actual:
                differences.append({"field": field, "expected": expected, "replayed": actual})
        return {
            "artifact_type": "rate_paper_ledger_reconciliation", "schema_version": SCHEMA_VERSION,
            "passed": not differences, "status": "RECONCILED" if not differences else "MISMATCH",
            "differences": differences, "expected": {field: trade.get(field) for field in ("paper_trade_id", "action", "entry_spread_bps", "exit_spread_bps", "gross_pnl_usd", "cost_usd", "net_pnl_usd")},
            "replayed": replayed, "events": self.events(),
            "guardrails": {"paper_only": True, "real_orders_created": False, "source_of_truth": "append_only_event_replay", "automatic_execution": False},
        }
