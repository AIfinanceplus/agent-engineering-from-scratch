"""Per-run cooperative stop scope. A deadline requests a stop; it cannot kill Python threads."""

from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from math import isfinite
from threading import Event, RLock
import time


_CURRENT = ContextVar("rate_run_control", default=None)


class RunStopped(Exception):
    """Not a TimeoutError: retry/source fallback must not swallow cancellation."""
    def __init__(self, reason):
        self.reason = reason
        self.status = "timed_out" if reason == "deadline" else "cancelled"
        super().__init__("运行预算已到，停止执行" if reason == "deadline" else "已请求取消本次运行")


class RunControl:
    def __init__(self, budget_ms=30000, *, clock=time.monotonic):
        if isinstance(budget_ms, bool) or not isinstance(budget_ms, (int, float)) or not isfinite(budget_ms) or not 10 <= budget_ms <= 120000:
            raise ValueError("budget_ms must be a finite number between 10 and 120000")
        self.budget_ms = budget_ms
        self.clock = clock
        self.started = clock()
        self.deadline = self.started + budget_ms / 1000
        self._lock = RLock()
        self._wake = Event()
        self._reason = None
        self._terminal = None

    def _refresh(self):
        if not self._terminal and self._reason is None and self.clock() >= self.deadline:
            self._reason = "deadline"
            self._wake.set()

    def snapshot(self):
        with self._lock:
            self._refresh()
            return {"budget_ms": self.budget_ms, "reason": self._reason,
                    "terminal": self._terminal, "stop_requested": self._reason is not None,
                    "elapsed_ms": round((self.clock() - self.started) * 1000, 3)}

    def request_stop(self, reason="user"):
        with self._lock:
            self._refresh()
            if self._terminal:
                return False
            if self._reason is None:
                self._reason = reason
                self._wake.set()
            return True

    def check(self):
        with self._lock:
            self._refresh()
            if self._reason:
                raise RunStopped(self._reason)

    def wait(self, seconds):
        """Interruptible waiting: stop requests wake the Tool, rather than killing it."""
        until = self.clock() + seconds
        while True:
            self.check()
            remaining = min(until, self.deadline) - self.clock()
            if remaining <= 0:
                self.check()
                return
            self._wake.wait(remaining)

    def finish(self, status):
        """Linearize success vs cancellation; a terminal run cannot be cancelled again."""
        with self._lock:
            if self._terminal:
                return self._terminal
            self._refresh()
            if status == "completed" and self._reason:
                raise RunStopped(self._reason)
            self._terminal = status
            return status

    @contextmanager
    def bind(self):
        token = _CURRENT.set(self)
        try:
            yield
        finally:
            _CURRENT.reset(token)


def check_run_control():
    scope = _CURRENT.get()
    if scope is not None:
        scope.check()


class RunControlRegistry:
    """Process-local controls only; bounded terminal history, no resume/persistence promise."""
    def __init__(self, capacity=128):
        self.capacity = capacity
        self._lock = RLock()
        self._runs = OrderedDict()

    def register(self, run_id, control):
        with self._lock:
            if run_id in self._runs:
                raise ValueError("duplicate run_id")
            for old in list(self._runs):
                if len(self._runs) < self.capacity:
                    break
                if self._runs[old].snapshot()["terminal"]:
                    del self._runs[old]
            if len(self._runs) >= self.capacity:
                raise RuntimeError("too many active runs; wait for one to finish")
            self._runs[run_id] = control

    def cancel(self, run_id):
        with self._lock:
            control = self._runs.get(run_id)
        if control is None:
            return None
        accepted = control.request_stop("user")
        return {"run_id": run_id, "accepted": accepted, **control.snapshot()}
