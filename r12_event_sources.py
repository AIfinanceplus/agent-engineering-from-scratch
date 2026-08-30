"""R12 Step 2 public event-market adapters.

The adapters fetch one exact market identifier at a time and normalize provider
metadata into a common `r12_market_contract` artifact. They do NOT decide that two
markets are the same event. Event identity / settlement compatibility is a separate
validator boundary in r12_identity.py.

Public data sources used by this teaching adapter:
- Kalshi Trade API v2: exact market, event, series metadata.
- Polymarket Gamma: exact market metadata; CLOB books for executable top of book.

No trading credentials, wallet, order placement, or authenticated portfolio APIs
are used anywhere in this module.
"""

from __future__ import annotations

import json
from math import isfinite
from urllib.parse import quote, urlencode

from native_http import http_get_json


KALSHI_BASE = "https://external-api.kalshi.com/trade-api/v2"
POLYMARKET_GAMMA_BASE = "https://gamma-api.polymarket.com"
POLYMARKET_CLOB_BASE = "https://clob.polymarket.com"


def fetch_kalshi_market_contract(
    ticker: str,
    *,
    fetch_json=http_get_json,
    include_book: bool = True,
) -> dict:
    ticker = _required_text(ticker, "ticker")
    market_url = f"{KALSHI_BASE}/markets/{quote(ticker, safe='')}"
    market_payload = fetch_json(market_url)
    market = _required_object(market_payload.get("market"), "Kalshi market")

    event_ticker = _required_text(market.get("event_ticker"), "Kalshi event_ticker")
    event_url = f"{KALSHI_BASE}/events/{quote(event_ticker, safe='')}"
    event_payload = fetch_json(event_url)
    event = _required_object(event_payload.get("event"), "Kalshi event")

    series_ticker = event.get("series_ticker")
    series = {}
    series_url = None
    if isinstance(series_ticker, str) and series_ticker.strip():
        series_url = f"{KALSHI_BASE}/series/{quote(series_ticker.strip(), safe='')}"
        series_payload = fetch_json(series_url)
        series = _required_object(series_payload.get("series"), "Kalshi series")

    orderbook = {}
    orderbook_url = None
    if include_book:
        orderbook_url = f"{KALSHI_BASE}/markets/{quote(ticker, safe='')}/orderbook"
        orderbook = _required_object(fetch_json(orderbook_url), "Kalshi orderbook")

    return normalize_kalshi_contract(
        market,
        event=event,
        series=series,
        orderbook=orderbook,
        provenance_urls=[url for url in (market_url, event_url, series_url, orderbook_url) if url],
    )


def normalize_kalshi_contract(
    market: dict,
    *,
    event: dict | None = None,
    series: dict | None = None,
    orderbook: dict | None = None,
    provenance_urls: list[str] | None = None,
) -> dict:
    market = _required_object(market, "Kalshi market")
    event = event or {}
    series = series or {}
    ticker = _required_text(market.get("ticker"), "Kalshi market ticker")

    yes_bid = _optional_float(market.get("yes_bid_dollars"))
    yes_ask = _optional_float(market.get("yes_ask_dollars"))
    no_bid = _optional_float(market.get("no_bid_dollars"))
    no_ask = _optional_float(market.get("no_ask_dollars"))

    settlement_sources = []
    for row in series.get("settlement_sources") or []:
        if isinstance(row, dict):
            settlement_sources.append(
                {
                    "name": row.get("name"),
                    "url": row.get("url"),
                }
            )

    quote_complete = all(value is not None for value in (yes_bid, yes_ask, no_bid, no_ask))
    return {
        "artifact_type": "r12_market_contract",
        "provider": "kalshi",
        "provider_market_id": ticker,
        "provider_event_id": market.get("event_ticker"),
        "provider_series_id": event.get("series_ticker"),
        "question": market.get("title") or event.get("title"),
        "subtitle": market.get("subtitle") or market.get("yes_sub_title"),
        "description": event.get("sub_title") or event.get("title"),
        "outcomes": ["YES", "NO"],
        "resolution": {
            "rules_primary": market.get("rules_primary"),
            "rules_secondary": market.get("rules_secondary"),
            "settlement_sources": settlement_sources,
            "contract_url": series.get("contract_url"),
            "contract_terms_url": series.get("contract_terms_url"),
            "early_close_condition": market.get("early_close_condition"),
        },
        "time_contract": {
            "open_time": market.get("open_time"),
            "close_time": market.get("close_time"),
            "expected_expiration_time": market.get("expected_expiration_time"),
            "expiration_time": market.get("expiration_time") or market.get("latest_expiration_time"),
            "occurrence_datetime": market.get("occurrence_datetime"),
        },
        "measurement_contract": {
            "strike_type": market.get("strike_type"),
            "floor_strike": market.get("floor_strike"),
            "cap_strike": market.get("cap_strike"),
            "functional_strike": market.get("functional_strike"),
        },
        "quotes": {
            "yes_bid": yes_bid,
            "yes_ask": yes_ask,
            "no_bid": no_bid,
            "no_ask": no_ask,
            "last_price": _optional_float(market.get("last_price_dollars")),
            "quote_status": "EXECUTABLE_TOP_OF_BOOK_FIELDS" if quote_complete else "PARTIAL_TOP_OF_BOOK_FIELDS",
        },
        "orderbook": _normalize_kalshi_orderbook(orderbook),
        "market_status": market.get("status"),
        "liquidity": {
            "liquidity_dollars": _optional_float(market.get("liquidity_dollars")),
            "volume": _optional_float(market.get("volume_fp")),
            "volume_24h": _optional_float(market.get("volume_24h_fp")),
            "open_interest": _optional_float(market.get("open_interest_fp")),
        },
        "source_contract": {
            "public_market_data": True,
            "authentication_used": False,
            "provider_api": "Kalshi Trade API v2",
            "provenance_urls": list(provenance_urls or []),
        },
        "identity_status": "NOT_EVALUATED",
        "execution_status": "MARKET_DATA_ONLY_NO_ORDER_PLACEMENT",
    }


