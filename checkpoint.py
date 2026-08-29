"""V8 durable checkpoint storage.

JsonCheckpointStore persists AgentState snapshots to disk so a fresh Python
process can load the latest safe checkpoint. Writes use os.replace so the
checkpoint file is replaced atomically on the local filesystem.

Important: persistence does not create exactly-once side effects. If a process
crashes after a real side effect but before the post-effect checkpoint is
written, the Runtime may not know whether that effect happened. V8 therefore
demonstrates recovery from an Observation that was already checkpointed.
"""

import hashlib
import json
import os
from pathlib import Path

from state import AgentState, StateStore


class JsonCheckpointStore(StateStore):
    """Small file-backed StateStore used to teach crash recovery."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, task_id: str) -> Path:
        digest = hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:24]
        return self.directory / f"{digest}.json"

    def save(self, state: AgentState, *, reason: str) -> None:
        if not isinstance(state, AgentState):
            raise TypeError("state must be an AgentState")

        path = self._path(state.task_id)
        existing = self._read_document(path)
        history = existing.get("history", []) if existing else []
        snapshot = state.to_dict()
        history.append({"reason": reason, "state": snapshot})

        document = {
            "version": 1,
            "task_id": state.task_id,
            "latest": snapshot,
            "history": history,
        }
        self._atomic_write(path, document)

    def load(self, task_id: str) -> AgentState | None:
        document = self._read_document(self._path(task_id))
        if not document:
            return None
        if document.get("task_id") != task_id:
            raise RuntimeError("Checkpoint task_id mismatch")
        return AgentState.from_dict(document["latest"])

    def history(self, task_id: str) -> list[dict]:
        document = self._read_document(self._path(task_id))
        return list(document.get("history", [])) if document else []

    def clear(self, task_id: str) -> None:
        path = self._path(task_id)
        if path.exists():
            path.unlink()

    def exists(self, task_id: str) -> bool:
        return self._path(task_id).exists()

    def checkpoint_path(self, task_id: str) -> str:
        return str(self._path(task_id))

    @staticmethod
    def _read_document(path: Path) -> dict | None:
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _atomic_write(path: Path, document: dict) -> None:
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
