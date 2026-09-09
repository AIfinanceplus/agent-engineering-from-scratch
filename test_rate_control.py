from concurrent.futures import ThreadPoolExecutor
import threading
import unittest

from rate_control import RunControl, RunControlRegistry, RunStopped
from rate_parallel import RateParallelAgent, RateRunStopped, prepare_rate_series
from rate_sources import FredCurveHistorySource
from test_rate_strategy import completed_steepener_history


class RateControlTests(unittest.TestCase):
    def test_deadline_uses_monotonic_budget_and_first_stop_reason_wins(self):
        now = [0.0]
        control = RunControl(100, clock=lambda: now[0])
        now[0] = .101
        self.assertTrue(control.request_stop("user"))
        self.assertEqual(control.snapshot()["reason"], "deadline")
        with self.assertRaises(RunStopped):
            control.check()
        control.finish("timed_out")
        self.assertFalse(control.request_stop())

    def test_success_and_cancel_have_one_linearized_winner(self):
        for _ in range(20):
            control = RunControl()
            barrier = threading.Barrier(2)

            def finish():
                barrier.wait()
                try:
                    return control.finish("completed")
                except RunStopped:
                    return "stopped"

            def cancel():
                barrier.wait()
                return control.request_stop()

            with ThreadPoolExecutor(max_workers=2) as pool:
                a, b = pool.submit(finish), pool.submit(cancel)
                outcome, accepted = a.result(), b.result()
            self.assertIn((outcome, accepted), {("completed", False), ("stopped", True)})

    def test_registry_targets_exact_run_and_preserves_active_runs(self):
        registry = RunControlRegistry(capacity=2)
        old, active = RunControl(), RunControl()
        registry.register("old", old)
        old.finish("completed")
        registry.register("active", active)
        self.assertFalse(registry.cancel("old")["accepted"])
        self.assertFalse(active.snapshot()["stop_requested"])
        self.assertIsNone(registry.cancel("missing"))
        registry.register("new", RunControl())
        self.assertIsNone(registry.cancel("old"))
        self.assertTrue(registry.cancel("active")["accepted"])
        self.assertTrue(registry.cancel("active")["accepted"])
        with self.assertRaises(RuntimeError):
            registry.register("overflow", RunControl())

    def test_invalid_budgets_are_rejected(self):
        for budget in [0, -1, True, None, float("nan"), float("inf"), 120001]:
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                RunControl(budget)

    def test_cancel_does_not_enter_source_fallback(self):
        control = RunControl()
        calls = []

        def transport(url):
            calls.append(url)
            control.request_stop()
            raise ConnectionError("closed")

        with control.bind(), self.assertRaises(RunStopped):
            FredCurveHistorySource(transport=transport).fetch("2026-01-01")
        self.assertEqual(len(calls), 1)

    def test_cancelled_retry_wait_never_starts_second_attempt(self):
        control = RunControl()
        attempts = []

        def fail(**_):
            attempts.append(1)
            raise ConnectionError("temporary failure")

        def observe(event):
            if event["event"] == "tool_retry_scheduled":
                control.request_stop()

        with self.assertRaises(RateRunStopped) as caught:
            RateParallelAgent({"fetch_public_rate_history": fail}).run_once(control=control, event_sink=observe)
        self.assertEqual(len(attempts), 1)
        self.assertEqual(caught.exception.trace[-1]["event"], "run_stopped")
        self.assertFalse(any(e["event"] == "tool_observation" for e in caught.exception.trace))

    def test_late_non_cooperative_result_is_discarded_before_join(self):
        control = RunControl()
        barrier = threading.Barrier(2, timeout=3)
        release = threading.Event()
        trace = []

        def prepare(**args):
            barrier.wait()
            if args["series_id"] == "DGS2":
                if not release.wait(3):
                    raise AssertionError("stop not observed")
                # Intentionally ignores the control scope like a legacy adapter.
                return {"artifact_type": "ignored_late_output", "never_use": True}
            return prepare_rate_series(**args)

        def observe(event):
            trace.append(event)
            if event["event"] == "task_completed" and event["task_id"] == "A10":
                control.request_stop()
            if event["event"] == "cancellation_requested":
                self.assertFalse(control.snapshot()["terminal"])
                release.set()

        agent = RateParallelAgent({"fetch_public_rate_history": lambda **_: completed_steepener_history(),
                                   "prepare_rate_series": prepare})
        try:
            with self.assertRaises(RateRunStopped):
                agent.run_once(control=control, event_sink=observe)
        finally:
            release.set()
        self.assertTrue(any(e["event"] == "tool_output_discarded" and e["task_id"] == "A2" for e in trace))
        self.assertFalse(any(e["event"] == "tool_observation" and e["task_id"] == "A2" for e in trace))
        self.assertFalse(any(e["event"] == "tool_execution_started" and e["task_id"] in {"J1", "S1"} for e in trace))
        self.assertEqual(trace[-1]["event"], "run_stopped")
        self.assertTrue(trace[-1]["workers_stopped"])
        self.assertEqual(control.snapshot()["terminal"], "cancelled")

    def test_timeout_is_not_a_retryable_tool_failure(self):
        now = [0.0]
        control = RunControl(100, clock=lambda: now[0])

        def observe(event):
            if event["event"] == "tool_execution_started" and event["task_id"] == "A2":
                now[0] = .101

        with self.assertRaises(RateRunStopped) as caught:
            RateParallelAgent(sleeper=lambda _: None).run_once(control=control, demo_scenario="deadline", event_sink=observe)
        trace = caught.exception.trace
        self.assertEqual(caught.exception.status, "timed_out")
        self.assertTrue(any(e["event"] == "deadline_exceeded" for e in trace))
        self.assertFalse(any(e["event"] == "tool_retry_scheduled" for e in trace))
        self.assertNotIn("run_completed", [e["event"] for e in trace])

    def test_two_live_controls_are_isolated(self):
        stopped, healthy = RunControl(), RunControl()
        stopped.request_stop()
        agent = RateParallelAgent({"fetch_public_rate_history": lambda **_: completed_steepener_history()})
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(agent.run_once, control=stopped)
            b = pool.submit(agent.run_once, control=healthy)
            with self.assertRaises(RateRunStopped):
                a.result()
            self.assertTrue(b.result()["eval"]["passed"])
        self.assertEqual(healthy.snapshot()["terminal"], "completed")


if __name__ == "__main__":
    unittest.main()
