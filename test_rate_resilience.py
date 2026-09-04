import unittest

from rate_parallel import ParallelRunError, RateParallelAgent
from rate_resilience import AdmissionController, CircuitBreaker


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance_ms(self, value):
        self.now += value / 1000


class CircuitBreakerTests(unittest.TestCase):
    def test_closed_open_half_open_closed(self):
        clock = FakeClock()
        breaker = CircuitBreaker(2, 100, clock=clock)
        self.assertTrue(breaker.before_call()["allowed"])
        self.assertIsNone(breaker.record_failure()["transition"])
        opened = breaker.record_failure()
        self.assertEqual(opened["transition"], {"from_state": "closed", "to_state": "open"})
        self.assertFalse(breaker.before_call()["allowed"])
        clock.advance_ms(100)
        probe = breaker.before_call()
        self.assertTrue(probe["allowed"])
        self.assertEqual(probe["state"], "half_open")
        self.assertFalse(breaker.before_call()["allowed"])
        closed = breaker.record_success()
        self.assertEqual(closed["transition"], {"from_state": "half_open", "to_state": "closed"})
        self.assertEqual(closed["failure_count"], 0)

    def test_failed_probe_reopens_circuit(self):
        clock = FakeClock()
        breaker = CircuitBreaker(1, 10, clock=clock)
        breaker.record_failure()
        clock.advance_ms(10)
        self.assertEqual(breaker.before_call()["state"], "half_open")
        failed = breaker.record_failure()
        self.assertEqual(failed["transition"], {"from_state": "half_open", "to_state": "open"})


class AdmissionControllerTests(unittest.TestCase):
    def test_bounded_fifo_queue_and_rate_interval(self):
        clock = FakeClock()
        gate = AdmissionController(1, 1, 100, clock=clock)
        self.assertEqual(gate.request("A2")["decision"], "granted")
        self.assertEqual(gate.request("A10")["decision"], "queued")
        gate.release("A2")
        self.assertEqual(gate.next_wait_ms(), 100)
        self.assertIsNone(gate.promote())
        clock.advance_ms(100)
        promoted = gate.promote()
        self.assertEqual(promoted["task_id"], "A10")
        self.assertEqual(promoted["queued"], [])

    def test_full_queue_rejects_without_admitting(self):
        gate = AdmissionController(1, 0)
        self.assertEqual(gate.request("A2")["decision"], "granted")
        rejected = gate.request("A10")
        self.assertEqual(rejected["decision"], "rejected")
        self.assertNotIn("A10", rejected["active"])


class RuntimeResilienceIntegrationTests(unittest.TestCase):
    def test_open_circuit_prevents_third_tool_execution(self):
        events = []
        with self.assertRaises(ParallelRunError):
            RateParallelAgent().run_once(demo_scenario="breaker_open", event_sink=events.append)
        d1_calls = [e for e in events if e["event"] == "tool_execution_started" and e["task_id"] == "D1"]
        self.assertEqual(len(d1_calls), 2)
        rejected = next(e for e in events if e["event"] == "circuit_call_rejected")
        self.assertEqual(rejected["snapshot"]["state"], "open")
        self.assertFalse(any(e["event"] == "tool_observation" and e["task_id"] == "D1" for e in events))

    def test_half_open_probe_recovers_and_completes_run(self):
        events = []
        run = RateParallelAgent().run_once(demo_scenario="breaker_recovery", event_sink=events.append)
        transitions = [(e["from_state"], e["to_state"]) for e in events if e["event"] == "circuit_state_changed"]
        self.assertEqual(transitions, [("closed", "open"), ("open", "half_open"), ("half_open", "closed")])
        self.assertEqual(sum(e["event"] == "tool_execution_started" and e["task_id"] == "D1" for e in events), 3)
        self.assertTrue(run["eval"]["passed"])

    def test_backpressure_queues_then_releases_before_tool_call(self):
        events = []
        run = RateParallelAgent().run_once(demo_scenario="backpressure", event_sink=events.append)
        names = [e["event"] for e in events]
        self.assertLess(names.index("backpressure_queued"), names.index("backpressure_released"))
        released = next(e["sequence"] for e in events if e["event"] == "backpressure_released")
        a10_call = next(e["sequence"] for e in events if e["event"] == "tool_execution_started" and e["task_id"] == "A10")
        self.assertLess(released, a10_call)
        self.assertTrue(run["eval"]["passed"])

    def test_overload_rejects_before_tool_and_blocks_join(self):
        events = []
        with self.assertRaises(ParallelRunError):
            RateParallelAgent().run_once(demo_scenario="overload_rejected", event_sink=events.append)
        self.assertTrue(any(e["event"] == "admission_rejected" and e["target_task"] == "A10" for e in events))
        self.assertFalse(any(e["event"] == "tool_execution_started" and e["task_id"] == "A10" for e in events))
        self.assertTrue(any(e["event"] == "join_blocked" for e in events))


class ValidationTests(unittest.TestCase):
    def test_invalid_policies_are_rejected(self):
        for args in ((0, 10), (1, -1)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                CircuitBreaker(*args)
        with self.assertRaises(ValueError):
            AdmissionController(0, 1)
        with self.assertRaises(ValueError):
            AdmissionController(1, -1)


if __name__ == "__main__":
    unittest.main()
