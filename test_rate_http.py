import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from rate_agent import RateStrategyAgent
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

    def test_root_retains_full_workbench_and_loads_rate_overlay_last(self):
        status, html = self.get_root()
        self.assertEqual(status, 200)
        self.assertIn("Agent 运行过程", html)
        self.assertIn('data-detail-tab="trace"', html)
        self.assertIn('data-detail-tab="logic"', html)
        self.assertIn('data-detail-tab="evidence"', html)
        self.assertIn('data-detail-tab="state"', html)
        self.assertIn('data-detail-tab="checkpoint"', html)
        self.assertIn('data-detail-tab="architecture"', html)
        self.assertIn("rate_workbench.js", html)
        self.assertLess(html.index("r12_step7.js"), html.index("rate_workbench.js"))
        self.assertIn("rate_workbench.js?v=rate-v1-state-eval-v2", html)

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


if __name__ == "__main__":
    unittest.main()
