import unittest

from rate_model_routing import (MODEL_CATALOG, ModelRouter, ModelTokenBudget,
                                ModelTokenBudgetExceeded)
from rate_parallel import ParallelRunError, RateParallelAgent


class ModelRoutingContractTests(unittest.TestCase):
    def test_router_returns_a_finite_declared_fallback_chain(self):
        router = ModelRouter(max_fallbacks=1)
        candidates = router.candidates(purpose="structured_rate_plan")
        self.assertEqual([spec.tier for spec in candidates], ["economy", "capable"])
        self.assertEqual(len(candidates), 2)
        self.assertEqual(router.snapshot()["max_fallbacks"], 1)

    def test_budget_reserves_before_call_and_releases_unused_tokens(self):
        budget = ModelTokenBudget(1000)
        reservation = budget.reserve(MODEL_CATALOG[0])
        self.assertEqual(budget.snapshot(), {
            "total_tokens": 1000, "spent_tokens": 0,
            "reserved_tokens": 600, "remaining_tokens": 400,
        })
        settlement = budget.settle(reservation["reservation_id"], input_tokens=160, output_tokens=280)
        self.assertEqual(settlement["charged_tokens"], 440)
        self.assertEqual(settlement["released_tokens"], 160)
        self.assertEqual(budget.snapshot()["remaining_tokens"], 560)
        with self.assertRaisesRegex(ValueError, "already settled"):
            budget.settle(reservation["reservation_id"], input_tokens=0, output_tokens=0)

    def test_budget_rejects_fallback_before_model_call(self):
        budget = ModelTokenBudget(700)
        first = budget.reserve(MODEL_CATALOG[0])
        budget.settle(first["reservation_id"], input_tokens=160, output_tokens=0)
        with self.assertRaises(ModelTokenBudgetExceeded) as caught:
            budget.reserve(MODEL_CATALOG[1])
        self.assertEqual(caught.exception.required_tokens, 1200)
        self.assertEqual(caught.exception.remaining_tokens, 540)
        self.assertEqual(budget.snapshot()["reserved_tokens"], 0)

    def test_invalid_budget_and_overreported_usage_fail_closed(self):
        with self.assertRaises(ValueError):
            ModelTokenBudget(0)
        budget = ModelTokenBudget(1000)
        reservation = budget.reserve(MODEL_CATALOG[0])
        with self.assertRaisesRegex(ValueError, "exceeds reserved"):
            budget.settle(reservation["reservation_id"], input_tokens=601, output_tokens=0)


class ModelRoutingIntegrationTests(unittest.TestCase):
    def agent(self):
        return RateParallelAgent(sleeper=lambda _: None)

    def test_economy_model_completes_without_fallback(self):
        run = self.agent().run_once(demo_scenario="route_primary")
        events = run["trace"]
        self.assertEqual(sum(e["event"] == "model_request_started" for e in events), 1)
        self.assertFalse(any(e["event"] == "model_fallback_requested" for e in events))
        self.assertEqual(run["architecture"]["model"], "scripted-economy-v1")
        self.assertEqual(run["architecture"]["model_routing"]["budget"]["spent_tokens"], 440)
        self.assertTrue(run["eval"]["passed"])

    def test_provider_failure_is_charged_before_one_declared_fallback(self):
        run = self.agent().run_once(demo_scenario="route_fallback")
        events = run["trace"]
        failed = next(e["sequence"] for e in events if e["event"] == "model_provider_failed")
        settled = next(e["sequence"] for e in events if e["event"] == "model_budget_settled")
        fallback = next(e["sequence"] for e in events if e["event"] == "model_fallback_requested")
        second_call = [e["sequence"] for e in events if e["event"] == "model_request_started"][1]
        self.assertLess(failed, settled)
        self.assertLess(settled, fallback)
        self.assertLess(fallback, second_call)
        self.assertEqual(sum(e["event"] == "model_fallback_requested" for e in events), 1)
        self.assertEqual(run["architecture"]["model"], "scripted-capable-v1")
        self.assertEqual(run["architecture"]["model_routing"]["budget"]["spent_tokens"], 640)
        self.assertTrue(run["eval"]["passed"])

    def test_insufficient_budget_abstains_before_fallback_model_call(self):
        with self.assertRaises(ParallelRunError) as caught:
            self.agent().run_once(demo_scenario="route_budget")
        self.assertEqual(caught.exception.code, "MODEL_TOKEN_BUDGET_EXCEEDED")
        events = caught.exception.trace
        self.assertEqual(sum(e["event"] == "model_request_started" for e in events), 1)
        self.assertTrue(any(e["event"] == "model_budget_rejected" and e["decision"] == "ABSTAIN" for e in events))
        self.assertFalse(any(e["event"] in {"plan_parse_started", "runtime_started", "tool_execution_started"} for e in events))


if __name__ == "__main__":
    unittest.main()
