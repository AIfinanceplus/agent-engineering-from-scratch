"""Thread-safe, one-shot human approval rendezvous for the teaching server."""

from copy import deepcopy
from threading import Condition
import time


class ApprovalUnavailable(RuntimeError):
    pass


class ApprovalRegistry:
    def __init__(self):
        self._condition = Condition()
        self._requests = {}

    def await_decision(self, run_id, request, *, timeout_seconds=90, check=None, on_ready=None):
        deadline = time.monotonic() + timeout_seconds
        with self._condition:
            if run_id in self._requests:
                raise ApprovalUnavailable("approval request already exists for run")
            self._requests[run_id] = {"request": deepcopy(request), "decision": None,
                                      "resolved_by": None}
            if on_ready:
                on_ready()
            while self._requests[run_id]["decision"] is None:
                if check:
                    check()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._requests[run_id]["decision"] = "timeout"
                    break
                self._condition.wait(min(0.1, remaining))
            return deepcopy(self._requests[run_id])

    def decide(self, run_id, decision, *, actor="human_ui"):
        if decision not in {"approve", "deny"}:
            raise ValueError("decision must be approve or deny")
        with self._condition:
            row = self._requests.get(run_id)
            if row is None:
                return {"accepted": False, "reason": "approval_request_not_found"}
            if row["decision"] is not None:
                return {"accepted": False, "reason": "approval_already_resolved",
                        "decision": row["decision"]}
            row["decision"] = decision
            row["resolved_by"] = actor
            self._condition.notify_all()
            return {"accepted": True, "decision": decision,
                    "approval_id": row["request"]["approval_id"]}

    def discard(self, run_id):
        with self._condition:
            self._requests.pop(run_id, None)

    def snapshot(self, run_id):
        with self._condition:
            return deepcopy(self._requests.get(run_id))
