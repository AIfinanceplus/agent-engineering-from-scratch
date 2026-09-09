"""Durable outbox and idempotent side-effect sink for the teaching runtime."""

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
from threading import Lock


class OutboxError(RuntimeError):
    pass


class OutboxCrash(OutboxError):
    """Teaching-only crash window: the sink applied, but the ack was lost."""


class OutboxFenced(OutboxError):
    pass


def _atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class IdempotentEffectSink:
    """A target that applies each idempotency key at most once."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def apply(self, idempotency_key, command):
        safe = "".join(ch for ch in idempotency_key if ch.isalnum() or ch in "-_")
        if safe != idempotency_key or not safe:
            raise ValueError("idempotency_key must contain only safe filename characters")
        path = self.directory / f"{safe}.json"
        with self._lock:
            if path.exists():
                record = json.loads(path.read_text(encoding="utf-8"))
                return {"applied": False, "effect_count": 1, "record": record}
            record = {"idempotency_key": idempotency_key, "command": deepcopy(command),
                      "effect_count": 1, "status": "APPLIED"}
            _atomic_json(path, record)
            return {"applied": True, "effect_count": 1, "record": record}


class OutboxStore:
    """Persist commands before sending them; delivery is intentionally at-least-once."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def _path(self, idempotency_key):
        safe = "".join(ch for ch in idempotency_key if ch.isalnum() or ch in "-_")
        if safe != idempotency_key or not safe:
            raise ValueError("idempotency_key must contain only safe filename characters")
        return self.directory / f"{safe}.json"

    def enqueue(self, idempotency_key, command, *, fencing_token):
        path = self._path(idempotency_key)
        with self._lock:
            if path.exists():
                existing = json.loads(path.read_text(encoding="utf-8"))
                if existing["command"] != command:
                    raise ValueError("idempotency key is already bound to another command")
                return {"status": "ALREADY_ENQUEUED", "record": existing}
            record = {"idempotency_key": idempotency_key, "command": deepcopy(command),
                      "fencing_token": fencing_token, "status": "PENDING", "attempts": 0}
            _atomic_json(path, record)
            return {"status": "ENQUEUED", "record": deepcopy(record)}

    def dispatch(self, idempotency_key, *, owner, fencing_token, sink, fence_check=None,
                 crash_after_apply=False):
        path = self._path(idempotency_key)
        with self._lock:
            if not path.exists():
                raise OutboxError("outbox record not found")
            record = json.loads(path.read_text(encoding="utf-8"))
            record["attempts"] += 1
            _atomic_json(path, record)
        if fence_check:
            try:
                fence_check(owner, fencing_token)
            except Exception as exc:
                raise OutboxFenced(str(exc)) from exc
        result = sink.apply(idempotency_key, record["command"])
        if crash_after_apply:
            raise OutboxCrash("sink applied effect but acknowledgement was lost")
        record["status"] = "ACKNOWLEDGED"
        record["owner"] = owner
        record["last_result"] = deepcopy(result)
        with self._lock:
            _atomic_json(path, record)
        return {"status": "DEDUPLICATED" if not result["applied"] else "APPLIED",
                "applied": result["applied"], "record": record, "sink": result}

    def snapshot(self, idempotency_key):
        path = self._path(idempotency_key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
