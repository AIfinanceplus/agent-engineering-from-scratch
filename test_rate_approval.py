import threading
import time
import tempfile
import json
import subprocess
import sys
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

    def test_fresh_registry_restores_fsynced_request_and_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = ApprovalRegistry(directory)
            request = {"approval_id": "APR-D", "run_id": "run-d",
                       "tool_name": "simulate_one_curve_trade", "scope": "paper:simulate",
                       "arguments_sha256": "abc"}
            result = {}
            thread = threading.Thread(target=lambda: result.update(
                registry.await_decision("run-d", request, timeout_seconds=2)))
            thread.start()
            for _ in range(100):
                if registry.snapshot("run-d"):
                    break
                time.sleep(0.005)
            registry.decide("run-d", "approve")
            thread.join(timeout=2)
            restored = ApprovalRegistry(directory).snapshot("run-d")
            self.assertEqual(restored["decision"], "approve")
            self.assertEqual(restored["request"]["arguments_sha256"], "abc")
            script = (
                "import json,sys; from rate_approval import ApprovalRegistry; "
                "print(json.dumps(ApprovalRegistry(sys.argv[1]).snapshot('run-d')))"
            )
            child = subprocess.run([sys.executable, "-c", script, directory],
                                   capture_output=True, text=True, check=True)
            cross_process = json.loads(child.stdout)
            self.assertEqual(cross_process["decision"], "approve")
            self.assertEqual(cross_process["request"]["arguments_sha256"], "abc")

    def test_timeout_is_durable_and_visible_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = ApprovalRegistry(directory)
            request = {"approval_id": "APR-T", "run_id": "run-timeout",
                       "tool_name": "simulate_one_curve_trade"}
            result = {}
            thread = threading.Thread(target=lambda: result.update(
                registry.await_decision("run-timeout", request, timeout_seconds=0.01)))
            thread.start()
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(result["decision"], "timeout")
            restored = ApprovalRegistry(directory).snapshot("run-timeout")
            self.assertEqual(restored["decision"], "timeout")


class ScriptedGate:
    def __init__(self, decision):
        self.decision = decision

    def await_decision(self, *_args, **_kwargs):
        if _kwargs.get("on_ready"):
            _kwargs["on_ready"]()
        return {"decision": self.decision, "resolved_by": "test_human"}


class AutoDurableGate(ApprovalRegistry):
    def __init__(self, directory, decision="approve"):
        super().__init__(directory)
        self.auto_decision = decision

    def await_decision(self, run_id, request, **kwargs):
        original_ready = kwargs.get("on_ready")
        def ready():
            if original_ready:
                original_ready()
            threading.Thread(target=lambda: self.decide(run_id, self.auto_decision),
                             daemon=True).start()
        return super().await_decision(run_id, request, **{**kwargs, "on_ready": ready})


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

    def test_durable_restart_restores_and_revalidates_before_capability(self):
        with tempfile.TemporaryDirectory() as directory:
            run = self.agent().run_once(
                demo_scenario="approval_durable_restart",
                approval_registry=AutoDurableGate(directory),
            )
        names = [e["event"] for e in run["trace"]]
        ordered = [names.index(name) for name in (
            "approval_checkpoint_saved", "approval_runtime_restarted",
            "approval_checkpoint_loaded", "approval_binding_validated",
            "capability_minted", "tool_execution_started")]
        self.assertEqual(ordered, sorted(ordered))
        self.assertTrue(next(e for e in run["trace"]
                             if e["event"] == "approval_binding_validated")["passed"])

    def test_changed_parameters_cannot_reuse_durable_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ParallelRunError) as caught:
                self.agent().run_once(
                    demo_scenario="approval_durable_stale",
                    approval_registry=AutoDurableGate(directory),
                )
        self.assertEqual(caught.exception.code, "STALE_APPROVAL_REJECTED")
        events = caught.exception.trace
        self.assertTrue(any(e["event"] == "approval_binding_validated" and not e["passed"]
                            for e in events))
        self.assertFalse(any(e["event"] in {"capability_minted", "tool_execution_started"}
                             for e in events))


if __name__ == "__main__":
    unittest.main()
