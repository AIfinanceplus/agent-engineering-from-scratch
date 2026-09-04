import http.client
import json
import tempfile
import threading
import unittest
from dataclasses import replace
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import serve_r12
from r12_agent import JsonR12StrategyRunStore, R12StrategyAgent
from r12_tooling import R12_MARKET_CONTRACT_TOOL, register_r12_tools
from serve_r12 import R12VisualizerHandler
from test_r12_execution import execution_contracts, explicit_zero_fee_model
from test_r12_identity import full_attestation
from tools import TOOL_REGISTRY


class TestHandler(R12VisualizerHandler):
    def log_message(self, format, *args):
        pass


class R12Step4HTTPTests(unittest.TestCase):
    def setUp(self):
        register_r12_tools()
        self.temp = tempfile.TemporaryDirectory()
        self.agent = R12StrategyAgent(JsonR12StrategyRunStore(self.temp.name))
        self.agent_patch = patch.object(serve_r12, "R12_STRATEGY_AGENT", self.agent)
        self.agent_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address
        self.kalshi, self.poly = execution_contracts()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.agent_patch.stop()
        self.temp.cleanup()

    def post(self, path, payload):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        connection.request(
            "POST",
            path,
            body=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        response = connection.getresponse()
        raw = response.read().decode("utf-8")
        connection.close()
        return response.status, json.loads(raw)

    def fake_fetch(self, provider, identifier):
        return self.kalshi if provider == "kalshi" else self.poly

    def start_run(self):
        fake_tool = replace(R12_MARKET_CONTRACT_TOOL, function=self.fake_fetch)
        with patch.dict(TOOL_REGISTRY, {R12_MARKET_CONTRACT_TOOL.name: fake_tool}):
            return self.post(
                "/api/r12/agent/start",
                {
                    "kalshi_identifier": self.kalshi["provider_market_id"],
                    "polymarket_identifier": self.poly["provider_market_id"],
                    "target_contracts": 10,
                    "fee_model": explicit_zero_fee_model(),
                    "latency_buffer_bps": 0,
                    "estimated_total_cost_per_basket": 0,
                },
            )

    def test_agent_start_pauses_durably_before_identity_tool(self):
        status, payload = self.start_run()
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["action"], "r12_strategy_agent_start")
        run = payload["run"]
        self.assertEqual(run["status"], "WAITING_HUMAN_IDENTITY_APPROVAL")
        self.assertEqual(set(run["results"]), {"K1", "P1", "R1"})
        self.assertNotIn("I1", run["results"])
        self.assertTrue(payload["eval"]["passed"])

        status, loaded = self.post("/api/r12/agent/status", {"run_id": run["run_id"]})
        self.assertEqual(status, 200)
        self.assertEqual(loaded["run"]["status"], "WAITING_HUMAN_IDENTITY_APPROVAL")

    def test_agent_approval_resumes_to_depth_quote(self):
        _, started = self.start_run()
        status, payload = self.post(
            "/api/r12/agent/approve",
            {"run_id": started["run"]["run_id"], "attestation": full_attestation()},
        )
        self.assertEqual(status, 200)
        run = payload["run"]
        self.assertEqual(run["status"], "COMPLETED_PAPER_QUOTE")
        self.assertTrue(run["results"]["I1"]["settlement_compatible_for_rv"])
        self.assertEqual(run["results"]["E1"]["paper_signal_count"], 1)
        self.assertTrue(payload["eval"]["passed"])

        status, resumed = self.post("/api/r12/agent/resume", {"run_id": run["run_id"]})
        self.assertEqual(status, 200)
        self.assertEqual(resumed["run"]["results"]["E1"], run["results"]["E1"])

    def test_agent_incomplete_approval_returns_structured_error(self):
        _, started = self.start_run()
        incomplete = full_attestation()
        incomplete["same_yes_outcome"] = False
        status, payload = self.post(
            "/api/r12/agent/approve",
            {"run_id": started["run"]["run_id"], "attestation": incomplete},
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["action"], "r12_strategy_agent_approve")
        self.assertIn("all six identity checks", payload["error"]["message"])


if __name__ == "__main__":
    unittest.main()
