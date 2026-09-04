"""R12 Step 3 market discovery and candidate matching.

Discovery helps a human find plausible Kalshi / Polymarket contracts without knowing
provider IDs in advance. It is deliberately upstream of the existing settlement
identity validator:

    free-text query -> provider discovery -> lexical candidate pairs
    -> explicit contract load -> settlement/rules review -> verified RV

A candidate match is NEVER evidence that two markets settle identically.

Provider contracts:
- Kalshi has public paginated event listing but no general free-text market search
  endpoint in the public Trade API contract used here. We therefore fetch a bounded
  number of OPEN events, rank them locally, and expand only the top events.
- Polymarket exposes the public Gamma `public-search` endpoint. Search results are
  event-level, so the adapter expands a bounded number of matching events to their
  individual markets.

No trading credentials or order APIs are used.
"""

from __future__ import annotations

import re
from hashlib import sha256
from urllib.parse import quote, urlencode

from native_http import http_get_json
from r12_event_sources import KALSHI_BASE, POLYMARKET_GAMMA_BASE


_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
    "is", "it", "of", "on", "or", "the", "to", "will", "with",
}


def discover_market_candidates(
    query: str,
    *,
    kalshi_fetch_json=http_get_json,
    polymarket_fetch_json=http_get_json,
    result_limit: int = 10,
) -> dict:
    """Discover both providers independently and build non-authoritative pairs.

    Provider failures are isolated so one unavailable venue does not erase useful
    candidates from the other venue. Application-level provider errors are returned
    as structured status fields rather than being mistaken for settlement evidence.
    """
    query = _required_query(query)
    result_limit = _bounded_limit(result_limit)

    providers = {}
    try:
        providers["kalshi"] = discover_kalshi_candidates(
            query,
            fetch_json=kalshi_fetch_json,
            result_limit=result_limit,
        )
    except Exception as exc:  # provider isolation is part of the artifact contract
        providers["kalshi"] = _provider_error("kalshi", query, exc)

    try:
        providers["polymarket"] = discover_polymarket_candidates(
            query,
            fetch_json=polymarket_fetch_json,
            result_limit=result_limit,
        )
    except Exception as exc:
        providers["polymarket"] = _provider_error("polymarket", query, exc)

    pairs = build_candidate_pairs(
        providers["kalshi"].get("candidates") or [],
        providers["polymarket"].get("candidates") or [],
        pair_limit=result_limit,
    )
    return {
        "artifact_type": "r12_market_discovery",
        "query": query,
        "providers": providers,
        "candidate_pairs": pairs,
        "pair_count": len(pairs),
        "identity_status": "CANDIDATE_ONLY_IDENTITY_UNVERIFIED",
        "candidate_match_is_settlement_proof": False,
        "next_required_step": "LOAD_EXACT_CONTRACTS_AND_RUN_SETTLEMENT_IDENTITY_VALIDATOR",
        "execution_status": "DISCOVERY_ONLY_NO_ORDER_PLACEMENT",
    }


