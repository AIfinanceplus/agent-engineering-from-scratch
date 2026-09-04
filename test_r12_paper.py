import copy
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

from r12_agent import JsonR12StrategyRunStore, R12StrategyAgent
from r12_paper import (
    JsonlR12PaperLedgerStore,
    R12PaperLedger,
    evaluate_r12_paper_trade,
    replay_paper_events,
)
from r12_tooling import R12_MARKET_CONTRACT_TOOL, register_r12_tools
from test_r12_execution import execution_contracts, explicit_zero_fee_model
from test_r12_identity import full_attestation
from tools import TOOL_REGISTRY


class R12PaperLedgerTests(unittest.TestCase):
    def setUp(self):
        register_r12_tools()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.agent = R12StrategyAgent(JsonR12StrategyRunStore(f"{self.temp.name}/agent"))
        self.ledger = R12PaperLedger(JsonlR12PaperLedgerStore(f"{self.temp.name}/paper"))
        self.kalshi, self.poly = execution_contracts()

        def fake_fetch(provider, identifier):
            del identifier
            return copy.deepcopy(self.kalshi if provider == "kalshi" else self.poly)

        fake_tool = replace(R12_MARKET_CONTRACT_TOOL, function=fake_fetch)
        with patch.dict(TOOL_REGISTRY, {R12_MARKET_CONTRACT_TOOL.name: fake_tool}):
            waiting = self.agent.start_exact_pair(
                run_id="R12A-PAPER-TEST",
                kalshi_identifier=self.kalshi["provider_market_id"],
                polymarket_identifier=self.poly["provider_market_id"],
                target_contracts=10,
                fee_model=explicit_zero_fee_model(),
            )
            self.run = self.agent.approve_and_resume(waiting["run_id"], full_attestation())
        self.opportunity = self.run["results"]["E1"]["opportunities"][0]
        self.trade = self.ledger.create_from_agent_run(
            self.run,
            self.opportunity["opportunity_id"],
            "create-paper-test",
        )

    def leg_ids(self):
        return [leg["leg_id"] for leg in self.trade["legs"]]

    def test_create_is_lineage_bound_and_never_auto_fills(self):
        self.assertEqual(self.trade["status"], "PENDING_PAPER_FILL")
        self.assertEqual(self.trade["source_run_id"], self.run["run_id"])
        self.assertEqual(self.trade["opportunity_id"], self.opportunity["opportunity_id"])
        self.assertEqual(self.trade["event_count"], 1)
        self.assertTrue(all(leg["filled_quantity"] == 0 for leg in self.trade["legs"]))
        self.assertFalse(self.trade["guardrails"]["automatic_execution"])
        self.assertTrue(evaluate_r12_paper_trade(self.trade)["passed"])

        retried = self.ledger.create_from_agent_run(
            self.run,
            self.opportunity["opportunity_id"],
            "create-paper-test",
        )
        self.assertEqual(retried["event_count"], 1)
        self.assertEqual(retried["last_event_hash"], self.trade["last_event_hash"])

        reloaded = R12PaperLedger(JsonlR12PaperLedgerStore(f"{self.temp.name}/paper")).get(
            self.trade["paper_trade_id"]
        )
        self.assertEqual(reloaded, self.trade)

    def test_one_leg_partial_fill_exposes_leg_risk_and_mtm(self):
        first, _second = self.leg_ids()
        partial = self.ledger.record_fill(
            self.trade["paper_trade_id"],
            leg_id=first,
            quantity=4,
            price=0.45,
            fee=0.1,
            idempotency_key="fill-first-four",
        )
        self.assertEqual(partial["status"], "PARTIALLY_FILLED_LEG_RISK")
        self.assertEqual(partial["risk"]["matched_quantity"], 0)
        self.assertEqual(partial["risk"]["leg_risk_quantity"], 4)
        self.assertFalse(partial["risk"]["fully_hedged"])

        marked = self.ledger.mark_to_market(
            self.trade["paper_trade_id"],
            marks={first: 0.50},
            idempotency_key="mark-first-leg",
        )
        self.assertAlmostEqual(marked["pnl"]["acquisition_cost"], 1.9)
        self.assertAlmostEqual(marked["pnl"]["marked_value"], 2.0)
        self.assertAlmostEqual(marked["pnl"]["mark_to_market_pnl"], 0.1)

    def test_matching_second_fill_removes_leg_risk_but_is_not_full_target(self):
        first, second = self.leg_ids()
        self.ledger.record_fill(
            self.trade["paper_trade_id"],
            leg_id=first,
            quantity=4,
            price=0.45,
            fee=0,
            idempotency_key="match-first",
        )
        matched = self.ledger.record_fill(
            self.trade["paper_trade_id"],
            leg_id=second,
            quantity=4,
            price=0.49,
            fee=0,
            idempotency_key="match-second",
        )
        self.assertEqual(matched["status"], "MATCHED_PARTIAL")
        self.assertEqual(matched["risk"]["matched_quantity"], 4)
        self.assertEqual(matched["risk"]["leg_risk_quantity"], 0)
        self.assertTrue(matched["risk"]["fully_hedged"])
        self.assertFalse(matched["risk"]["fully_matched_target"])

    def test_full_fills_then_settlement_computes_realized_pnl(self):
        for index, leg in enumerate(self.trade["legs"], start=1):
            self.ledger.record_fill(
                self.trade["paper_trade_id"],
                leg_id=leg["leg_id"],
                quantity=10,
                price=leg["quoted_vwap"],
                fee=leg["quoted_fee"],
                idempotency_key=f"full-fill-{index}",
            )
        filled = self.ledger.get(self.trade["paper_trade_id"])
        self.assertEqual(filled["status"], "FULLY_MATCHED")
        self.assertTrue(filled["risk"]["fully_matched_target"])

        settled = self.ledger.settle(
            self.trade["paper_trade_id"],
            winning_outcome="YES",
            idempotency_key="settle-yes",
        )
        self.assertEqual(settled["status"], "SETTLED")
        self.assertEqual(settled["pnl"]["settlement_payoff"], 10)
        self.assertAlmostEqual(
            settled["pnl"]["realized_pnl"],
            10 - settled["pnl"]["acquisition_cost"],
        )
        self.assertTrue(evaluate_r12_paper_trade(settled)["passed"])

    def test_fill_idempotency_replays_and_conflicting_reuse_fails(self):
        first = self.leg_ids()[0]
        first_result = self.ledger.record_fill(
            self.trade["paper_trade_id"],
            leg_id=first,
            quantity=2,
            price=0.44,
            fee=0,
            idempotency_key="same-fill-key",
        )
        replayed = self.ledger.record_fill(
            self.trade["paper_trade_id"],
            leg_id=first,
            quantity=2,
            price=0.44,
            fee=0,
            idempotency_key="same-fill-key",
        )
        self.assertEqual(replayed["event_count"], first_result["event_count"])
        self.assertEqual(replayed["last_event_hash"], first_result["last_event_hash"])

        with self.assertRaisesRegex(ValueError, "different paper command"):
            self.ledger.record_fill(
                self.trade["paper_trade_id"],
                leg_id=first,
                quantity=3,
                price=0.44,
                fee=0,
                idempotency_key="same-fill-key",
            )

    def test_overfill_unknown_leg_and_invalid_source_fail_closed(self):
        first = self.leg_ids()[0]
        with self.assertRaisesRegex(ValueError, "exceeds remaining"):
            self.ledger.record_fill(
                self.trade["paper_trade_id"],
                leg_id=first,
                quantity=11,
                price=0.5,
                fee=0,
                idempotency_key="overfill",
            )
        with self.assertRaisesRegex(ValueError, "unknown paper leg_id"):
            self.ledger.record_fill(
                self.trade["paper_trade_id"],
                leg_id="unknown:YES",
                quantity=1,
                price=0.5,
                fee=0,
                idempotency_key="unknown-leg",
            )

        incomplete = copy.deepcopy(self.run)
        incomplete["status"] = "WAITING_HUMAN_IDENTITY_APPROVAL"
        with self.assertRaisesRegex(ValueError, "COMPLETED_PAPER_QUOTE"):
            self.ledger.create_from_agent_run(incomplete, self.opportunity["opportunity_id"], "bad-source")

    def test_cancel_preserves_partial_exposure_and_only_allows_settlement(self):
        first = self.leg_ids()[0]
        self.ledger.record_fill(
            self.trade["paper_trade_id"],
            leg_id=first,
            quantity=3,
            price=0.45,
            fee=0,
            idempotency_key="cancel-fill",
        )
        cancelled = self.ledger.cancel(
            self.trade["paper_trade_id"],
            reason="paper quote expired",
            idempotency_key="cancel-command",
        )
        self.assertEqual(cancelled["status"], "CANCELLED_WITH_LEG_RISK")
        marked = self.ledger.mark_to_market(
            self.trade["paper_trade_id"],
            marks={first: 0.5},
            idempotency_key="mark-after-cancel",
        )
        self.assertEqual(marked["status"], "CANCELLED_WITH_LEG_RISK")
        with self.assertRaisesRegex(ValueError, "marks or settlement"):
            self.ledger.record_fill(
                self.trade["paper_trade_id"],
                leg_id=first,
                quantity=1,
                price=0.5,
                fee=0,
                idempotency_key="fill-after-cancel",
            )
        settled = self.ledger.settle(
            self.trade["paper_trade_id"],
            winning_outcome="NO",
            idempotency_key="settle-cancelled",
        )
        self.assertEqual(settled["status"], "SETTLED")

    def test_hash_chain_detects_tampering(self):
        first = self.leg_ids()[0]
        filled = self.ledger.record_fill(
            self.trade["paper_trade_id"],
            leg_id=first,
            quantity=1,
            price=0.45,
            fee=0,
            idempotency_key="tamper-fill",
        )
        tampered = copy.deepcopy(filled["events"])
        tampered[-1]["payload"]["price"] = 0.01
        with self.assertRaisesRegex(ValueError, "event hash mismatch|command fingerprint mismatch"):
            replay_paper_events(tampered)

    def test_expire_unfilled_intent_is_terminal_and_replayable(self):
        expired = self.ledger.expire(
            self.trade["paper_trade_id"],
            reason="visible quote window ended",
            idempotency_key="expire-unfilled",
        )
        self.assertEqual(expired["status"], "EXPIRED_UNFILLED")
        self.assertEqual(expired["pnl"]["acquisition_cost"], 0)
        self.assertTrue(evaluate_r12_paper_trade(expired)["passed"])


if __name__ == "__main__":
    unittest.main()
