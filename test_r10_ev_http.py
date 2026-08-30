import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

import serve_r8
from serve_r10 import R10VisualizerHandler


class TestHandler(R10VisualizerHandler):
    def log_message(self, format, *args):
        pass


class R10EVHTTPTests(unittest.TestCase):
    def setUp(self):
        serve_r8.RUN_REGISTRY.clear()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address
        serve_r8.remember_run(
            {
                "ok": True,
                "run_id": "RUN-R10-EV",
                "domain": "investment",
                "investment_decision": {"artifact_type": "r10_investment_decision"},
            }
        )

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        serve_r8.RUN_REGISTRY.clear()

    def post(self, payload):
        body = json.dumps(payload).encode("utf-8")
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        connection.request(
            "POST",
            "/api/r10/ev",
            body=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        response = connection.getresponse()
        raw = response.read().decode("utf-8")
        headers = dict(response.getheaders())
        connection.close()
        return response.status, headers, json.loads(raw)

    def test_ev_endpoint_computes_only_from_explicit_scenario_book(self):
        status, headers, payload = self.post(
            {
                "run_id": "RUN-R10-EV",
                "scenarios": [
                    {"name":"down","probability":0.25,"payoff":-2,"probability_source":"user_assumption"},
                    {"name":"base","probability":0.5,"payoff":0.5,"probability_source":"user_assumption"},
                    {"name":"up","probability":0.25,"payoff":2,"probability_source":"user_assumption"},
                ],
                "transaction_cost": 0.05,
                "payoff_unit": "return_pct",
            }
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["ev"]["net_expected_value"], 0.2)
        self.assertEqual(payload["ev"]["position"], "NONE_UNTIL_RISK_BUDGET_AND_IMPLEMENTATION")
        self.assertIn("application/json", headers.get("Content-Type", ""))
        self.assertEqual(headers.get("Connection"), "close")

    def test_invalid_probability_book_returns_structured_json(self):
        status, _, payload = self.post(
            {
                "run_id": "RUN-R10-EV",
                "scenarios": [
                    {"name":"down","probability":0.4,"payoff":-1,"probability_source":"user_assumption"},
                    {"name":"up","probability":0.4,"payoff":1,"probability_source":"user_assumption"},
                ],
            }
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertIn("sum to 1.0", payload["error"]["message"])

    def test_missing_run_is_structured_json(self):
        status, _, payload = self.post(
            {
                "run_id": "RUN-MISSING",
                "scenarios": [
                    {"name":"down","probability":0.5,"payoff":-1,"probability_source":"user_assumption"},
                    {"name":"up","probability":0.5,"payoff":1,"probability_source":"user_assumption"},
                ],
            }
        )
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "run_not_found")


if __name__ == "__main__":
    unittest.main()
