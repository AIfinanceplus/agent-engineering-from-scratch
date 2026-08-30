import copy
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
from r12_paper import JsonlR12PaperLedgerStore, R12PaperLedger
from r12_tooling import R12_MARKET_CONTRACT_TOOL, register_r12_tools
from serve_r12 import R12VisualizerHandler
from test_r12_execution import execution_contracts, explicit_zero_fee_model
from test_r12_identity import full_attestation
from tools import TOOL_REGISTRY


class TestHandler(R12VisualizerHandler):
    def log_message(self, format, *args):
        pass


class R12Step5HTTPTests(unittest.TestCase):
    def setUp(self):
        register_r12_tools()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.agent = R12StrategyAgent(JsonR12StrategyRunStore(f"{self.temp.name}/agent"))
        self.ledger = R12PaperLedger(JsonlR12PaperLedgerStore(f"{self.temp.name}/paper"))
        self.agent_patch = patch.object(serve_r12, "R12_STRATEGY_AGENT", self.agent)
        self.ledger_patch = patch.object(serve_r12, "R12_PAPER_LEDGER", self.ledger)
        self.agent_patch.start()
        self.ledger_patch.start()
        self.addCleanup(self.agent_patch.stop)
        self.addCleanup(self.ledger_patch.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop_server)
        self.host, self.port = self.server.server_address
        self.kalshi, self.poly = execution_contracts()
        self.run = self._completed_run()
        self.opportunity_id = self.run["results"]["E1"]["opportunities"][0]["opportunity_id"]

    def _stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _completed_run(self):
        def fake_fetch(provider, identifier):
            del identifier
            return copy.deepcopy(self.kalshi if provider == "kalshi" else self.poly)

        fake_tool = replace(R12_MARKET_CONTRACT_TOOL, function=fake_fetch)
        with patch.dict(TOOL_REGISTRY, {R12_MARKET_CONTRACT_TOOL.name: fake_tool}):
            waiting = self.agent.start_exact_pair(
                run_id="R12A-HTTP-PAPER",
                kalshi_identifier=self.kalshi["provider_market_id"],
                polymarket_identifier=self.poly["provider_market_id"],
                target_contracts=10,
                fee_model=explicit_zero_fee_model(),
            )
            return self.agent.approve_and_resume(waiting["run_id"], full_attestation())

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

    def create_trade(self):
        return self.post(
            "/api/r12/paper/create",
            {
                "run_id": self.run["run_id"],
                "opportunity_id": self.opportunity_id,
                "idempotency_key": "http-create",
            },
        )

    def test_create_fill_idempotent_retry_and_status_replay(self):
        status, created = self.create_trade()
        self.assertEqual(status, 200)
        self.assertTrue(created["ok"])
        self.assertEqual(created["action"], "r12_paper_create")
        self.assertEqual(created["trade"]["status"], "PENDING_PAPER_FILL")
        self.assertTrue(created["eval"]["passed"])
        trade_id = created["trade"]["paper_trade_id"]
        leg = created["trade"]["legs"][0]
        fill_request = {
            "paper_trade_id": trade_id,
            "leg_id": leg["leg_id"],
            "quantity": 2,
            "price": 0.45,
            "fee": 0,
            "idempotency_key": "http-fill-one",
        }
        status, filled = self.post("/api/r12/paper/fill", fill_request)
        self.assertEqual(status, 200)
        self.assertEqual(filled["trade"]["status"], "PARTIALLY_FILLED_LEG_RISK")
        event_count = filled["trade"]["event_count"]

        status, retried = self.post("/api/r12/paper/fill", fill_request)
        self.assertEqual(status, 200)
        self.assertEqual(retried["trade"]["event_count"], event_count)

        status, loaded = self.post("/api/r12/paper/status", {"paper_trade_id": trade_id})
        self.assertEqual(status, 200)
        self.assertEqual(loaded["trade"]["last_event_hash"], filled["trade"]["last_event_hash"])

    def test_mark_cancel_and_settle_partial_exposure(self):
        _, created = self.create_trade()
        trade_id = created["trade"]["paper_trade_id"]
        leg = created["trade"]["legs"][0]
        self.post(
            "/api/r12/paper/fill",
            {
                "paper_trade_id": trade_id,
                "leg_id": leg["leg_id"],
                "quantity": 3,
                "price": 0.4,
                "fee": 0.1,
                "idempotency_key": "http-partial",
            },
        )
        status, marked = self.post(
            "/api/r12/paper/mark",
            {"paper_trade_id": trade_id, "marks": {leg["leg_id"]: 0.5}, "idempotency_key": "http-mark"},
        )
        self.assertEqual(status, 200)
        self.assertAlmostEqual(marked["trade"]["pnl"]["mark_to_market_pnl"], 0.2)

        status, cancelled = self.post(
            "/api/r12/paper/cancel",
            {"paper_trade_id": trade_id, "reason": "test cancel", "idempotency_key": "http-cancel"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(cancelled["trade"]["status"], "CANCELLED_WITH_LEG_RISK")

        status, settled = self.post(
            "/api/r12/paper/settle",
            {"paper_trade_id": trade_id, "winning_outcome": "YES", "idempotency_key": "http-settle"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(settled["trade"]["status"], "SETTLED")
        self.assertIsNotNone(settled["trade"]["pnl"]["realized_pnl"])

    def test_missing_idempotency_and_overfill_return_structured_errors(self):
        status, payload = self.post(
            "/api/r12/paper/create",
            {"run_id": self.run["run_id"], "opportunity_id": self.opportunity_id},
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["action"], "r12_paper_create")
        self.assertIn("idempotency_key", payload["error"]["message"])

        _, created = self.create_trade()
        leg = created["trade"]["legs"][0]
        status, payload = self.post(
            "/api/r12/paper/fill",
            {
                "paper_trade_id": created["trade"]["paper_trade_id"],
                "leg_id": leg["leg_id"],
                "quantity": 11,
                "price": 0.5,
                "fee": 0,
                "idempotency_key": "http-overfill",
            },
        )
        self.assertEqual(status, 400)
        self.assertIn("exceeds remaining", payload["error"]["message"])


if __name__ == "__main__":
    unittest.main()
