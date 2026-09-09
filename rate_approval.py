"""Thread-safe, one-shot human approval rendezvous for the teaching server."""

from copy import deepcopy
import json
import os
from pathlib import Path
from threading import Condition
import tempfile
import time


class ApprovalUnavailable(RuntimeError):
    pass


class ApprovalRegistry:
    def __init__(self, directory=None):
        self._condition = Condition()
        self._requests = {}
        self.directory = Path(directory) if directory else None
        if self.directory:
            self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id):
        if not self.directory:
            return None
        safe = "".join(ch for ch in run_id if ch.isalnum() or ch in "-_")
        if safe != run_id or not safe:
            raise ValueError("invalid run_id for durable approval")
        return self.directory / f"{safe}.json"

    def _persist(self, run_id, row):
        path = self._path(run_id)
        if not path:
            return
        payload = json.dumps(row, sort_keys=True, separators=(",", ":")).encode()
        fd, temporary = tempfile.mkstemp(prefix=f".{run_id}-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
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

    def _load(self, run_id):
        path = self._path(run_id)
        if not path or not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def await_decision(self, run_id, request, *, timeout_seconds=90, check=None, on_ready=None):
        deadline = time.monotonic() + timeout_seconds
        with self._condition:
            if run_id in self._requests:
                raise ApprovalUnavailable("approval request already exists for run")
            self._requests[run_id] = {"request": deepcopy(request), "decision": None,
                                      "resolved_by": None}
            self._persist(run_id, self._requests[run_id])
            if on_ready:
                on_ready()
            while self._requests[run_id]["decision"] is None:
                if check:
                    check()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._requests[run_id]["decision"] = "timeout"
                    self._persist(run_id, self._requests[run_id])
                    break
                self._condition.wait(min(0.1, remaining))
            return deepcopy(self._requests[run_id])

    def decide(self, run_id, decision, *, actor="human_ui"):
        if decision not in {"approve", "deny"}:
            raise ValueError("decision must be approve or deny")
        with self._condition:
            row = self._requests.get(run_id)
            if row is None:
                row = self._load(run_id)
                if row is not None:
                    self._requests[run_id] = row
            if row is None:
                return {"accepted": False, "reason": "approval_request_not_found"}
            if row["decision"] is not None:
                return {"accepted": False, "reason": "approval_already_resolved",
                        "decision": row["decision"]}
            row["decision"] = decision
            row["resolved_by"] = actor
            self._persist(run_id, row)
            self._condition.notify_all()
            return {"accepted": True, "decision": decision,
                    "approval_id": row["request"]["approval_id"]}

    def discard(self, run_id):
        with self._condition:
            self._requests.pop(run_id, None)

    def snapshot(self, run_id):
        with self._condition:
            return deepcopy(self._requests.get(run_id) or self._load(run_id))

    def restart_and_restore(self, run_id):
        if not self.directory:
            raise ApprovalUnavailable("durable approval directory is not configured")
        fresh_process_registry = ApprovalRegistry(self.directory)
        restored = fresh_process_registry.snapshot(run_id)
        if restored is None:
            raise ApprovalUnavailable("durable approval checkpoint not found")
        return restored
