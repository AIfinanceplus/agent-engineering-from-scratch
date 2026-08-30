import unittest

from r12_event_sources import (
    fetch_kalshi_market_contract,
    fetch_polymarket_market_contract,
    normalize_kalshi_contract,
    normalize_polymarket_contract,
)


def kalshi_market():
    return {
        "ticker": "KX-DEMO",
        "event_ticker": "KX-EVENT",
        "title": "Will the demo event happen?",
        "subtitle": "Demo",
        "status": "open",
        "yes_bid_dollars": "0.47",
        "yes_ask_dollars": "0.48",
        "no_bid_dollars": "0.52",
        "no_ask_dollars": "0.53",
        "last_price_dollars": "0.48",
        "liquidity_dollars": "10000",
        "volume_fp": "500",
        "rules_primary": "Resolves Yes if demo condition is satisfied.",
        "rules_secondary": "Uses official source; edge cases defined here.",
        "close_time": "2026-09-01T16:00:00Z",
        "expiration_time": "2026-09-01T17:00:00Z",
        "strike_type": "greater",
        "floor_strike": 3.0,
    }


def kalshi_event():
    return {"event_ticker": "KX-EVENT", "series_ticker": "KX-SERIES", "title": "Demo Event"}


def kalshi_series():
    return {
        "ticker": "KX-SERIES",
        "settlement_sources": [{"name": "Official Source", "url": "https://example.com/source"}],
        "contract_url": "https://example.com/contract",
        "contract_terms_url": "https://example.com/terms",
    }


def polymarket_market():
    return {
        "id": "703257",
        "conditionId": "0xcondition",
        "question": "Will the demo event happen?",
        "slug": "will-demo-event-happen",
        "description": "Resolves Yes if demo condition is satisfied according to official source.",
        "resolutionSource": "https://example.com/source",
        "startDate": "2026-08-01T00:00:00Z",
        "endDate": "2026-09-01T16:00:00Z",
        "active": True,
        "closed": False,
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.50", "0.50"]',
        "clobTokenIds": '["YES-TOKEN", "NO-TOKEN"]',
        "liquidity": "20000",
        "volume": "1000",
    }


def poly_books():
    return {
        "YES": {"bids": [{"price": "0.49", "size": "20"}], "asks": [{"price": "0.50", "size": "10"}]},
        "NO": {"bids": [{"price": "0.48", "size": "20"}], "asks": [{"price": "0.49", "size": "10"}]},
    }


class R12EventSourceTests(unittest.TestCase):
    def test_kalshi_normalizer_preserves_rules_quotes_and_settlement_sources(self):
        contract = normalize_kalshi_contract(
            kalshi_market(),
            event=kalshi_event(),
            series=kalshi_series(),
            provenance_urls=["market", "event", "series"],
        )
        self.assertEqual(contract["artifact_type"], "r12_market_contract")
        self.assertEqual(contract["provider"], "kalshi")
        self.assertEqual(contract["provider_market_id"], "KX-DEMO")
        self.assertEqual(contract["quotes"]["yes_ask"], 0.48)
        self.assertEqual(contract["quotes"]["no_ask"], 0.53)
        self.assertEqual(contract["quotes"]["quote_status"], "EXECUTABLE_TOP_OF_BOOK_FIELDS")
        self.assertEqual(contract["resolution"]["settlement_sources"][0]["name"], "Official Source")
        self.assertFalse(contract["source_contract"]["authentication_used"])
        self.assertEqual(contract["identity_status"], "NOT_EVALUATED")

    def test_polymarket_normalizer_uses_clob_top_of_book_not_indicative_price(self):
        contract = normalize_polymarket_contract(
            polymarket_market(),
            books=poly_books(),
            provenance_urls=["gamma", "yes-book", "no-book"],
        )
        self.assertEqual(contract["provider"], "polymarket")
        self.assertEqual(contract["outcomes"], ["YES", "NO"])
        self.assertEqual(contract["quotes"]["yes_bid"], 0.49)
        self.assertEqual(contract["quotes"]["yes_ask"], 0.50)
        self.assertEqual(contract["quotes"]["no_ask"], 0.49)
        self.assertEqual(contract["quotes"]["quote_status"], "EXECUTABLE_CLOB_TOP_OF_BOOK")
        self.assertEqual(contract["quotes"]["indicative_outcome_prices"]["YES"], 0.50)
        self.assertEqual(contract["token_ids"]["YES"], "YES-TOKEN")
        self.assertFalse(contract["source_contract"]["authentication_used"])

    def test_kalshi_fetches_exact_market_event_and_series_contract(self):
        calls = []
        def fake_fetch(url):
            calls.append(url)
            if url.endswith("/markets/KX-DEMO"):
                return {"market": kalshi_market()}
            if url.endswith("/events/KX-EVENT"):
                return {"event": kalshi_event()}
            if url.endswith("/series/KX-SERIES"):
                return {"series": kalshi_series()}
            raise AssertionError(url)

        contract = fetch_kalshi_market_contract("KX-DEMO", fetch_json=fake_fetch)
        self.assertEqual(len(calls), 3)
        self.assertTrue(calls[0].endswith("/markets/KX-DEMO"))
        self.assertEqual(contract["provider_series_id"], "KX-SERIES")

    def test_polymarket_fetches_exact_market_and_both_binary_books(self):
        calls = []
        def fake_fetch(url):
            calls.append(url)
            if "/markets/703257" in url:
                return polymarket_market()
            if "token_id=YES-TOKEN" in url:
                return poly_books()["YES"]
            if "token_id=NO-TOKEN" in url:
                return poly_books()["NO"]
            raise AssertionError(url)

        contract = fetch_polymarket_market_contract("703257", fetch_json=fake_fetch)
        self.assertEqual(len(calls), 3)
        self.assertEqual(contract["quotes"]["quote_status"], "EXECUTABLE_CLOB_TOP_OF_BOOK")

    def test_polymarket_without_books_stays_indicative_not_executable(self):
        contract = normalize_polymarket_contract(polymarket_market(), books={})
        self.assertEqual(contract["quotes"]["quote_status"], "INDICATIVE_OR_PARTIAL_QUOTES")
        self.assertIsNone(contract["quotes"]["yes_ask"])


if __name__ == "__main__":
    unittest.main()
