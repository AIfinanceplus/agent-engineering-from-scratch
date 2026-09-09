import copy
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

from r12_agent import JsonR12StrategyRunStore, R12StrategyAgent
from r12_paper import JsonlR12PaperLedgerStore, R12PaperLedger
from r12_portfolio import (
    R12PaperPortfolio,
    R12PaperPortfolioLimits,
    R12PortfolioLimitExceeded,
    evaluate_r12_paper_portfolio,
)
from r12_tooling import R12_MARKET_CONTRACT_TOOL, register_r12_tools
from test_r12_execution import execution_contracts, explicit_zero_fee_model
from test_r12_identity import full_attestation
from tools import TOOL_REGISTRY


class R12PaperPortfolioTests(unittest.TestCase):
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
                run_id="R12A-PORTFOLIO-TEST",
                kalshi_identifier=self.kalshi["provider_market_id"],
                polymarket_identifier=self.poly["provider_market_id"],
                target_contracts=10,
                fee_model=explicit_zero_fee_model(),
            )
            self.run = self.agent.approve_and_resume(waiting["run_id"], full_attestation())
        self.opportunity_id = self.run["results"]["E1"]["opportunities"][0]["opportunity_id"]

    def portfolio(self, **limit_overrides):
        limits = R12PaperPortfolioLimits(**limit_overrides) if limit_overrides else R12PaperPortfolioLimits()
        return R12PaperPortfolio(self.ledger, limits)

    def create(self, portfolio, key="portfolio-create"):
        return portfolio.create_from_agent_run(self.run, self.opportunity_id, key)

    def test_replays_all_ledgers_and_aggregates_provider_identity_and_mtm(self):
        portfolio = self.portfolio()
        first = self.create(portfolio, "aggregate-first")
        second = self.create(portfolio, "aggregate-second")
        first_leg = first["legs"][0]
        second_leg = second["legs"][1]
        portfolio.record_fill(
            first["paper_trade_id"],
            leg_id=first_leg["leg_id"],
            quantity=4,
            price=0.45,
            fee=0.1,
            idempotency_key="aggregate-fill-first",
        )
        portfolio.record_fill(
            second["paper_trade_id"],
            leg_id=second_leg["leg_id"],
            quantity=2,
            price=0.49,
            fee=0.02,
            idempotency_key="aggregate-fill-second",
        )

        snapshot = portfolio.status()
        self.assertEqual(snapshot["summary"]["trade_count"], 2)
        self.assertEqual(snapshot["summary"]["unsettled_trade_count"], 2)
        self.assertAlmostEqual(snapshot["summary"]["unsettled_acquisition_cost"], 2.9)
        self.assertEqual(snapshot["summary"]["total_leg_risk_quantity"], 6)
        self.assertFalse(snapshot["summary"]["mark_to_market_complete"])
        self.assertIsNone(snapshot["summary"]["mark_to_market_pnl"])
        self.assertEqual(set(snapshot["by_provider"]), {"kalshi", "polymarket"})
        identity = snapshot["by_identity"][first["identity_id"]]
        self.assertEqual(identity["trade_count"], 2)
        self.assertAlmostEqual(identity["acquisition_cost"], 2.9)
        self.assertFalse(snapshot["guardrails"]["automatic_execution"])
        self.assertFalse(snapshot["guardrails"]["cross_trade_netting_credit_applied"])
        self.assertTrue(evaluate_r12_paper_portfolio(snapshot)["passed"])

    def test_fill_preflight_blocks_atomically_before_ledger_mutation(self):
        portfolio = self.portfolio(max_total_leg_risk_quantity=3)
        trade = self.create(portfolio)
        leg = trade["legs"][0]
        preflight = portfolio.preflight_fill(
            trade["paper_trade_id"], leg_id=leg["leg_id"], quantity=4, price=0.45, fee=0
        )
        self.assertFalse(preflight["allowed"])
        self.assertEqual(preflight["violations"][0]["limit"], "max_total_leg_risk_quantity")
        self.assertFalse(preflight["guardrails"]["ledger_mutated"])

        with self.assertRaisesRegex(R12PortfolioLimitExceeded, "max_total_leg_risk_quantity"):
            portfolio.record_fill(
                trade["paper_trade_id"],
                leg_id=leg["leg_id"],
                quantity=4,
                price=0.45,
                fee=0,
                idempotency_key="blocked-fill",
            )
        self.assertEqual(self.ledger.get(trade["paper_trade_id"])["event_count"], 1)

    def test_provider_and_same_identity_concentration_limits_fail_closed(self):
        provider_limited = self.portfolio(max_provider_filled_notional=1)
        trade = self.create(provider_limited, "provider-limit-create")
        leg = trade["legs"][0]
        with self.assertRaisesRegex(R12PortfolioLimitExceeded, "max_provider_filled_notional"):
            provider_limited.record_fill(
                trade["paper_trade_id"],
                leg_id=leg["leg_id"],
                quantity=4,
                price=0.45,
                fee=0,
                idempotency_key="provider-block",
            )

        identity_limited = self.portfolio(max_identity_acquisition_cost=2)
        identity_limited.record_fill(
            trade["paper_trade_id"],
            leg_id=leg["leg_id"],
            quantity=4,
            price=0.45,
            fee=0,
            idempotency_key="identity-first-fill",
        )
        other_leg = trade["legs"][1]
        with self.assertRaisesRegex(R12PortfolioLimitExceeded, "max_identity_acquisition_cost"):
            identity_limited.record_fill(
                trade["paper_trade_id"],
                leg_id=other_leg["leg_id"],
                quantity=1,
                price=0.49,
                fee=0,
                idempotency_key="identity-block",
            )

    def test_idempotent_fill_retry_does_not_double_count_at_limit(self):
        portfolio = self.portfolio(max_unsettled_acquisition_cost=1.8, max_identity_acquisition_cost=1.8)
        trade = self.create(portfolio)
        leg = trade["legs"][0]
        first = portfolio.record_fill(
            trade["paper_trade_id"],
            leg_id=leg["leg_id"],
            quantity=4,
            price=0.45,
            fee=0,
            idempotency_key="fill-at-limit",
        )
        retried = portfolio.record_fill(
            trade["paper_trade_id"],
            leg_id=leg["leg_id"],
            quantity=4,
            price=0.45,
            fee=0,
            idempotency_key="fill-at-limit",
        )
        self.assertEqual(retried["event_count"], first["event_count"])
        self.assertEqual(portfolio.status()["summary"]["unsettled_acquisition_cost"], 1.8)

    def test_unsettled_trade_limit_blocks_new_intent_but_retry_still_replays(self):
        portfolio = self.portfolio(max_unsettled_trades=1)
        first = self.create(portfolio, "only-open-slot")
        retried = self.create(portfolio, "only-open-slot")
        self.assertEqual(retried["paper_trade_id"], first["paper_trade_id"])
        with self.assertRaisesRegex(R12PortfolioLimitExceeded, "max_unsettled_trades"):
            self.create(portfolio, "second-open-slot")
        self.assertEqual(len(self.ledger.list_trades()), 1)

    def test_settlement_moves_cost_out_of_unsettled_exposure_and_adds_realized_pnl(self):
        portfolio = self.portfolio()
        trade = self.create(portfolio)
        for index, leg in enumerate(trade["legs"], start=1):
            portfolio.record_fill(
                trade["paper_trade_id"],
                leg_id=leg["leg_id"],
                quantity=10,
                price=leg["quoted_vwap"],
                fee=0,
                idempotency_key=f"settled-full-fill-{index}",
            )
        settled = self.ledger.settle(
            trade["paper_trade_id"], winning_outcome="YES", idempotency_key="portfolio-settle"
        )
        snapshot = portfolio.status()
        self.assertEqual(snapshot["summary"]["unsettled_trade_count"], 0)
        self.assertEqual(snapshot["summary"]["settled_trade_count"], 1)
        self.assertEqual(snapshot["summary"]["unsettled_acquisition_cost"], 0)
        self.assertEqual(snapshot["summary"]["realized_pnl"], settled["pnl"]["realized_pnl"])


if __name__ == "__main__":
    unittest.main()
