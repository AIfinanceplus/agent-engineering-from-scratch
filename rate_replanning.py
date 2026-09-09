"""Bounded replanning primitives for the Agent Runtime teaching graph."""

from copy import deepcopy
import hashlib
import json


class ReplanLoopDetected(RuntimeError):
    def __init__(self, fingerprint):
        self.fingerprint = fingerprint
        super().__init__("Planner repeated a previously rejected plan")


class ReplanBudgetExhausted(RuntimeError):
    def __init__(self, max_revisions):
        self.max_revisions = max_revisions
        super().__init__(f"replanning budget exhausted after {max_revisions} plan revision(s)")


class PlanRevisionGuard:
    """Accept only novel plans and cap how many may execute in one Run."""

    def __init__(self, max_revisions=2):
        if isinstance(max_revisions, bool) or not isinstance(max_revisions, int) or max_revisions < 1:
            raise ValueError("max_revisions must be a positive integer")
        self.max_revisions = max_revisions
        self._fingerprints = []
        self._revisions = 0

    @staticmethod
    def fingerprint(plan):
        canonical = json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def seed(self, plan):
        """Remember the initial plan without charging the replan budget."""
        fingerprint = self.fingerprint(plan)
        if fingerprint not in self._fingerprints:
            self._fingerprints.append(fingerprint)
        return {
            "revision": 0,
            "fingerprint": fingerprint,
            "max_revisions": self.max_revisions,
            "remaining_revisions": self.max_revisions,
            "plan": deepcopy(plan),
        }

    def register(self, plan):
        fingerprint = self.fingerprint(plan)
        if fingerprint in self._fingerprints:
            raise ReplanLoopDetected(fingerprint)
        if self._revisions >= self.max_revisions:
            raise ReplanBudgetExhausted(self.max_revisions)
        self._fingerprints.append(fingerprint)
        self._revisions += 1
        return {
            "revision": self._revisions,
            "fingerprint": fingerprint,
            "max_revisions": self.max_revisions,
            "remaining_revisions": self.max_revisions - self._revisions,
            "plan": deepcopy(plan),
        }

    def snapshot(self):
        return {"used_revisions": self._revisions, "max_revisions": self.max_revisions,
                "fingerprints": list(self._fingerprints)}


def validate_rate_history_observation(history, *, lookback_days, holding_days):
    """Observation quality gate; a successful Tool call can still be unusable."""
    minimum = int(lookback_days) + int(holding_days) + 1
    observations = history.get("observations", []) if isinstance(history, dict) else []
    count = len(observations) if isinstance(observations, list) else 0
    passed = history.get("artifact_type") == "rate_curve_history" and count >= minimum
    return {
        "artifact_type": "rate_history_validation",
        "passed": passed,
        "observation_count": count,
        "minimum_required": minimum,
        "reason": None if passed else f"need at least {minimum} aligned observations; received {count}",
    }