def fetch_polymarket_market_contract(
    market_id: str,
    *,
    fetch_json=http_get_json,
    include_books: bool = True,
) -> dict:
    market_id = _required_text(str(market_id), "market_id")
    market_url = f"{POLYMARKET_GAMMA_BASE}/markets/{quote(market_id, safe='')}"
    market = _required_object(fetch_json(market_url), "Polymarket market")

    outcomes = _json_list(market.get("outcomes"), "Polymarket outcomes")
    token_ids = _json_list(market.get("clobTokenIds"), "Polymarket clobTokenIds", allow_empty=True)
    books: dict[str, dict] = {}
    book_urls: list[str] = []
    if include_books and token_ids and len(token_ids) == len(outcomes):
        for outcome, token_id in zip(outcomes, token_ids):
            query = urlencode({"token_id": token_id})
            url = f"{POLYMARKET_CLOB_BASE}/book?{query}"
            books[str(outcome).upper()] = _required_object(fetch_json(url), f"Polymarket {outcome} book")
            book_urls.append(url)

    return normalize_polymarket_contract(
        market,
        books=books,
        provenance_urls=[market_url, *book_urls],
    )


def normalize_polymarket_contract(
    market: dict,
    *,
    books: dict[str, dict] | None = None,
    provenance_urls: list[str] | None = None,
) -> dict:
    market = _required_object(market, "Polymarket market")
    market_id = _required_text(str(market.get("id")), "Polymarket market id")
    outcomes = [str(value).upper() for value in _json_list(market.get("outcomes"), "Polymarket outcomes")]
    prices = _json_list(market.get("outcomePrices"), "Polymarket outcomePrices", allow_empty=True)
    token_ids = _json_list(market.get("clobTokenIds"), "Polymarket clobTokenIds", allow_empty=True)
    books = books or {}

    outcome_prices = {}
    if prices and len(prices) == len(outcomes):
        for outcome, price in zip(outcomes, prices):
            outcome_prices[outcome] = _optional_float(price)

    tokens = {}
    if token_ids and len(token_ids) == len(outcomes):
        tokens = {outcome: str(token_id) for outcome, token_id in zip(outcomes, token_ids)}

    yes_book = books.get("YES") or {}
    no_book = books.get("NO") or {}
    yes_bid, yes_ask = _best_book_prices(yes_book)
    no_bid, no_ask = _best_book_prices(no_book)
    complete_book = all(value is not None for value in (yes_bid, yes_ask, no_bid, no_ask))

    resolution_source = market.get("resolutionSource")
    event_resolution_sources = []
    for event in market.get("events") or []:
        if isinstance(event, dict) and event.get("resolutionSource"):
            event_resolution_sources.append(event.get("resolutionSource"))

    return {
        "artifact_type": "r12_market_contract",
        "provider": "polymarket",
        "provider_market_id": market_id,
        "provider_event_id": market.get("conditionId"),
        "provider_series_id": None,
        "question": market.get("question"),
        "subtitle": market.get("slug"),
        "description": market.get("description"),
        "outcomes": outcomes,
        "resolution": {
            "resolution_source": resolution_source,
            "event_resolution_sources": event_resolution_sources,
            "description": market.get("description"),
        },
        "time_contract": {
            "start_time": market.get("startDate"),
            "end_time": market.get("endDate"),
            "closed_time": market.get("closedTime"),
        },
        "measurement_contract": {
            "x_axis_value": market.get("xAxisValue"),
            "y_axis_value": market.get("yAxisValue"),
        },
        "quotes": {
            "yes_bid": yes_bid,
            "yes_ask": yes_ask,
            "no_bid": no_bid,
            "no_ask": no_ask,
            "indicative_outcome_prices": outcome_prices,
            "quote_status": "EXECUTABLE_CLOB_TOP_OF_BOOK" if complete_book else "INDICATIVE_OR_PARTIAL_QUOTES",
        },
        "orderbook": _normalize_polymarket_orderbook(books, tokens),
        "token_ids": tokens,
        "market_status": "closed" if market.get("closed") else "active" if market.get("active") else "unknown",
        "liquidity": {
            "liquidity": _optional_float(market.get("liquidity")),
            "volume": _optional_float(market.get("volume")),
            "volume_24h": _optional_float(market.get("volume24hr")),
        },
        "source_contract": {
            "public_market_data": True,
            "authentication_used": False,
            "provider_api": "Polymarket Gamma + CLOB public market data",
            "provenance_urls": list(provenance_urls or []),
        },
        "identity_status": "NOT_EVALUATED",
        "execution_status": "MARKET_DATA_ONLY_NO_ORDER_PLACEMENT",
    }


