"""Small durable command boundary for the Rate Agent teaching demos."""

from __future__ import annotations

import json
import os
from pathlib import Path


class RateIdempotencyStore:
    """Persist one result per idempotency key and deduplicate retries."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def execute_once(self, idempotency_key: str, command: dict) -> dict:
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError("idempotency_key must be a non-empty string")
        safe = "".join(ch for ch in idempotency_key if ch.isalnum() or ch in {"-", "_"})
        if not safe:
            raise ValueError("idempotency_key must contain a safe filename character")
        path = self.directory / f"{safe}.json"
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                record = json.load(handle)
            return {"status": "DEDUPLICATED", "applied": False, "record": record}
        record = {
            "idempotency_key": idempotency_key,
            "command": command,
            "status": "APPLIED",
            "effect_count": 1,
        }
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        return {"status": "APPLIED", "applied": True, "record": record}

