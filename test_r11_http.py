import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

import serve_r8
from serve_r11 import R11VisualizerHandler
from test_r11_portfolio import eligible_i2


class TestHandler(R11VisualizerHandler):
    def log_message(self, format, *args):
        pass


class R11HTTPTests(unittest.TestCase):
    def setUp(self):
        serve_r8.RUN_REGISTRY.clear()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address
        serve_r8.remember_run(
            {
                "ok": True,
                "run_id": "RUN-R11-SIZE",
                "domain": "investment",
                "r10_instrument_risk_ev": eligible_i2(),
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
            "/api/r11/size",
            body=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        response = connection.getresponse()
        raw = response.read().decode("utf-8")
        headers = dict(response.getheaders())
        connection.close()
        return response.status, headers, json.loads(raw)

    def valid_payload(self):
        return {
            "run_id": "RUN-R11-SIZE",
            "portfolio_value": 1_000_000.0,
            "portfolio_value_unit": "USD",
            "portfolio_risk_budget": 50_000.0,
            "portfolio_current_risk_used": 25_000.0,
            "max_position_nav_fraction": 0.10,
            "capital_required_per_reference_position": 50_000.0,
            "capital_source": "user_input",
            "max_reference_scale": 10.0,
        }

    def test_position_size_endpoint_returns_structured_json(self):
        status, headers, payload = self.post(self.valid_payload())
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["action"], "r11_position_size")
        self.assertEqual(payload["position_size"]["status"], "SIZE_AVAILABLE_FOR_REVIEW_NOT_EXECUTION")
        self.assertEqual(payload["position_size"]["sizing"]["binding_constraints"], ["trade_loss_limit"])
        self.assertFalse(payload["position_size"]["position_review_gate"]["execution_authorized"])
        self.assertIn("application/json", headers.get("Content-Type", ""))
        self.assertEqual(headers.get("Connection"), "close")

    def test_missing_i2_returns_structured_error(self):
        serve_r8.remember_run({"ok": True, "run_id": "RUN-NO-I2", "domain": "investment"})
        payload = self.valid_payload()
        payload["run_id"] = "RUN-NO-I2"
        status, _, result = self.post(payload)
        self.assertEqual(status, 400)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "instrument_risk_required")

    def test_unit_mismatch_returns_structured_error(self):
        payload = self.valid_payload()
        payload["portfolio_value_unit"] = "EUR"
        status, _, result = self.post(payload)
        self.assertEqual(status, 400)
        self.assertFalse(result["ok"])
        self.assertIn("must match the I2 P&L unit", result["error"]["message"])


if __name__ == "__main__":
    unittest.main()
