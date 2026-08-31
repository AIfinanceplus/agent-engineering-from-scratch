import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from rate_agent import RateStrategyAgent
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

    def post(self, payload):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        body = json.dumps(payload).encode("utf-8")
        connection.request(
            "POST",
            "/api/rates/run-once",
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
        self.assertIn("rate_workbench.js?v=rate-v1-eval-v2", html)

    def test_invalid_config_returns_structured_error(self):
        status, _, payload = self.post({"holding_days": 0})
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["action"], "rate_strategy_run_once")
        self.assertIn("holding_days", payload["error"]["message"])


if __name__ == "__main__":
    unittest.main()
