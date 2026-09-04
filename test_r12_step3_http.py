import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import serve_r12
from serve_r12 import R12VisualizerHandler


class TestHandler(R12VisualizerHandler):
    def log_message(self, format, *args):
        pass


def discovery_fixture():
    return {
        "artifact_type": "r12_market_discovery",
        "query": "Fed September rate cut",
        "providers": {
            "kalshi": {
                "provider": "kalshi",
                "status": "OK",
                "search_mode": "BOUNDED_OPEN_EVENTS_LOCAL_TEXT_RANKING",
                "candidates": [
                    {
                        "provider": "kalshi",
                        "identifier": "KXFEDSEP-CUT",
                        "market_title": "Will the Fed cut rates in September?",
                        "status": "CANDIDATE_ONLY_IDENTITY_UNVERIFIED",
                        "settlement_compatible_for_rv": False,
                    }
                ],
            },
            "polymarket": {
                "provider": "polymarket",
                "status": "OK",
                "search_mode": "POLYMARKET_PUBLIC_SEARCH_EVENT_EXPANSION",
                "candidates": [
                    {
                        "provider": "polymarket",
                        "identifier": "701",
                        "market_title": "Will the Fed cut rates in September?",
                        "status": "CANDIDATE_ONLY_IDENTITY_UNVERIFIED",
                        "settlement_compatible_for_rv": False,
                    }
                ],
            },
        },
        "candidate_pairs": [
            {
                "pair_id": "PAIR-DEMO",
                "kalshi_identifier": "KXFEDSEP-CUT",
                "polymarket_identifier": "701",
                "status": "CANDIDATE_ONLY_IDENTITY_UNVERIFIED",
                "settlement_compatible_for_rv": False,
            }
        ],
        "pair_count": 1,
        "identity_status": "CANDIDATE_ONLY_IDENTITY_UNVERIFIED",
        "candidate_match_is_settlement_proof": False,
        "next_required_step": "LOAD_EXACT_CONTRACTS_AND_RUN_SETTLEMENT_IDENTITY_VALIDATOR",
        "execution_status": "DISCOVERY_ONLY_NO_ORDER_PLACEMENT",
    }


class R12Step3HTTPTests(unittest.TestCase):
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

    def test_discovery_endpoint_returns_candidate_only_artifact(self):
        with patch.object(serve_r12.discovery_engine, "discover_market_candidates", return_value=discovery_fixture()) as mock_discover:
            status, headers, payload = self.post("/api/r12/discovery", {"query": "Fed September rate cut"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["action"], "r12_market_discovery")
        self.assertEqual(payload["discovery"]["pair_count"], 1)
        self.assertFalse(payload["discovery"]["candidate_match_is_settlement_proof"])
        self.assertEqual(payload["discovery"]["identity_status"], "CANDIDATE_ONLY_IDENTITY_UNVERIFIED")
        self.assertIn("application/json", headers.get("Content-Type", ""))
        self.assertEqual(headers.get("Connection"), "close")
        mock_discover.assert_called_once_with("Fed September rate cut")

    def test_invalid_discovery_query_returns_structured_json_error(self):
        status, _, payload = self.post("/api/r12/discovery", {"query": ""})
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["action"], "r12_market_discovery")
        self.assertEqual(payload["error"]["code"], "ValueError")
        self.assertIn("query is required", payload["error"]["message"])


if __name__ == "__main__":
    unittest.main()
