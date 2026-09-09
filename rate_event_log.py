"""Durable, ordered NDJSON event log for replaying Agent runs."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path


class EventLogError(ValueError):
    pass


class RateEventLog:
    """Append stream envelopes before delivery so a client can replay them."""

    def __init__(self, directory: str | os.PathLike[str]):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, run_id: str) -> Path:
        if not isinstance(run_id, str) or not run_id or "/" in run_id or "\\" in run_id:
            raise EventLogError("invalid run_id")
        return self.directory / f"{run_id}.jsonl"

    def append(self, message: dict) -> dict:
        if not isinstance(message, dict) or message.get("protocol") != "rate-ndjson-v1":
            raise EventLogError("event log only accepts rate-ndjson-v1 envelopes")
        run_id = message.get("run_id")
        message_type = message.get("type")
        if message_type not in {"start", "event", "result", "error"}:
            raise EventLogError(f"unsupported message type: {message_type}")
        path = self._path(run_id)
        with self._lock:
            existing = self._read_path(path)
            if message_type == "start" and existing:
                if existing[0] == message:
                    return message
                raise EventLogError("duplicate stream start")
            if existing and existing[-1].get("type") in {"result", "error"}:
                if existing[-1] == message:
                    return message
                raise EventLogError("terminal stream already persisted")
            if message_type == "event":
                event = message.get("event") or {}
                sequence = event.get("sequence")
                expected = sum(1 for item in existing if item.get("type") == "event") + 1
                if sequence != expected:
                    raise EventLogError(f"event sequence {sequence} is not {expected}")
            elif message_type in {"result", "error"} and not existing:
                raise EventLogError("terminal message requires a persisted start")
            payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"
            with path.open("a", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        return message

    def _read_path(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        messages: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                messages.append(json.loads(line))
        return messages

    def read(self, run_id: str, after_sequence: int = 0) -> list[dict]:
        if not isinstance(after_sequence, int) or isinstance(after_sequence, bool) or after_sequence < 0:
            raise EventLogError("after_sequence must be a non-negative integer")
        with self._lock:
            messages = self._read_path(self._path(run_id))
        if not messages:
            return []
        selected = [messages[0]]
        selected.extend(
            item for item in messages[1:]
            if item.get("type") != "event" or (item.get("event") or {}).get("sequence", 0) > after_sequence
        )
        return selected

    def snapshot(self, run_id: str) -> dict:
        messages = self.read(run_id)
        return {
            "run_id": run_id,
            "message_count": len(messages),
            "event_count": sum(1 for item in messages if item.get("type") == "event"),
            "terminal": messages[-1].get("type") in {"result", "error"} if messages else False,
        }
