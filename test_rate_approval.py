import threading
import time
import unittest

from rate_approval import ApprovalRegistry
from rate_parallel import ParallelRunError, RateParallelAgent


class ApprovalRegistryTests(unittest.TestCase):
    def test_real_wait_resumes_once_after_human_decision(self):
        registry = ApprovalRegistry()
        result = {}
        request = {"approval_id": "APR-1", "tool_name": "simulate_one_curve_trade"}
        thread = threading.Thread(target=lambda: result.update(
            registry.await_decision("run-1", request, timeout_seconds=2)))
        thread.start()
        for _ in range(100):
            if registry.snapshot("run-1"):
                break
            time.sleep(0.005)
        decision = registry.decide("run-1", "approve")
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertTrue(decision["accepted"])
        self.assertEqual(result["decision"], "approve")
        self.assertFalse(registry.decide("run-1", "deny")["accepted"])

    def test_unknown_and_invalid_decisions_fail_closed(self):
        registry = ApprovalRegistry()
        self.assertFalse(registry.decide("missing", "deny")["accepted"])
        with self.assertRaises(ValueError):
            registry.decide("missing", "maybe")


class ScriptedGate:
    def __init__(self, decision):
        self.decision = decision

    def await_decision(self, *_args, **_kwargs):
        if _kwargs.get("on_ready"):
            _kwargs["on_ready"]()
        return {"decision": self.decision, "resolved_by": "test_human"}


class ApprovalAgentIntegrationTests(unittest.TestCase):
    def agent(self):
        return RateParallelAgent(sleeper=lambda _: None)

    def test_approval_precedes_capability_and_every_tool(self):
        run = self.agent().run_once(demo_scenario="approval_interactive",
                                    approval_registry=ScriptedGate("approve"))
        events = run["trace"]
        request = next(e for e in events if e["event"] == "human_approval_requested")
        approved = next(e for e in events if e["event"] == "permission_elevation_approved")
        minted = next(e for e in events if e["event"] == "capability_minted")
        called = next(e for e in events if e["event"] == "tool_execution_started")
        self.assertLess(request["sequence"], approved["sequence"])
        self.assertLess(approved["sequence"], minted["sequence"])
        self.assertLess(minted["sequence"], called["sequence"])
        self.assertEqual(run["lesson"]["topic"], "human_approval")
        self.assertTrue(request["paper_only"])

    def test_human_denial_issues_no_capability_and_calls_no_tool(self):
        with self.assertRaises(ParallelRunError) as caught:
            self.agent().run_once(demo_scenario="approval_interactive",
                                  approval_registry=ScriptedGate("deny"))
        self.assertEqual(caught.exception.code, "HUMAN_APPROVAL_DENIED")
        events = caught.exception.trace
        self.assertFalse(any(e["event"] == "capability_minted" for e in events))
        self.assertFalse(any(e["event"] == "tool_execution_started" for e in events))


if __name__ == "__main__":
    unittest.main()
