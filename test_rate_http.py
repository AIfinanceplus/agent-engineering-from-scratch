import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from rate_agent import RateStrategyAgent
from rate_parallel import RateParallelAgent, prepare_rate_series
from rate_sources import FredCurveHistorySource
import serve_rates
from serve_rates import RateStrategyHandler
from test_rate_strategy import completed_steepener_history


class QuietRateHandler(RateStrategyHandler):
    def log_message(self, format, *args):
        pass


class RateHTTPTests(unittest.TestCase):
    def setUp(self):
        agent = RateStrategyAgent(
            {"fetch_public_rate_history": lambda start_date: completed_steepener_history()}
        )
        self.patch = patch.object(serve_rates, "RATE_AGENT", agent)
        self.patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), QuietRateHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.patch.stop()

    def post(self, payload, path="/api/rates/run-once"):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        body = json.dumps(payload).encode("utf-8")
        connection.request(
            "POST",
            path,
            body=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        response = connection.getresponse()
        raw = response.read().decode("utf-8")
        headers = dict(response.getheaders())
        connection.close()
        return response.status, headers, json.loads(raw)

    def post_stream(self, payload):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=10)
        body = json.dumps(payload).encode("utf-8")
        connection.request(
            "POST", "/api/rates/stream", body=body,
            headers={"Content-Type": "application/json", "Accept": "application/x-ndjson"},
        )
        response = connection.getresponse()
        raw = response.read().decode("utf-8")
        headers = dict(response.getheaders())
        connection.close()
        return response.status, headers, [json.loads(line) for line in raw.splitlines()]

    def get_root(self):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        connection.request("GET", "/")
        response = connection.getresponse()
        raw = response.read().decode("utf-8")
        connection.close()
        return response.status, raw

    def test_run_once_returns_one_closed_trade_trace_and_eval(self):
        status, headers, payload = self.post({})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        run = payload["run"]
        self.assertEqual(run["simulation"]["completed_trade"]["status"], "SIMULATED_CLOSED")
        self.assertTrue(run["eval"]["passed"])
        self.assertFalse(run["guardrails"]["broker_connection"])
        self.assertIn("application/json", headers["Content-Type"])
        self.assertEqual(headers["Connection"], "close")

    def test_stream_emits_start_events_and_result(self):
        status, headers, messages = self.post_stream({})
        self.assertEqual(status, 200)
        self.assertIn("application/x-ndjson", headers["Content-Type"])
        self.assertEqual(messages[0]["type"], "start")
        self.assertTrue(any(message["type"] == "event" for message in messages))
        result = messages[-1]
        self.assertEqual(result["type"], "result")
        self.assertTrue(result["result"]["eval"]["passed"])
        self.assertGreaterEqual(len([message for message in messages if message["type"] == "event"]), 10)

    def test_root_loads_only_focused_graph_and_stream_console(self):
        status, html = self.get_root()
        self.assertEqual(status, 200)
        self.assertIn("Agent Graph", html)
        self.assertIn("Agent Live Stream", html)
        self.assertIn("rate_console.js?v=2", html)
        self.assertIn("rate_console_core.js?v=2", html)
        self.assertNotIn("rate_workbench.js", html)
        self.assertNotIn("r12_step7.js", html)
        self.assertNotIn("data-detail-tab", html)

    def test_stream_arrives_before_tool_finishes_and_contains_exact_payloads(self):
        entered, release = threading.Event(), threading.Event()

        def gated_fetch(start_date):
            entered.set()
            if not release.wait(5):
                raise TimeoutError("test gate timed out")
            return completed_steepener_history()

        agent = RateStrategyAgent({"fetch_public_rate_history": gated_fetch})
        connection = http.client.HTTPConnection(self.host, self.port, timeout=3)
        with patch.object(serve_rates, "RATE_AGENT", agent):
            try:
                connection.request("POST", "/api/rates/stream", body=b"{}",
                                   headers={"Content-Type": "application/json"})
                response = connection.getresponse()
                messages = []
                while True:
                    message = json.loads(response.readline())
                    messages.append(message)
                    if message.get("event", {}).get("event") == "tool_execution_started":
                        break
                self.assertTrue(entered.wait(1))
                self.assertFalse(release.is_set())
                self.assertEqual(messages[-1]["event"]["task_id"], "D1")
                self.assertIn("start_date", messages[-1]["event"]["arguments"])
                release.set()
                messages.extend(json.loads(line) for line in response.read().splitlines())
            finally:
                release.set()
                connection.close()
        run = messages[-1]["result"]
        self.assertEqual({m["protocol"] for m in messages}, {"rate-ndjson-v1"})
        self.assertEqual({m["run_id"] for m in messages}, {run["run_id"]})
        events = [m["event"] for m in messages if m["type"] == "event"]
        self.assertEqual(events, run["trace"])
        self.assertEqual([e["sequence"] for e in events], list(range(1, len(events) + 1)))
        self.assertEqual({e["task_id"] for e in events}, {"G1", "P1", "R1", "D1", "S1", "E1", "END"})
        outputs = {e["task_id"]: e["output"] for e in events if "output" in e}
        self.assertEqual(outputs, {"D1": run["data"], "S1": run["simulation"], "E1": run["eval"]})

    def test_stream_error_keeps_the_correct_node_and_complete_partial_trace(self):
        status, _, messages = self.post_stream({"holding_days": 0})
        self.assertEqual(status, 200)
        self.assertEqual(messages[-1]["type"], "error")
        self.assertEqual(messages[-1]["error"]["task_id"], "S1")
        events = [m["event"] for m in messages if m["type"] == "event"]
        self.assertEqual(messages[-1]["error"]["trace"], events)
        self.assertTrue(any(e["event"] == "task_completed" and e["task_id"] == "D1" for e in events))
        self.assertFalse(any(e["task_id"] == "E1" for e in events))

    def test_stream_runs_have_distinct_ids(self):
        first = self.post_stream({})[2]
        second = self.post_stream({})[2]
        self.assertNotEqual(first[0]["run_id"], second[0]["run_id"])

    def test_parallel_stream_reports_join_waiting_before_slow_branch_returns(self):
        release = threading.Event()
        barrier = threading.Barrier(2, timeout=3)

        def prepare(**arguments):
            barrier.wait()
            if arguments["series_id"] == "DGS2" and not release.wait(3):
                raise TimeoutError("test release not received")
            return prepare_rate_series(**arguments)

        agent = RateParallelAgent({"fetch_public_rate_history": lambda **_: completed_steepener_history(),
                                   "prepare_rate_series": prepare})
        connection = http.client.HTTPConnection(self.host, self.port, timeout=3)
        with patch.object(serve_rates, "PARALLEL_RATE_AGENT", agent):
            try:
                connection.request("POST", "/api/rates/stream", body=b'{"execution_mode":"parallel"}',
                                   headers={"Content-Type": "application/json"})
                response = connection.getresponse()
                messages = []
                while True:
                    message = json.loads(response.readline())
                    messages.append(message)
                    event = message.get("event", {})
                    if event.get("event") == "join_waiting" and event["completed_dependencies"] == ["A10"]:
                        break
                self.assertEqual(messages[0]["execution_mode"], "parallel")
                self.assertFalse(release.is_set())
                release.set()
                messages.extend(json.loads(line) for line in response.read().splitlines())
            finally:
                release.set()
                connection.close()
        self.assertEqual(messages[-1]["type"], "result")
        run = messages[-1]["result"]
        self.assertEqual([m["event"] for m in messages if m["type"] == "event"], run["trace"])
        self.assertEqual(run["architecture"]["join_policy"], "all_success")

    def test_invalid_config_returns_structured_error(self):
        status, _, payload = self.post({"holding_days": 0})
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["action"], "rate_strategy_run_once")
        self.assertIn("holding_days", payload["error"]["message"])

    def test_exhausted_fred_retries_return_503_with_partial_agent_trace(self):
        failing_agent = RateStrategyAgent(
            {"fetch_public_rate_history": lambda **_kwargs: (_ for _ in ()).throw(
                ConnectionError("FRED DGS2 connection failed: RemoteDisconnected")
            )}
        )
        with patch.object(serve_rates, "RATE_AGENT", failing_agent), patch(
            "rate_agent.time.sleep"
        ):
            status, _, payload = self.post({})

        self.assertEqual(status, 503)
        self.assertEqual(payload["error"]["code"], "DATA_SOURCE_UNAVAILABLE")
        self.assertTrue(payload["error"]["retryable"])
        self.assertEqual(payload["error"]["task_id"], "D1")
        self.assertEqual(payload["error"]["attempts"], 3)
        self.assertEqual(payload["error"]["trace"][-1]["event"], "tool_execution_failed")

    def test_fred_disconnect_returns_200_via_disclosed_snapshot_fallback(self):
        source = FredCurveHistorySource(
            transport=lambda _url: (_ for _ in ()).throw(
                ConnectionError("RemoteDisconnected: remote closed")
            )
        )
        fallback_agent = RateStrategyAgent(
            {"fetch_public_rate_history": source.fetch}
        )
        with patch.object(serve_rates, "RATE_AGENT", fallback_agent):
            status, _, payload = self.post({})

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["run"]["data"]["source_mode"], "bundled_snapshot")
        self.assertEqual(payload["run"]["data"]["source_freshness"], "SNAPSHOT")
        self.assertTrue(payload["run"]["eval"]["passed"])
        self.assertIn(
            "data_source_fallback_selected",
            [row["event"] for row in payload["run"]["trace"]],
        )

    def test_recovery_demo_returns_resumed_run_and_durable_boundaries(self):
        status, _, payload = self.post({}, "/api/rates/recovery-demo")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        run = payload["run"]
        self.assertTrue(run["recovery"]["demo"])
        self.assertTrue(run["recovery"]["resumed"])
        self.assertEqual(run["recovery"]["crashed_after"], "D1")
        self.assertEqual(run["recovery"]["d1_executions"], 0)
        self.assertEqual(
            [row["boundary"] for row in run["checkpoints"]],
            ["after_plan_created", "after_D1", "after_S1", "after_E1"],
        )
        events = [row["event"] for row in run["trace"]]
        self.assertIn("process_restarted", events)
        self.assertIn("task_skipped_from_checkpoint", events)
        self.assertTrue(run["eval"]["passed"])

    def test_idempotency_demo_applies_same_command_once(self):
        status, _, payload = self.post({}, "/api/rates/idempotency-demo")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        idem = payload["run"]["idempotency"]
        self.assertEqual(idem["attempts"], ["APPLIED", "DEDUPLICATED"])
        self.assertEqual(idem["applied_attempts"], 1)
        self.assertEqual(idem["ledger_event_count"], 1)
        self.assertEqual(idem["boundary"], "Command Gateway")
        self.assertEqual(
            [idem["ledger_before"], idem["ledger_after_first"], idem["ledger_after_retry"]],
            [0, 1, 1],
        )


if __name__ == "__main__":
    unittest.main()
