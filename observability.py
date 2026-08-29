"""V11 tracing and metric primitives.

Tracing explains one run. Evals compare many runs. This module keeps tracing
small and deterministic enough to inspect in the teaching debugger.
"""

from dataclasses import dataclass, field, asdict
from time import perf_counter
from typing import Callable


@dataclass
class Span:
    span_id: str
    name: str
    parent_span_id: str | None
    task_id: str | None
    start_time: float
    end_time: float | None = None
    status: str = "running"
    attributes: dict = field(default_factory=dict)

    @property
    def duration_ms(self) -> float | None:
        if self.end_time is None:
            return None
        return round((self.end_time - self.start_time) * 1000, 3)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["duration_ms"] = self.duration_ms
        return payload


class TraceRecorder:
    """Runtime-owned trace recorder with explicit spans and counters."""

    def __init__(self, trace_id: str, *, clock: Callable[[], float] = perf_counter):
        self.trace_id = trace_id
        self.clock = clock
        self._counter = 0
        self._spans: list[Span] = []
        self._open: dict[str, Span] = {}
        self.metrics = {
            "scheduler_ticks": 0,
            "tasks_started": 0,
            "tasks_completed": 0,
            "tool_attempts": 0,
            "evidence_registered": 0,
            "citations_verified": 0,
            "runtime_events": 0,
        }

    def start_span(
        self,
        name: str,
        *,
        parent_span_id: str | None = None,
        task_id: str | None = None,
        attributes: dict | None = None,
    ) -> str:
        self._counter += 1
        span_id = f"span-{self._counter:03d}"
        span = Span(
            span_id=span_id,
            name=name,
            parent_span_id=parent_span_id,
            task_id=task_id,
            start_time=self.clock(),
            attributes=dict(attributes or {}),
        )
        self._spans.append(span)
        self._open[span_id] = span
        return span_id

    def end_span(
        self,
        span_id: str,
        *,
        status: str = "ok",
        attributes: dict | None = None,
    ) -> None:
        span = self._open.pop(span_id, None)
        if span is None:
            raise KeyError(f"Unknown or already-ended span_id: {span_id}")
        span.end_time = self.clock()
        span.status = status
        if attributes:
            span.attributes.update(attributes)

    def increment(self, metric: str, amount: int = 1) -> None:
        if metric not in self.metrics:
            self.metrics[metric] = 0
        self.metrics[metric] += amount

    def observe_runtime_event(self, event: dict) -> None:
        self.increment("runtime_events")
        event_type = event.get("type")
        if event_type == "tool_attempt":
            self.increment("tool_attempts")

    def summary(self) -> dict:
        spans = [span.to_dict() for span in self._spans]
        completed = [span for span in self._spans if span.end_time is not None]
        total_ms = round(sum(span.duration_ms or 0 for span in completed), 3)
        return {
            "trace_id": self.trace_id,
            "span_count": len(spans),
            "total_span_duration_ms": total_ms,
            "metrics": dict(self.metrics),
            "spans": spans,
        }
