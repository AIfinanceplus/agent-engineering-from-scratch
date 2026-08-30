import math
import unittest

from r12_event_sources import normalize_kalshi_contract, normalize_polymarket_contract
from r12_execution import quote_cross_market_execution
from r12_identity import validate_event_identity
from r12_tooling import R12_EXECUTION_QUOTE_TOOL, register_r12_tools
from test_r12_event_sources import kalshi_event, kalshi_market, kalshi_series, polymarket_market
from test_r12_identity import full_attestation


def execution_contracts():
    kalshi_book = {
        "orderbook_fp": {
            "yes_dollars": [["0.4600", "20.00"]],
            "no_dollars": [["0.5500", "10.00"], ["0.5600", "5.00"]],
        }
    }
    poly_books = {
        "YES": {
            "timestamp": "1782753404902",
            "hash": "yes-hash",
            "bids": [{"price": "0.49", "size": "20"}],
            "asks": [{"price": "0.50", "size": "10"}],
        },
        "NO": {
            "timestamp": "1782753404903",
            "hash": "no-hash",
            "bids": [{"price": "0.48", "size": "20"}],
            "asks": [{"price": "0.49", "size": "10"}],
        },
    }
    return (
        normalize_kalshi_contract(
            kalshi_market(),
            event=kalshi_event(),
            series=kalshi_series(),
            orderbook=kalshi_book,
        ),
        normalize_polymarket_contract(polymarket_market(), books=poly_books),
    )


def explicit_zero_fee_model():
    return {
        "source": "reviewed_provider_fee_schedules",
        "kalshi": {
            "fee_rate_on_notional": 0.0,
            "fee_per_contract": 0.0,
            "fixed_fee_per_order": 0.0,
        },
        "polymarket": {
            "fee_rate_on_notional": 0.0,
            "fee_per_contract": 0.0,
            "fixed_fee_per_order": 0.0,
        },
    }


class R12ExecutionQuoteTests(unittest.TestCase):
    def setUp(self):
        self.kalshi, self.poly = execution_contracts()
        self.identity = validate_event_identity(self.kalshi, self.poly, attestation=full_attestation())

    def test_walks_visible_depth_and_emits_only_fully_matched_paper_signal(self):
        quote = quote_cross_market_execution(
            self.identity,
            self.kalshi,
            self.poly,
            target_contracts=10,
            fee_model=explicit_zero_fee_model(),
        )
        self.assertEqual(quote["artifact_type"], "r12_execution_quality_scan")
        self.assertEqual(quote["paper_signal_count"], 1)
        basket = quote["opportunities"][0]["market_view"]["execution_quote"]
        self.assertTrue(basket["full_fill_at_target"])
        self.assertAlmostEqual(basket["legs"][0]["vwap"], 0.445)
        self.assertAlmostEqual(basket["legs"][0]["slippage_vs_best_ask"], 0.005)
        self.assertAlmostEqual(basket["net_edge_total"], 0.65)
        self.assertEqual(quote["execution_policy"], "PAPER_SIGNAL_ONLY_NO_AUTO_EXECUTION")

    def test_insufficient_depth_never_treats_partial_legs_as_locked(self):
        quote = quote_cross_market_execution(
            self.identity,
            self.kalshi,
            self.poly,
            target_contracts=11,
            fee_model=explicit_zero_fee_model(),
        )
        self.assertEqual(quote["paper_signal_count"], 0)
        first = quote["baskets_checked"][0]
        self.assertEqual(first["status"], "INSUFFICIENT_DEPTH_FOR_TARGET")
        self.assertFalse(first["full_fill_at_target"])
        self.assertIsNone(first["net_edge_total"])

    def test_missing_explicit_fee_model_fails_closed(self):
        quote = quote_cross_market_execution(
            self.identity,
            self.kalshi,
            self.poly,
            target_contracts=10,
        )
        self.assertEqual(quote["fee_model_status"], "MISSING_EXPLICIT_FEE_MODEL")
        self.assertEqual(quote["paper_signal_count"], 0)
        self.assertEqual(quote["baskets_checked"][0]["status"], "EXPLICIT_FEE_MODEL_REQUIRED")

    def test_latency_buffer_can_remove_visible_book_edge(self):
        quote = quote_cross_market_execution(
            self.identity,
            self.kalshi,
            self.poly,
            target_contracts=10,
            fee_model=explicit_zero_fee_model(),
            latency_buffer_bps=400,
        )
        self.assertEqual(quote["paper_signal_count"], 0)
        self.assertEqual(quote["baskets_checked"][0]["status"], "NO_EDGE_AFTER_DEPTH_FEES_LATENCY")

    def test_opportunity_id_changes_when_executable_quote_inputs_change(self):
        first = quote_cross_market_execution(
            self.identity,
            self.kalshi,
            self.poly,
            target_contracts=10,
            fee_model=explicit_zero_fee_model(),
            latency_buffer_bps=0,
        )
        second = quote_cross_market_execution(
            self.identity,
            self.kalshi,
            self.poly,
            target_contracts=10,
            fee_model=explicit_zero_fee_model(),
            latency_buffer_bps=1,
        )
        self.assertEqual(first["paper_signal_count"], 1)
        self.assertEqual(second["paper_signal_count"], 1)
        self.assertNotEqual(first["opportunities"][0]["opportunity_id"], second["opportunities"][0]["opportunity_id"])

    def test_identity_and_finite_numeric_boundaries_fail_closed(self):
        unverified = validate_event_identity(self.kalshi, self.poly)
        with self.assertRaisesRegex(ValueError, "SETTLEMENT_COMPATIBLE_FOR_RV"):
            quote_cross_market_execution(
                unverified,
                self.kalshi,
                self.poly,
                target_contracts=10,
                fee_model=explicit_zero_fee_model(),
            )
        with self.assertRaisesRegex(ValueError, "finite"):
            quote_cross_market_execution(
                self.identity,
                self.kalshi,
                self.poly,
                target_contracts=math.inf,
                fee_model=explicit_zero_fee_model(),
            )

    def test_execution_quote_is_registered_as_low_risk_non_execution_tool(self):
        names = register_r12_tools()
        self.assertIn("quote_r12_cross_market_execution", names)
        self.assertEqual(R12_EXECUTION_QUOTE_TOOL.risk, "low")
        self.assertIn("never places orders", R12_EXECUTION_QUOTE_TOOL.description)


if __name__ == "__main__":
    unittest.main()
