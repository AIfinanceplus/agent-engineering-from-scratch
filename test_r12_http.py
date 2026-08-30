import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from serve_r12 import R12VisualizerHandler
from test_r12_strategy import demo_snapshot


class TestHandler(R12VisualizerHandler):
    def log_message(self, format, *args):
        pass


class R12HTTPTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def post(self, path, payload):
        body = json.dumps(payload).encode("utf-8")
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
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

    def test_registry_endpoint_returns_five_strategy_roadmap(self):
        status, headers, payload = self.post("/api/r12/registry", {})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["action"], "r12_strategy_registry")
        registry = payload["registry"]
        self.assertEqual(len(registry["strategies"]), 5)
        self.assertEqual(registry["roadmap_version"], "R12_STEP6")
        cross = next(row for row in registry["strategies"] if row["strategy_id"] == "cross_market_event_rv")
        self.assertEqual(cross["status"], "LIVE_HITL_AGENT_DEPTH_QUOTE_IDENTITY_GATED")
        self.assertFalse(registry["discovery_contract"]["candidate_match_is_settlement_proof"])
        self.assertTrue(registry["execution_quote_contract"]["target_quantity_must_fill_on_both_legs"])
        self.assertFalse(registry["execution_quote_contract"]["automatic_execution"])
        self.assertTrue(registry["rules_analysis_contract"]["contract_fingerprint_bound"])
        self.assertFalse(registry["rules_analysis_contract"]["parser_can_auto_approve_identity"])
        self.assertTrue(registry["strategy_agent_contract"]["durable_human_approval_pause"])
        self.assertFalse(registry["strategy_agent_contract"]["automatic_execution"])
        self.assertIn("application/json", headers.get("Content-Type", ""))
        self.assertEqual(headers.get("Connection"), "close")

    def test_structural_scan_endpoint_returns_paper_signal_contracts(self):
        status, headers, payload = self.post(
            "/api/r12/structural-scan",
            {"snapshot": demo_snapshot()},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["action"], "r12_structural_scan")
        scan = payload["scan"]
        self.assertEqual(scan["opportunity_count"], 3)
        self.assertEqual(scan["paper_signal_count"], 3)
        self.assertTrue(all(not row["guardrails"]["automatic_execution"] for row in scan["opportunities"]))
        self.assertIn("application/json", headers.get("Content-Type", ""))
        self.assertEqual(headers.get("Connection"), "close")

    def test_invalid_snapshot_returns_structured_json_error(self):
        status, _, payload = self.post(
            "/api/r12/structural-scan",
            {"snapshot": {"source": "missing_as_of"}},
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["action"], "r12_structural_scan")
        self.assertEqual(payload["error"]["code"], "ValueError")
        self.assertIn("as_of is required", payload["error"]["message"])


if __name__ == "__main__":
    unittest.main()