def discover_kalshi_candidates(
    query: str,
    *,
    fetch_json=http_get_json,
    max_pages: int = 2,
    page_size: int = 200,
    event_expand_limit: int = 8,
    result_limit: int = 10,
) -> dict:
    """Bounded Kalshi discovery: OPEN event pages -> local rank -> top event expansion."""
    query = _required_query(query)
    result_limit = _bounded_limit(result_limit)
    query_tokens = _tokens(query)
    cursor = None
    event_rows = []
    provenance_urls = []
    pages_fetched = 0
    remaining_cursor = None

    for _ in range(max(1, int(max_pages))):
        params = {"status": "open", "limit": max(1, min(int(page_size), 200))}
        if cursor:
            params["cursor"] = cursor
        url = f"{KALSHI_BASE}/events?{urlencode(params)}"
        payload = _required_object(fetch_json(url), "Kalshi events response")
        provenance_urls.append(url)
        pages_fetched += 1
        for event in payload.get("events") or []:
            if not isinstance(event, dict):
                continue
            text = " ".join(
                str(value or "")
                for value in (event.get("title"), event.get("sub_title"), event.get("event_ticker"))
            )
            score = _query_score(query_tokens, query, text)
            if score > 0:
                event_rows.append((score, event))
        cursor = payload.get("cursor")
        remaining_cursor = cursor if isinstance(cursor, str) and cursor else None
        if not remaining_cursor:
            break

    event_rows.sort(key=lambda row: (-row[0], str(row[1].get("event_ticker") or "")))
    expanded = event_rows[: max(1, int(event_expand_limit))]
    candidates = []

    for event_score, event_summary in expanded:
        event_ticker = _required_text(event_summary.get("event_ticker"), "Kalshi event ticker")
        event_url = f"{KALSHI_BASE}/events/{quote(event_ticker, safe='')}"
        payload = _required_object(fetch_json(event_url), "Kalshi event detail response")
        provenance_urls.append(event_url)
        event = payload.get("event") if isinstance(payload.get("event"), dict) else event_summary
        markets = payload.get("markets")
        if not isinstance(markets, list):
            markets = event.get("markets") if isinstance(event, dict) else []
        if not isinstance(markets, list):
            markets = []

        for market in markets:
            if not isinstance(market, dict):
                continue
            ticker = market.get("ticker")
            if not isinstance(ticker, str) or not ticker.strip():
                continue
            text = " ".join(
                str(value or "")
                for value in (
                    event.get("title") if isinstance(event, dict) else None,
                    event.get("sub_title") if isinstance(event, dict) else None,
                    market.get("title"),
                    market.get("subtitle"),
                    market.get("yes_sub_title"),
                    market.get("no_sub_title"),
                    ticker,
                )
            )
            market_score = _query_score(query_tokens, query, text)
            score = max(event_score * 0.7 + market_score * 0.3, market_score)
            candidates.append(
                _candidate(
                    provider="kalshi",
                    identifier=ticker.strip(),
                    event_id=event_ticker,
                    event_title=event.get("title") if isinstance(event, dict) else event_summary.get("title"),
                    market_title=market.get("title") or market.get("yes_sub_title") or ticker,
                    subtitle=market.get("subtitle") or market.get("yes_sub_title"),
                    close_time=market.get("close_time") or market.get("expiration_time"),
                    market_status=market.get("status"),
                    score=score,
                    search_mode="BOUNDED_OPEN_EVENTS_LOCAL_TEXT_RANKING",
                )
            )

    candidates = _dedupe_candidates(candidates)[:result_limit]
    return {
        "provider": "kalshi",
        "status": "OK",
        "query": query,
        "search_mode": "BOUNDED_OPEN_EVENTS_LOCAL_TEXT_RANKING",
        "official_free_text_search_used": False,
        "pages_fetched": pages_fetched,
        "events_with_token_overlap": len(event_rows),
        "events_expanded": len(expanded),
        "coverage_status": "BOUNDED_PARTIAL_DISCOVERY" if remaining_cursor else "OPEN_EVENT_LIST_EXHAUSTED_WITHIN_BOUND",
        "remaining_cursor_present": bool(remaining_cursor),
        "candidates": candidates,
        "provenance_urls": provenance_urls,
    }


def discover_polymarket_candidates(
    query: str,
    *,
    fetch_json=http_get_json,
    event_expand_limit: int = 8,
    result_limit: int = 10,
) -> dict:
    """Polymarket discovery using public-search, then bounded event expansion."""
    query = _required_query(query)
    result_limit = _bounded_limit(result_limit)
    query_tokens = _tokens(query)
    search_url = f"{POLYMARKET_GAMMA_BASE}/public-search?{urlencode({'q': query})}"
    search_payload = _required_object(fetch_json(search_url), "Polymarket search response")
    events = [row for row in (search_payload.get("events") or []) if isinstance(row, dict)]
    provenance_urls = [search_url]
    candidates = []

    for event_summary in events[: max(1, int(event_expand_limit))]:
        event_id = event_summary.get("id")
        if event_id is None or str(event_id).strip() == "":
            continue
        event_url = f"{POLYMARKET_GAMMA_BASE}/events/{quote(str(event_id), safe='')}"
        event = _required_object(fetch_json(event_url), "Polymarket event detail")
        provenance_urls.append(event_url)
        event_title = event.get("title") or event_summary.get("title")
        for market in event.get("markets") or []:
            if not isinstance(market, dict):
                continue
            market_id = market.get("id")
            if market_id is None or str(market_id).strip() == "":
                continue
            text = " ".join(
                str(value or "")
                for value in (
                    event_title,
                    event.get("slug"),
                    market.get("question"),
                    market.get("slug"),
                    market_id,
                )
            )
            score = _query_score(query_tokens, query, text)
            if score <= 0:
                continue
            candidates.append(
                _candidate(
                    provider="polymarket",
                    identifier=str(market_id),
                    event_id=str(event.get("id") or event_id),
                    event_title=event_title,
                    market_title=market.get("question") or market.get("slug") or str(market_id),
                    subtitle=market.get("slug"),
                    close_time=market.get("endDate") or event.get("endDate"),
                    market_status="closed" if market.get("closed") else "active" if market.get("active", True) else "unknown",
                    score=score,
                    search_mode="POLYMARKET_PUBLIC_SEARCH_EVENT_EXPANSION",
                )
            )

    candidates = _dedupe_candidates(candidates)[:result_limit]
    pagination = search_payload.get("pagination") if isinstance(search_payload.get("pagination"), dict) else {}
    return {
        "provider": "polymarket",
        "status": "OK",
        "query": query,
        "search_mode": "POLYMARKET_PUBLIC_SEARCH_EVENT_EXPANSION",
        "official_free_text_search_used": True,
        "events_returned": len(events),
        "events_expanded": min(len(events), max(1, int(event_expand_limit))),
        "coverage_status": "SEARCH_RESULTS_HAVE_MORE" if pagination.get("hasMore") else "SEARCH_PAGE_RETURNED",
        "search_total_results": pagination.get("totalResults"),
        "candidates": candidates,
        "provenance_urls": provenance_urls,
    }