def _best_book_prices(book: dict) -> tuple[float | None, float | None]:
    bids = []
    asks = []
    for row in book.get("bids") or []:
        if isinstance(row, dict):
            price = _optional_float(row.get("price"))
        elif isinstance(row, (list, tuple)) and row:
            price = _optional_float(row[0])
        else:
            price = None
        if price is not None:
            bids.append(price)
    for row in book.get("asks") or []:
        if isinstance(row, dict):
            price = _optional_float(row.get("price"))
        elif isinstance(row, (list, tuple)) and row:
            price = _optional_float(row[0])
        else:
            price = None
        if price is not None:
            asks.append(price)
    return (max(bids) if bids else None, min(asks) if asks else None)


def _normalize_kalshi_orderbook(payload: dict | None) -> dict:
    """Expose full YES/NO books, deriving asks from opposite-side bids.

    Kalshi's public REST book contains YES and NO bids only. A NO bid at p is
    executable as a YES ask at 1-p, and vice versa. Sizes are preserved.
    """
    payload = payload if isinstance(payload, dict) else {}
    raw = payload.get("orderbook_fp")
    if not isinstance(raw, dict):
        raw = payload.get("orderbook")
    if not isinstance(raw, dict):
        raw = {}

    yes_bids = _normalize_book_levels(
        raw.get("yes_dollars") or raw.get("yes"),
        cents=bool(raw.get("yes") and not raw.get("yes_dollars")),
    )
    no_bids = _normalize_book_levels(
        raw.get("no_dollars") or raw.get("no"),
        cents=bool(raw.get("no") and not raw.get("no_dollars")),
    )
    yes_asks = _complement_levels(no_bids)
    no_asks = _complement_levels(yes_bids)
    available = bool(yes_bids or no_bids)
    return {
        "snapshot_status": "PUBLIC_DEPTH_AVAILABLE" if available else "ORDERBOOK_DEPTH_UNAVAILABLE",
        "source_format": "KALSHI_BIDS_WITH_DERIVED_COMPLEMENT_ASKS",
        "YES": {"bids": yes_bids, "asks": yes_asks},
        "NO": {"bids": no_bids, "asks": no_asks},
    }


def _normalize_polymarket_orderbook(books: dict, token_ids: dict[str, str]) -> dict:
    outcomes = {}
    for outcome in ("YES", "NO"):
        book = books.get(outcome) if isinstance(books, dict) else None
        book = book if isinstance(book, dict) else {}
        outcomes[outcome] = {
            "token_id": token_ids.get(outcome),
            "snapshot_timestamp": book.get("timestamp"),
            "snapshot_hash": book.get("hash"),
            "bids": _normalize_book_levels(book.get("bids")),
            "asks": _normalize_book_levels(book.get("asks")),
            "min_order_size": _optional_float(book.get("min_order_size")),
            "tick_size": _optional_float(book.get("tick_size")),
        }
    available = any(outcomes[outcome][side] for outcome in outcomes for side in ("bids", "asks"))
    return {
        "snapshot_status": "PUBLIC_DEPTH_AVAILABLE" if available else "ORDERBOOK_DEPTH_UNAVAILABLE",
        "source_format": "POLYMARKET_CLOB_OUTCOME_BOOKS",
        **outcomes,
    }


def _normalize_book_levels(levels, *, cents: bool = False) -> list[dict]:
    normalized = []
    for row in levels or []:
        if isinstance(row, dict):
            price = _optional_float(row.get("price"))
            size = _optional_float(row.get("size"))
        elif isinstance(row, (list, tuple)) and len(row) >= 2:
            price = _optional_float(row[0])
            size = _optional_float(row[1])
        else:
            continue
        if price is None or size is None:
            continue
        if cents:
            price /= 100.0
        if not 0 <= price <= 1 or size <= 0:
            continue
        normalized.append({"price": round(price, 8), "size": round(size, 8)})
    normalized.sort(key=lambda level: level["price"])
    return normalized


def _complement_levels(bids: list[dict]) -> list[dict]:
    asks = [
        {"price": round(1.0 - float(level["price"]), 8), "size": level["size"]}
        for level in bids
    ]
    asks.sort(key=lambda level: level["price"])
    return asks


def _json_list(value, label: str, *, allow_empty: bool = False) -> list:
    if value is None and allow_empty:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label} must be a JSON list string") from exc
    if not isinstance(value, list):
        if allow_empty:
            return []
        raise ValueError(f"{label} must be a list")
    if not value and not allow_empty:
        raise ValueError(f"{label} must not be empty")
    return value


def _required_object(value, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _required_text(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value.strip()


def _optional_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None
