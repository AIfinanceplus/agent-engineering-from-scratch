"""Durable checkpoints for the teaching Rate Agent.

This store is intentionally small: one atomic JSON document per run plus an
append-only checkpoint history.  It is not a distributed transaction log; its
purpose is to make the recovery boundary explicit and testable.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


class RateCheckpointStore:
    """Atomic local checkpoint store keyed by a stable rate-agent run ID."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        safe = "".join(ch for ch in run_id if ch.isalnum() or ch in {"-", "_"})
        if not safe:
            raise ValueError("run_id must contain a safe filename character")
        return self.directory / f"{safe}.json"

    def save(self, checkpoint: dict) -> str:
        if not isinstance(checkpoint, dict):
            raise TypeError("checkpoint must be a dictionary")
        run_id = checkpoint.get("run_id")
        checkpoint_id = checkpoint.get("checkpoint_id")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("checkpoint.run_id must be a non-empty string")
        if not isinstance(checkpoint_id, str) or not checkpoint_id:
            raise ValueError("checkpoint.checkpoint_id must be a non-empty string")
        path = self._path(run_id)
        existing = self._read(path) or {"version": 1, "run_id": run_id, "history": []}
        history = list(existing.get("history", []))
        history.append(checkpoint)
        document = {"version": 1, "run_id": run_id, "latest": checkpoint, "history": history}
        temp = path.with_suffix(path.suffix + ".tmp")
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        return str(path)

    def load(self, run_id: str) -> dict | None:
        document = self._read(self._path(run_id))
        return document.get("latest") if document else None

    def history(self, run_id: str) -> list[dict]:
        document = self._read(self._path(run_id))
        return list(document.get("history", [])) if document else []

    def clear(self, run_id: str) -> None:
        path = self._path(run_id)
        if path.exists():
            path.unlink()

    def exists(self, run_id: str) -> bool:
        return self._path(run_id).exists()

    def checkpoint_path(self, run_id: str) -> str:
        return str(self._path(run_id))

    @staticmethod
    def _read(path: Path) -> dict | None:
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
