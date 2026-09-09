import unittest

from r12_discovery import (
    build_candidate_pairs,
    discover_kalshi_candidates,
    discover_market_candidates,
    discover_polymarket_candidates,
)


def kalshi_fixture_fetch(url):
    if "/events?" in url:
        return {
            "events": [
                {
                    "event_ticker": "KXFEDSEP",
                    "title": "Federal Reserve September rate decision",
                    "sub_title": "Fed policy meeting",
                },
                {
                    "event_ticker": "KXWEATHER",
                    "title": "New York temperature",
                    "sub_title": "Weather",
                },
            ],
            "cursor": "",
        }
    if url.endswith("/events/KXFEDSEP"):
        markets = [
            {
                "ticker": "KXFEDSEP-CUT",
                "event_ticker": "KXFEDSEP",
                "title": "Will the Fed cut rates in September?",
                "yes_sub_title": "Fed cuts rates",
                "status": "active",
                "close_time": "2026-09-16T18:00:00Z",
            }
        ]
        return {
            "event": {
                "event_ticker": "KXFEDSEP",
                "title": "Federal Reserve September rate decision",
                "sub_title": "Fed policy meeting",
                "markets": markets,
            },
            "markets": markets,
        }
    if url.endswith("/events/KXWEATHER"):
        return {"event": {"event_ticker": "KXWEATHER", "title": "New York temperature", "markets": []}, "markets": []}
    raise AssertionError(f"unexpected Kalshi fixture URL: {url}")


def polymarket_fixture_fetch(url):
    if "/public-search?" in url:
        return {
            "events": [
                {"id": "901", "slug": "fed-september-rate", "title": "Fed September rate decision"}
            ],
            "tags": [],
            "profiles": [],
            "pagination": {"hasMore": False, "totalResults": 1},
        }
    if url.endswith("/events/901"):
        return {
            "id": "901",
            "slug": "fed-september-rate",
            "title": "Fed September rate decision",
            "markets": [
                {
                    "id": "701",
                    "slug": "fed-cut-september",
                    "question": "Will the Fed cut rates in September?",
                    "active": True,
                    "closed": False,
                    "endDate": "2026-09-16T18:00:00Z",
                }
            ],
        }
    raise AssertionError(f"unexpected Polymarket fixture URL: {url}")


class R12DiscoveryTests(unittest.TestCase):
    def test_kalshi_uses_bounded_open_event_listing_and_local_ranking(self):
        result = discover_kalshi_candidates(
            "Fed September rate cut",
            fetch_json=kalshi_fixture_fetch,
            result_limit=5,
        )
        self.assertEqual(result["status"], "OK")
        self.assertFalse(result["official_free_text_search_used"])
        self.assertEqual(result["search_mode"], "BOUNDED_OPEN_EVENTS_LOCAL_TEXT_RANKING")
        self.assertEqual(result["candidates"][0]["identifier"], "KXFEDSEP-CUT")
        self.assertEqual(result["candidates"][0]["status"], "CANDIDATE_ONLY_IDENTITY_UNVERIFIED")
        self.assertFalse(result["candidates"][0]["settlement_compatible_for_rv"])

    def test_polymarket_uses_public_search_then_expands_event_markets(self):
        result = discover_polymarket_candidates(
            "Fed September rate cut",
            fetch_json=polymarket_fixture_fetch,
            result_limit=5,
        )
        self.assertEqual(result["status"], "OK")
        self.assertTrue(result["official_free_text_search_used"])
        self.assertEqual(result["candidates"][0]["identifier"], "701")
        self.assertEqual(result["candidates"][0]["event_id"], "901")
        self.assertEqual(result["candidates"][0]["status"], "CANDIDATE_ONLY_IDENTITY_UNVERIFIED")

    def test_candidate_pair_never_auto_approves_settlement_identity(self):
        kalshi = discover_kalshi_candidates("Fed September rate cut", fetch_json=kalshi_fixture_fetch)["candidates"]
        poly = discover_polymarket_candidates("Fed September rate cut", fetch_json=polymarket_fixture_fetch)["candidates"]
        pairs = build_candidate_pairs(kalshi, poly)
        self.assertEqual(len(pairs), 1)
        self.assertGreater(pairs[0]["pair_score"], 0)
        self.assertEqual(pairs[0]["status"], "CANDIDATE_ONLY_IDENTITY_UNVERIFIED")
        self.assertFalse(pairs[0]["settlement_compatible_for_rv"])
        self.assertFalse(pairs[0]["auto_identity_approval"])
        self.assertEqual(pairs[0]["next_required_step"], "LOAD_EXACT_CONTRACTS_AND_REVIEW_RULES")

    def test_combined_discovery_isolates_provider_failure(self):
        def broken_kalshi(_url):
            raise ConnectionError("kalshi unavailable")

        result = discover_market_candidates(
            "Fed September rate cut",
            kalshi_fetch_json=broken_kalshi,
            polymarket_fetch_json=polymarket_fixture_fetch,
        )
        self.assertEqual(result["providers"]["kalshi"]["status"], "PROVIDER_DISCOVERY_ERROR")
        self.assertEqual(result["providers"]["polymarket"]["status"], "OK")
        self.assertEqual(result["candidate_pairs"], [])
        self.assertFalse(result["candidate_match_is_settlement_proof"])
        self.assertEqual(result["identity_status"], "CANDIDATE_ONLY_IDENTITY_UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