def build_candidate_pairs(kalshi_candidates: list[dict], polymarket_candidates: list[dict], *, pair_limit: int = 10) -> list[dict]:
    """Rank plausible cross-provider pairs WITHOUT approving event identity."""
    pairs = []
    for kalshi in kalshi_candidates:
        for poly in polymarket_candidates:
            k_text = _candidate_text(kalshi)
            p_text = _candidate_text(poly)
            similarity = _text_similarity(k_text, p_text)
            if similarity <= 0:
                continue
            k_score = _safe_score(kalshi.get("query_match_score"))
            p_score = _safe_score(poly.get("query_match_score"))
            pair_score = round(similarity * 0.6 + k_score * 0.2 + p_score * 0.2, 4)
            seed = f"{kalshi.get('identifier')}|{poly.get('identifier')}"
            pairs.append(
                {
                    "pair_id": "PAIR-" + sha256(seed.encode("utf-8")).hexdigest()[:12].upper(),
                    "kalshi_identifier": kalshi.get("identifier"),
                    "polymarket_identifier": poly.get("identifier"),
                    "kalshi_title": kalshi.get("market_title"),
                    "polymarket_title": poly.get("market_title"),
                    "lexical_similarity": round(similarity, 4),
                    "pair_score": pair_score,
                    "status": "CANDIDATE_ONLY_IDENTITY_UNVERIFIED",
                    "settlement_compatible_for_rv": False,
                    "auto_identity_approval": False,
                    "next_required_step": "LOAD_EXACT_CONTRACTS_AND_REVIEW_RULES",
                }
            )
    pairs.sort(key=lambda row: (-row["pair_score"], str(row["pair_id"])))
    return pairs[: _bounded_limit(pair_limit)]


def _candidate(
    *,
    provider: str,
    identifier: str,
    event_id: str,
    event_title,
    market_title,
    subtitle,
    close_time,
    market_status,
    score: float,
    search_mode: str,
) -> dict:
    return {
        "provider": provider,
        "identifier": identifier,
        "event_id": event_id,
        "event_title": event_title,
        "market_title": market_title,
        "subtitle": subtitle,
        "close_time": close_time,
        "market_status": market_status,
        "query_match_score": round(max(0.0, min(float(score), 1.0)), 4),
        "match_score_type": "LEXICAL_DISCOVERY_HEURISTIC_NOT_PROBABILITY",
        "search_mode": search_mode,
        "status": "CANDIDATE_ONLY_IDENTITY_UNVERIFIED",
        "settlement_compatible_for_rv": False,
    }


def _query_score(query_tokens: set[str], raw_query: str, text: str) -> float:
    text_tokens = _tokens(text)
    if not query_tokens or not text_tokens:
        return 0.0
    overlap = query_tokens & text_tokens
    if not overlap:
        return 0.0
    coverage = len(overlap) / len(query_tokens)
    precision = len(overlap) / len(text_tokens)
    phrase = 1.0 if _normalize_phrase(raw_query) in _normalize_phrase(text) else 0.0
    return round(min(1.0, 0.72 * coverage + 0.18 * min(1.0, precision * 4) + 0.10 * phrase), 4)


def _text_similarity(left: str, right: str) -> float:
    a = _tokens(left)
    b = _tokens(right)
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


def _candidate_text(row: dict) -> str:
    return " ".join(str(row.get(key) or "") for key in ("event_title", "market_title", "subtitle"))


def _tokens(value: str) -> set[str]:
    return {token for token in _TOKEN_RE.findall(str(value).lower()) if token not in _STOPWORDS and len(token) > 1}


def _normalize_phrase(value: str) -> str:
    return " ".join(_TOKEN_RE.findall(str(value).lower()))


def _dedupe_candidates(rows: list[dict]) -> list[dict]:
    best = {}
    for row in rows:
        key = (row.get("provider"), row.get("identifier"))
        current = best.get(key)
        if current is None or _safe_score(row.get("query_match_score")) > _safe_score(current.get("query_match_score")):
            best[key] = row
    result = list(best.values())
    result.sort(key=lambda row: (-_safe_score(row.get("query_match_score")), str(row.get("identifier") or "")))
    return result


def _provider_error(provider: str, query: str, exc: Exception) -> dict:
    return {
        "provider": provider,
        "status": "PROVIDER_DISCOVERY_ERROR",
        "query": query,
        "candidates": [],
        "error": {"code": exc.__class__.__name__, "message": str(exc)},
        "identity_status": "NOT_EVALUATED",
    }


def _required_query(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("discovery query is required")
    return value.strip()


def _required_text(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value.strip()


def _required_object(value, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _bounded_limit(value) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("result_limit must be an integer") from exc
    if number < 1 or number > 25:
        raise ValueError("result_limit must be between 1 and 25")
    return number


def _safe_score(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
