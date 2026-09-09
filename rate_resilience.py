"""Small, deterministic resilience primitives used by the teaching Runtime.

The objects own policy state only.  They never call a Tool and never emit UI
events; the Runtime remains the single owner of execution and observability.
"""

from collections import deque
from math import isfinite
import threading
import time


class CircuitOpen(ConnectionError):
    """The Runtime intentionally rejected a Tool call while its circuit is open."""


class CircuitBreaker:
    """Thread-safe CLOSED -> OPEN -> HALF_OPEN -> CLOSED state machine."""

    def __init__(self, failure_threshold=2, reset_timeout_ms=500, *, clock=time.monotonic):
        if isinstance(failure_threshold, bool) or not isinstance(failure_threshold, int) or failure_threshold < 1:
            raise ValueError("failure_threshold must be a positive integer")
        if (isinstance(reset_timeout_ms, bool) or not isinstance(reset_timeout_ms, (int, float))
                or not isfinite(reset_timeout_ms) or reset_timeout_ms < 0):
            raise ValueError("reset_timeout_ms must be a finite non-negative number")
        self.failure_threshold = failure_threshold
        self.reset_timeout_ms = reset_timeout_ms
        self.clock = clock
        self._lock = threading.RLock()
        self._state = "closed"
        self._failures = 0
        self._opened_at = None
        self._probe_in_flight = False

    def snapshot(self):
        with self._lock:
            return {
                "state": self._state,
                "failure_count": self._failures,
                "failure_threshold": self.failure_threshold,
                "reset_timeout_ms": self.reset_timeout_ms,
                "probe_in_flight": self._probe_in_flight,
            }

    def before_call(self):
        """Return an admission decision and perform OPEN -> HALF_OPEN once."""
        with self._lock:
            transition = None
            if self._state == "open":
                elapsed_ms = (self.clock() - self._opened_at) * 1000
                if elapsed_ms >= self.reset_timeout_ms and not self._probe_in_flight:
                    self._state = "half_open"
                    self._probe_in_flight = True
                    transition = {"from_state": "open", "to_state": "half_open"}
                else:
                    remaining = max(0, self.reset_timeout_ms - elapsed_ms)
                    return {"allowed": False, "remaining_ms": round(remaining, 3), **self.snapshot()}
            elif self._state == "half_open":
                return {"allowed": False, "remaining_ms": 0, **self.snapshot()}
            return {"allowed": True, "transition": transition, **self.snapshot()}

    def record_failure(self):
        with self._lock:
            old = self._state
            self._failures += 1
            transition = None
            if old == "half_open" or self._failures >= self.failure_threshold:
                self._state = "open"
                self._opened_at = self.clock()
                self._probe_in_flight = False
                transition = {"from_state": old, "to_state": "open"}
            return {"transition": transition, **self.snapshot()}

    def record_success(self):
        with self._lock:
            old = self._state
            self._state = "closed"
            self._failures = 0
            self._opened_at = None
            self._probe_in_flight = False
            return {
                "transition": ({"from_state": old, "to_state": "closed"}
                               if old != "closed" else None),
                **self.snapshot(),
            }


class AdmissionController:
    """Bounded admission: active capacity plus a finite FIFO waiting room."""

    def __init__(self, max_in_flight=1, queue_capacity=1, min_interval_ms=0, *, clock=time.monotonic):
        for name, value, minimum in (("max_in_flight", max_in_flight, 1),
                                     ("queue_capacity", queue_capacity, 0)):
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        if (isinstance(min_interval_ms, bool) or not isinstance(min_interval_ms, (int, float))
                or not isfinite(min_interval_ms) or min_interval_ms < 0):
            raise ValueError("min_interval_ms must be a finite non-negative number")
        self.max_in_flight = max_in_flight
        self.queue_capacity = queue_capacity
        self.min_interval_ms = min_interval_ms
        self.clock = clock
        self._lock = threading.RLock()
        self._active = set()
        self._queue = deque()
        self._known = set()
        self._next_allowed_at = self.clock()

    def snapshot(self):
        with self._lock:
            return {"active": sorted(self._active), "queued": list(self._queue),
                    "max_in_flight": self.max_in_flight,
                    "queue_capacity": self.queue_capacity,
                    "min_interval_ms": self.min_interval_ms}

    def request(self, task_id):
        with self._lock:
            if task_id in self._known:
                raise ValueError("task already submitted to admission controller")
            self._known.add(task_id)
            if len(self._active) < self.max_in_flight and self.clock() >= self._next_allowed_at:
                self._grant(task_id)
                return {"decision": "granted", **self.snapshot()}
            if len(self._queue) < self.queue_capacity:
                self._queue.append(task_id)
                return {"decision": "queued", **self.snapshot()}
            return {"decision": "rejected", **self.snapshot()}

    def release(self, task_id):
        with self._lock:
            self._active.discard(task_id)
            return self.snapshot()

    def next_wait_ms(self):
        with self._lock:
            if not self._queue or len(self._active) >= self.max_in_flight:
                return None
            return round(max(0, (self._next_allowed_at - self.clock()) * 1000), 3)

    def promote(self):
        with self._lock:
            if not self._queue or len(self._active) >= self.max_in_flight or self.clock() < self._next_allowed_at:
                return None
            task_id = self._queue.popleft()
            self._grant(task_id)
            return {"task_id": task_id, **self.snapshot()}

    def _grant(self, task_id):
        self._active.add(task_id)
        self._next_allowed_at = self.clock() + self.min_interval_ms / 1000
