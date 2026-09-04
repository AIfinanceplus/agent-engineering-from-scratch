import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import serve_r12
from r12_event_sources import normalize_kalshi_contract, normalize_polymarket_contract
from r12_identity import validate_event_identity
from serve_r12 import R12VisualizerHandler
from test_r12_event_sources import kalshi_event, kalshi_market, kalshi_series, poly_books, polymarket_market
from test_r12_identity import full_attestation, rules_analysis
from test_r12_execution import execution_contracts, explicit_zero_fee_model


class TestHandler(R12VisualizerHandler):
    def log_message(self, format, *args):
        pass


def normalized_contracts():
    return (
        normalize_kalshi_contract(kalshi_market(), event=kalshi_event(), series=kalshi_series()),
        normalize_polymarket_contract(polymarket_market(), books=poly_books()),
    )


class R12Step2HTTPTests(unittest.TestCase):
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

    def test_market_contract_endpoint_dispatches_exact_public_provider_adapter(self):
        kalshi, poly = normalized_contracts()
        with patch.object(serve_r12.event_sources, "fetch_kalshi_market_contract", return_value=kalshi) as kfetch:
            status, headers, payload = self.post(
                "/api/r12/market-contract",
                {"provider": "kalshi", "identifier": "KX-DEMO"},
            )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["contract"]["provider"], "kalshi")
        kfetch.assert_called_once_with("KX-DEMO")
        self.assertIn("application/json", headers.get("Content-Type", ""))
        self.assertEqual(headers.get("Connection"), "close")

        with patch.object(serve_r12.event_sources, "fetch_polymarket_market_contract", return_value=poly) as pfetch:
            status, _, payload = self.post(
                "/api/r12/market-contract",
                {"provider": "polymarket", "identifier": "703257"},
            )
        self.assertEqual(status, 200)
        self.assertEqual(payload["contract"]["provider"], "polymarket")
        pfetch.assert_called_once_with("703257")

    def test_identity_endpoint_never_auto_approves_without_attestation(self):
        kalshi, poly = normalized_contracts()
        analysis = rules_analysis(kalshi, poly)
        status, _, payload = self.post(
            "/api/r12/identity",
            {"kalshi_contract": kalshi, "polymarket_contract": poly, "rules_analysis": analysis},
        )
        self.assertEqual(status, 200)
        identity = payload["identity"]
        self.assertEqual(identity["status"], "IDENTITY_UNVERIFIED_MANUAL_REVIEW_REQUIRED")
        self.assertFalse(identity["settlement_compatible_for_rv"])

    def test_rules_analysis_endpoint_returns_fingerprint_bound_non_approval_artifact(self):
        kalshi, poly = normalized_contracts()
        status, _, payload = self.post(
            "/api/r12/rules-analysis",
            {"kalshi_contract": kalshi, "polymarket_contract": poly},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["action"], "r12_settlement_rules_analysis")
        analysis = payload["analysis"]
        self.assertTrue(analysis["eligible_for_identity_review"])
        self.assertFalse(analysis["can_auto_approve_identity"])
        self.assertTrue(analysis["contracts"]["kalshi"]["fingerprint"])

    def test_verified_identity_can_run_locked_cross_market_complement_scan(self):
        kalshi, poly = normalized_contracts()
        identity = validate_event_identity(
            kalshi,
            poly,
            rules_analysis=rules_analysis(kalshi, poly),
            attestation=full_attestation(),
        )
        status, _, payload = self.post(
            "/api/r12/cross-market-rv",
            {
                "identity": identity,
                "kalshi_contract": kalshi,
                "polymarket_contract": poly,
                "estimated_total_cost_per_basket": 0.01,
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        scan = payload["scan"]
        self.assertEqual(scan["paper_signal_count"], 1)
        self.assertEqual(scan["opportunities"][0]["execution_status"], "PAPER_SIGNAL_ONLY_NO_AUTO_EXECUTION")

    def test_unverified_identity_cross_market_endpoint_fails_closed(self):
        kalshi, poly = normalized_contracts()
        identity = validate_event_identity(kalshi, poly, rules_analysis=rules_analysis(kalshi, poly))
        status, _, payload = self.post(
            "/api/r12/cross-market-rv",
            {"identity": identity, "kalshi_contract": kalshi, "polymarket_contract": poly},
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertIn("SETTLEMENT_COMPATIBLE_FOR_RV", payload["error"]["message"])

    def test_depth_execution_endpoint_requires_full_target_and_explicit_fees(self):
        kalshi, poly = execution_contracts()
        identity = validate_event_identity(
            kalshi,
            poly,
            rules_analysis=rules_analysis(kalshi, poly),
            attestation=full_attestation(),
        )
        status, _, payload = self.post(
            "/api/r12/execution-quote",
            {
                "identity": identity,
                "kalshi_contract": kalshi,
                "polymarket_contract": poly,
                "target_contracts": 10,
                "fee_model": explicit_zero_fee_model(),
                "latency_buffer_bps": 0,
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["action"], "r12_execution_quote")
        self.assertEqual(payload["quote"]["paper_signal_count"], 1)

        status, _, payload = self.post(
            "/api/r12/execution-quote",
            {
                "identity": identity,
                "kalshi_contract": kalshi,
                "polymarket_contract": poly,
                "target_contracts": 11,
                "fee_model": explicit_zero_fee_model(),
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["quote"]["paper_signal_count"], 0)
        self.assertEqual(payload["quote"]["baskets_checked"][0]["status"], "INSUFFICIENT_DEPTH_FOR_TARGET")

    def test_invalid_provider_returns_structured_json(self):
        status, _, payload = self.post(
            "/api/r12/market-contract",
            {"provider": "other", "identifier": "x"},
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["action"], "r12_market_contract")


if __name__ == "__main__":
    unittest.main()
