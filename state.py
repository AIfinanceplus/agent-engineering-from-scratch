"""V7 AgentState and StateStore.

AgentState answers two practical questions:

1. Where is the Agent in its current run?
2. What useful results has it already accumulated?

V7 deliberately uses an in-memory store. Durable persistence and crash recovery
belong to V8 Checkpoint / Durable Execution.
"""

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class AgentState:
    task_id: str
    max_steps: int
    status: str = "running"
    phase: str = "starting"
    step: int = 0
    current_tool: str | None = None
    current_arguments: dict | None = None
    observations: list[dict] = field(default_factory=list)
    last_observation: Any = None
    final_answer: str | None = None
    stop_reason: str | None = None

    def to_dict(self) -> dict:
        return deepcopy(asdict(self))

    def record_observation(self, tool_name: str, observation: Any) -> None:
        snapshot = deepcopy(observation)
        self.last_observation = snapshot
        self.observations.append(
            {
                "step": self.step,
                "tool_name": tool_name,
                "observation": snapshot,
            }
        )


class StateStore:
    """Minimal storage contract used by the Runtime."""

    def save(self, state: AgentState, *, reason: str) -> None:
        raise NotImplementedError

    def load(self, task_id: str) -> AgentState | None:
        raise NotImplementedError

    def history(self, task_id: str) -> list[dict]:
        raise NotImplementedError


class InMemoryStateStore(StateStore):
    """Teaching StateStore that snapshots state but does not survive restart."""

    def __init__(self):
        self._latest: dict[str, AgentState] = {}
        self._history: dict[str, list[dict]] = {}

    def save(self, state: AgentState, *, reason: str) -> None:
        if not isinstance(state, AgentState):
            raise TypeError("state must be an AgentState")

        snapshot = deepcopy(state)
        self._latest[state.task_id] = snapshot
        self._history.setdefault(state.task_id, []).append(
            {
                "reason": reason,
                "state": snapshot.to_dict(),
            }
        )

    def load(self, task_id: str) -> AgentState | None:
        state = self._latest.get(task_id)
        return deepcopy(state) if state is not None else None

    def history(self, task_id: str) -> list[dict]:
        return deepcopy(self._history.get(task_id, []))
