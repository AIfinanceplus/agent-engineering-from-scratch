import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

import serve_r8
from serve_r10 import R10VisualizerHandler


def decision():
    return {
        "artifact_type": "r10_investment_decision",
        "mispricing": {
            "status": "NUMERIC_GAP_AVAILABLE",
            "dimension": "5Y inflation compensation",
            "gap_magnitude_bp": 5.0,
        },
        "scenario_payoff_template": {
            "status": "STANDARDIZED_MARKET_MOVE_PAYOFF_TEMPLATE_AVAILABLE",
            "exposure": "LONG_5Y_INFLATION_COMPENSATION",
            "scenarios": [
                {"name": "research_target_realized", "market_move_bp": 5.0},
                {"name": "no_repricing", "market_move_bp": 0.0},
                {"name": "equal_opposite_move", "market_move_bp": -5.0},
            ],
        },
    }


class TestHandler(R10VisualizerHandler):
    def log_message(self, format, *args):
        pass


class R10InstrumentHTTPTests(unittest.TestCase):
    def setUp(self):
        serve_r8.RUN_REGISTRY.clear()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address
        serve_r8.remember_run(
            {
                "ok": True,
                "run_id": "RUN-R10-I2",
                "domain": "investment",
                "investment_decision": decision(),
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
            "/api/r10/instrument-risk",
            body=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        response = connection.getresponse()
        raw = response.read().decode("utf-8")
        headers = dict(response.getheaders())
        connection.close()
        return response.status, headers, json.loads(raw)

    @staticmethod
    def payload():
        return {
            "run_id": "RUN-R10-I2",
            "instrument_name": "5Y breakeven package",
            "position_direction": "LONG",
            "sensitivity_per_bp": 2500,
            "sensitivity_source": "user_input",
            "pnl_unit": "USD",
            "scenario_probabilities": [
                {"name":"research_target_realized","probability":0.5,"probability_source":"user_assumption"},
                {"name":"no_repricing","probability":0.25,"probability_source":"user_assumption"},
                {"name":"equal_opposite_move","probability":0.25,"probability_source":"user_assumption"},
            ],
            "transaction_cost": 100,
            "carry": 50,
            "risk_budget": 15000,
            "loss_limit": 13000,
        }

    def test_instrument_endpoint_returns_real_pnl_risk_artifact(self):
        status, headers, payload = self.post(self.payload())
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        artifact = payload["instrument_risk_ev"]
        self.assertEqual(artifact["net_expected_value"], 3075.0)
        self.assertEqual(artifact["position_review_gate"]["status"], "ELIGIBLE_FOR_POSITION_REVIEW_NOT_EXECUTION")
        self.assertIn("application/json", headers.get("Content-Type", ""))
        self.assertEqual(headers.get("Connection"), "close")
        self.assertEqual(serve_r8.RUN_REGISTRY["RUN-R10-I2"]["r10_instrument_risk_ev"]["artifact_type"], "r10_instrument_risk_ev")

    def test_invalid_sensitivity_returns_structured_json(self):
        payload = self.payload()
        payload["sensitivity_per_bp"] = 0
        status, _, response = self.post(payload)
        self.assertEqual(status, 400)
        self.assertFalse(response["ok"])
        self.assertIn("must be > 0", response["error"]["message"])

    def test_missing_run_returns_structured_json(self):
        payload = self.payload()
        payload["run_id"] = "RUN-MISSING"
        status, _, response = self.post(payload)
        self.assertEqual(status, 404)
        self.assertEqual(response["error"]["code"], "run_not_found")


if __name__ == "__main__":
    unittest.main()
