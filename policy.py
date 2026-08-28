"""V6 Policy Engine: capability facts + trusted ExecutionContext.

Tool tells Runtime what a capability is. ExecutionContext tells Runtime who is
acting, for whom, in which tenant/task/trace. Policy combines both to decide
whether the request may execute.
"""

from dataclasses import dataclass
from enum import Enum

from context import ExecutionContext
from tools import Tool


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


@dataclass(frozen=True)
class PolicyResult:
    decision: PolicyDecision
    reason: str

    def to_dict(self) -> dict:
        return {
            "decision": self.decision.value,
            "reason": self.reason,
        }


class PolicyEngine:
    """Minimal deterministic context-aware policy for the V6 lesson."""

    def evaluate(
        self,
        tool: Tool,
        arguments: dict,
        context: ExecutionContext,
    ) -> PolicyResult:
        # Context-aware rule: a read-only agent may use low-risk read/compute
        # capabilities, but cannot request side-effecting medium/high-risk tools.
        if context.agent_id == "read-only-agent" and tool.risk != "low":
            return PolicyResult(
                PolicyDecision.DENY,
                (
                    f"Agent {context.agent_id} is not permitted to use "
                    f"{tool.risk}-risk Tool {tool.name}."
                ),
            )

        if tool.risk == "low":
            return PolicyResult(
                PolicyDecision.ALLOW,
                (
                    f"Low-risk Tool may execute for agent {context.agent_id} "
                    f"in tenant {context.tenant_id}."
                ),
            )

        if tool.risk == "medium":
            return PolicyResult(
                PolicyDecision.REQUIRE_APPROVAL,
                (
                    f"Medium-risk Tool requires human approval for user "
                    f"{context.user_id} before execution."
                ),
            )

        if tool.risk == "high":
            return PolicyResult(
                PolicyDecision.DENY,
                (
                    f"High-risk Tool is denied for agent {context.agent_id} "
                    "by the current teaching policy."
                ),
            )

        return PolicyResult(
            PolicyDecision.DENY,
            f"Unknown risk classification: {tool.risk}",
        )


DEFAULT_POLICY = PolicyEngine()
