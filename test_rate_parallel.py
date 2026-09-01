from copy import deepcopy
import json
from pathlib import Path
import subprocess
import threading
import unittest

from rate_parallel import GRAPH_ROWS, GRAPH_EDGES, RateParallelAgent, ParallelRunError, prepare_rate_series, join_rate_series
from test_rate_strategy import completed_steepener_history


class RateParallelTests(unittest.TestCase):
    def test_browser_graph_matches_runtime_graph(self):
        result = subprocess.run(["node", "-e", "console.log(JSON.stringify(require('./web/rate_console_core.js').PARALLEL_ROWS))"],
                                cwd=Path(__file__).parent, capture_output=True, text=True, check=True)
        rows = json.loads(result.stdout)
        self.assertEqual(rows, GRAPH_ROWS)
        edges = [[left, right] for current, following in zip(rows, rows[1:]) for left in current for right in following]
        self.assertEqual(edges, GRAPH_EDGES)

    def agent(self, **overrides):
        return RateParallelAgent({"fetch_public_rate_history": lambda **_: completed_steepener_history(), **overrides}, sleeper=lambda _: None)

    def test_both_tools_start_before_one_finishes_and_join_waits_for_both(self):
        barrier = threading.Barrier(2, timeout=3)
        release_slow = threading.Event()
        owners, trace = [], []
        owner = threading.get_ident()

        def prepare(**args):
            barrier.wait()  # A serial implementation cannot pass this barrier.
            if args["series_id"] == "DGS2" and not release_slow.wait(3):
                raise TimeoutError("Join never reported waiting for slow branch")
            return prepare_rate_series(**args)

        def observe(event):
            owners.append(threading.get_ident())
            trace.append(event)
            if event["event"] == "join_waiting" and event["completed_dependencies"] == ["A10"]:
                self.assertEqual(event["waiting_for"], ["A2"])
                self.assertFalse(any(e["event"] == "tool_execution_started" and e["task_id"] == "J1" for e in trace))
                release_slow.set()

        try:
            run = self.agent(prepare_rate_series=prepare).run_once(event_sink=observe)
        finally:
            release_slow.set()
        self.assertEqual(set(owners), {owner})
        self.assertEqual(trace, run["trace"])
        starts = [e["sequence"] for e in trace if e["event"] == "tool_execution_started" and e["task_id"] in {"A2", "A10"}]
        finishes = [e["sequence"] for e in trace if e["event"] == "task_completed" and e["task_id"] in {"A2", "A10"}]
        joined = next(e["sequence"] for e in trace if e["event"] == "join_released")
        self.assertLess(max(starts), min(finishes))
        self.assertGreater(joined, max(finishes))
        self.assertEqual([e["sequence"] for e in trace], list(range(1, len(trace) + 1)))
        self.assertTrue(run["eval"]["passed"])
        self.assertEqual(run["data"]["observations"], completed_steepener_history()["observations"])

    def test_failed_branch_does_not_run_join_or_strategy_and_sibling_is_drained(self):
        barrier = threading.Barrier(2, timeout=3)
        release = threading.Event()
        trace = []

        def prepare(**args):
            barrier.wait()
            if args["series_id"] == "DGS10":
                raise ValueError("bad ten-year series")
            if not release.wait(3):
                raise TimeoutError("failure was not streamed")
            return prepare_rate_series(**args)

        def observe(event):
            trace.append(event)
            if event["event"] == "join_blocked":
                release.set()

        try:
            with self.assertRaises(ParallelRunError) as caught:
                self.agent(prepare_rate_series=prepare).run_once(event_sink=observe)
        finally:
            release.set()
        self.assertEqual(caught.exception.task_id, "A10")
        self.assertEqual(caught.exception.trace, trace)
        self.assertTrue(any(e["event"] == "task_completed" and e["task_id"] == "A2" for e in trace))
        self.assertFalse(any(e["event"] == "tool_execution_started" and e["task_id"] in {"J1", "S1"} for e in trace))
        self.assertFalse(any(e["event"] == "eval_started" for e in trace))

    def test_two_simultaneous_runs_do_not_mix_state_or_batch_ids(self):
        from concurrent.futures import ThreadPoolExecutor
        agent = self.agent()
        with ThreadPoolExecutor(max_workers=2) as pool:
            runs = list(pool.map(lambda _: agent.run_once(), range(2)))
        self.assertNotEqual(runs[0]["run_id"], runs[1]["run_id"])
        for run in runs:
            self.assertEqual({e["run_id"] for e in run["trace"]}, {run["run_id"]})
            self.assertEqual(run["observations"]["A2"]["batch_id"], run["run_id"])

    def test_snapshot_demo_is_disclosed_and_never_fetches_network(self):
        def forbidden(**_):
            raise AssertionError("demo must not fetch public network")
        run = self.agent(fetch_public_rate_history=forbidden).run_once(demo_scenario="two_year_slow")
        self.assertEqual(run["data"]["source_freshness"], "SNAPSHOT")
        self.assertTrue(run["lesson"]["teaching_delay"])
        self.assertEqual(sum(e["event"] == "demo_delay_started" for e in run["trace"]), 2)
        self.assertTrue(run["eval"]["passed"])

    def test_live_mode_never_injects_delays(self):
        run = self.agent().run_once()
        self.assertFalse(any(e["event"].startswith("demo_") for e in run["trace"]))
        self.assertFalse(run["lesson"]["teaching_delay"])

    def test_join_rejects_mismatched_batch_or_source_and_preserves_original(self):
        history = completed_steepener_history()
        original = deepcopy(history)
        left = prepare_rate_series(history, "DGS2", "run-A")
        right = prepare_rate_series(history, "DGS10", "run-A")
        self.assertEqual(join_rate_series(left, right)["observations"], history["observations"])
        self.assertEqual(history, original)
        right["batch_id"] = "run-B"
        with self.assertRaisesRegex(ValueError, "different runs"):
            join_rate_series(left, right)
        right["batch_id"] = "run-A"
        right["source_fingerprint"] = "different source"
        with self.assertRaisesRegex(ValueError, "different source"):
            join_rate_series(left, right)

    def test_series_preparation_rejects_non_finite_and_duplicate_dates(self):
        history = completed_steepener_history()
        history["observations"][0]["dgs2"] = float("nan")
        with self.assertRaisesRegex(ValueError, "non-finite"):
            prepare_rate_series(history, "DGS2", "test")
        history = completed_steepener_history()
        history["observations"][1]["date"] = history["observations"][0]["date"]
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            prepare_rate_series(history, "DGS2", "test")


if __name__ == "__main__":
    unittest.main()
