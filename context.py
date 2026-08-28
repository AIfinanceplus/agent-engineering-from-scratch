"""V6 trusted execution identity for Runtime decisions.

ExecutionContext is not model context. It carries authenticated/runtime-owned
identity and tracing fields used by Policy, state, audit, and later storage.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionContext:
    tenant_id: str
    user_id: str
    agent_id: str
    task_id: str
    trace_id: str

    def __post_init__(self):
        for field_name in ("tenant_id", "user_id", "agent_id", "task_id", "trace_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")

    def to_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "trace_id": self.trace_id,
        }


def default_execution_context() -> ExecutionContext:
    """Deterministic local context for the from-scratch teaching Runtime."""
    return ExecutionContext(
        tenant_id="demo-tenant",
        user_id="demo-user",
        agent_id="general-agent",
        task_id="local-task",
        trace_id="local-trace",
    )
