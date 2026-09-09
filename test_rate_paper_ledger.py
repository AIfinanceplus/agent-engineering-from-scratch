import tempfile
import unittest

from rate_paper_ledger import PaperLedger
from rate_parallel import ParallelRunError, RateParallelAgent
from test_rate_strategy import completed_steepener_history


class RatePaperLedgerTests(unittest.TestCase):
    def simulation(self):
        return RateParallelAgent(
            {"fetch_public_rate_history": lambda **_: completed_steepener_history()},
            sleeper=lambda _: None,
        ).run_once()["simulation"]

    def test_append_replay_is_idempotent_and_durable(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = PaperLedger(f"{directory}/events.jsonl")
            simulation = self.simulation()
            result = ledger.reconcile(simulation)
            replayed = ledger.replay()
            self.assertTrue(result["passed"])
            self.assertEqual(replayed["event_count"], 3)
            ledger.append("paper_trade_closed", {"paper_trade_id": replayed["paper_trade_id"], "net_pnl_usd": simulation["completed_trade"]["net_pnl_usd"]}, idempotency_key=f"{replayed['paper_trade_id']}:close")
            self.assertEqual(ledger.replay()["event_count"], 3)

    def test_reconciliation_reports_expected_vs_replayed_difference(self):
        with tempfile.TemporaryDirectory() as directory:
            result = PaperLedger(f"{directory}/events.jsonl").reconcile(self.simulation(), tamper=True)
            self.assertFalse(result["passed"])
            self.assertEqual(result["status"], "MISMATCH")
            self.assertEqual(result["differences"][0]["field"], "net_pnl_usd")

    def test_parallel_runtime_blocks_eval_on_ledger_mismatch(self):
        agent = RateParallelAgent(
            {"fetch_public_rate_history": lambda **_: completed_steepener_history()},
            sleeper=lambda _: None,
        )
        with self.assertRaises(ParallelRunError) as caught:
            agent.run_once(demo_scenario="ledger_mismatch")
        self.assertEqual(caught.exception.code, "PAPER_LEDGER_MISMATCH")
        self.assertEqual(caught.exception.task_id, "LG1")
        names = [event["event"] for event in caught.exception.trace]
        self.assertIn("ledger_mismatch_detected", names)
        self.assertNotIn("eval_started", names)


if __name__ == "__main__":
    unittest.main()
