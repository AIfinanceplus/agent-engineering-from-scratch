"""V5 Policy Engine: decide whether a valid Tool request may execute.

Tool metadata describes capability facts such as risk. PolicyEngine interprets
those facts and returns one of three deterministic decisions:

- ALLOW
- REQUIRE_APPROVAL
- DENY

V5 does not yet implement pause/resume approval. REQUIRE_APPROVAL is surfaced as
a structured Observation and the Tool is not executed.
"""

from dataclasses import dataclass
from enum import Enum

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
    """Minimal deterministic policy used for the V5 lesson.

    The rules intentionally live outside Tool definitions. A Tool reports its
    risk classification; the PolicyEngine decides what that classification
    means for execution.
    """

    def evaluate(self, tool: Tool, arguments: dict) -> PolicyResult:
        if tool.risk == "low":
            return PolicyResult(
                PolicyDecision.ALLOW,
                "Low-risk Tool may execute automatically.",
            )

        if tool.risk == "medium":
            return PolicyResult(
                PolicyDecision.REQUIRE_APPROVAL,
                "Medium-risk Tool requires human approval before execution.",
            )

        if tool.risk == "high":
            return PolicyResult(
                PolicyDecision.DENY,
                "High-risk Tool is denied by the current teaching policy.",
            )

        # Tool.__post_init__ already rejects unknown values, but policy still
        # fails closed if a malformed Tool somehow reaches this boundary.
        return PolicyResult(
            PolicyDecision.DENY,
            f"Unknown risk classification: {tool.risk}",
        )


DEFAULT_POLICY = PolicyEngine()
