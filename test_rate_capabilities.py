from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest

from rate_capabilities import CapabilityAuthority, CapabilityRejected
from rate_parallel import ParallelRunError, RateParallelAgent


class CapabilityAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.authority = CapabilityAuthority(secret=b"teaching-secret")
        self.ticket = self.authority.mint(
            run_id="run-1", task_id="D1", tool_name="fetch_public_rate_history",
            scope="rates:read", ttl_seconds=60,
        )

    def authorize(self, ticket=None, **overrides):
        args = {"run_id": "run-1", "task_id": "D1",
                "tool_name": "fetch_public_rate_history", "required_scope": "rates:read"}
        args.update(overrides)
        return self.authority.authorize(ticket or self.ticket, **args)

    def test_valid_ticket_is_signed_bound_and_consumed_once(self):
        result = self.authorize()
        self.assertTrue(result["authorized"])
        self.assertEqual(result["consumed_uses"], 1)
        with self.assertRaises(CapabilityRejected) as caught:
            self.authorize()
        self.assertIn("capability_already_consumed", caught.exception.reasons)

    def test_wrong_tool_scope_and_run_are_rejected(self):
        with self.assertRaises(CapabilityRejected) as caught:
            self.authorize(run_id="run-2", tool_name="simulate_one_curve_trade",
                           required_scope="paper:simulate")
        self.assertIn("run_id_mismatch", caught.exception.reasons)
        self.assertIn("tool_not_authorized", caught.exception.reasons)
        self.assertIn("scope_not_authorized", caught.exception.reasons)

    def test_tampered_claim_fails_signature(self):
        tampered = replace(self.ticket, scope="paper:simulate")
        with self.assertRaises(CapabilityRejected) as caught:
            self.authorize(tampered, required_scope="paper:simulate")
        self.assertIn("signature_invalid", caught.exception.reasons)

    def test_expired_ticket_is_rejected(self):
        with self.assertRaises(CapabilityRejected) as caught:
            self.authorize(now=datetime.now(timezone.utc) + timedelta(seconds=61))
        self.assertIn("capability_expired", caught.exception.reasons)


class CapabilityIntegrationTests(unittest.TestCase):
    def agent(self):
        return RateParallelAgent(sleeper=lambda _: None)

    def test_valid_capabilities_precede_every_tool_call(self):
        run = self.agent().run_once(demo_scenario="capability_valid")
        events = run["trace"]
        calls = [e for e in events if e["event"] == "tool_execution_started"]
        consumed = [e for e in events if e["event"] == "capability_consumed"]
        self.assertEqual(len(calls), 5)
        self.assertEqual(len(consumed), 5)
        for call in calls:
            match = next(e for e in consumed if e["target_task"] == call["task_id"])
            self.assertLess(match["sequence"], call["sequence"])
        self.assertEqual(run["lesson"]["topic"], "capability_security")
        self.assertFalse(run["architecture"]["capability_authority"]["secret_exposed"])

    def test_wrong_tool_and_expired_tickets_deny_before_any_tool(self):
        expected = {"capability_wrong_tool": "tool_not_authorized",
                    "capability_expired": "capability_expired"}
        for scenario, reason in expected.items():
            with self.subTest(scenario=scenario), self.assertRaises(ParallelRunError) as caught:
                self.agent().run_once(demo_scenario=scenario)
            self.assertEqual(caught.exception.code, "CAPABILITY_REJECTED")
            events = caught.exception.trace
            denial = next(e for e in events if e["event"] == "capability_rejected")
            self.assertIn(reason, denial["reasons"])
            self.assertFalse(any(e["event"] == "tool_execution_started" for e in events))


if __name__ == "__main__":
    unittest.main()
