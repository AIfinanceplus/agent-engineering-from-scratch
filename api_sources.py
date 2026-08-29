"""API-only macro source adapters for the active R2 workbench.

Production code has no fixture/live switch. The active path always calls public
APIs. Tests inject a transport that returns API-shaped JSON so parser behavior is
repeatable without adding a user-visible fixture mode.

Credentials stay Runtime-owned:
- BLS v1 single-series GET: no key required.
- FRED observations: FRED_API_KEY from environment.
- EIA v2 petroleum route: EIA_API_KEY from environment.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BLS_BASE_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data"
FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
EIA_GASOLINE_URL = "https://api.eia.gov/v2/petroleum/pri/gnd/data/"

API_SERIES = {
    "headline_cpi": {
        "provider": "BLS",
        "series_id": "CUSR0000SA0",
        "label": "CPI-U All Items, seasonally adjusted",
        "unit": "index_level",
    },
    "core_cpi": {
        "provider": "BLS",
        "series_id": "CUSR0000SA0L1E",
        "label": "CPI-U All Items Less Food and Energy, seasonally adjusted",
        "unit": "index_level",
    },
    "breakeven_5y": {
        "provider": "FRED",
        "series_id": "T5YIE",
        "label": "5-Year Breakeven Inflation Rate",
        "unit": "percent",
    },
    "regular_gasoline": {
        "provider": "EIA",
        "series_id": "EMM_EPMR_PTE_NUS_DPG",
        "label": "U.S. Regular All Formulations Retail Gasoline Prices",
        "unit": "dollars_per_gallon",
    },
}


class SourceAPIError(RuntimeError):
    def __init__(self, provider: str, message: str, *, status: int | None = None):
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.status = status


@dataclass(frozen=True)
class Point:
    period: str
    value: float

    def to_dict(self) -> dict:
        return {"period": self.period, "value": self.value}


class BLSPublicAPI:
    def __init__(self, transport=None):
        self._transport = transport or _http_get_json

    def fetch(self, series_id: str, label: str) -> dict:
        _require_text(series_id, "series_id")
        _require_text(label, "label")
        request_url = f"{BLS_BASE_URL}/{series_id}"
        payload = self._transport(request_url)
        rows = _bls_rows(payload, series_id)
        history = _normalize_bls(rows)
        if not history:
            raise SourceAPIError("BLS", f"series {series_id} returned no monthly observations")
        latest = history[-1]
        return {
            "kind": "evidence",
            "evidence_id": f"BLS:{series_id}",
            "claim": f"{label}: latest available index level is {latest['value']} for {latest['period_key']}.",
            "value": latest["value"],
            "unit": "index_level",
            "confidence": 1.0,
            "provider": "BLS",
            "series_id": series_id,
            "source_mode": "api",
            "as_of": latest["period_key"],
            "history": history,
            "source": {
                "source_id": f"BLS:{series_id}",
                "title": label,
                "publisher": "U.S. Bureau of Labor Statistics",
                "uri": request_url,
            },
            "note": "Live BLS Public Data API observation.",
        }


class FREDPublicAPI:
    def __init__(self, transport=None, env=None):
        self._transport = transport or _http_get_json
        self._env = os.environ if env is None else env

    def fetch(self, series_id: str, label: str, unit: str) -> dict:
        _require_text(series_id, "series_id")
        _require_text(label, "label")
        _require_text(unit, "unit")
        api_key = self._env.get("FRED_API_KEY")
        if not api_key:
            raise SourceAPIError("FRED", "FRED_API_KEY is not set")
        query = urlencode({
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 8,
        })
        payload = self._transport(f"{FRED_OBSERVATIONS_URL}?{query}")
        if not isinstance(payload, dict):
            raise SourceAPIError("FRED", "response is not a JSON object")
        if payload.get("error_code"):
            raise SourceAPIError("FRED", str(payload.get("error_message") or payload["error_code"]))
        history = _normalize_points(payload.get("observations") or [], period_key="date")
        return _point_evidence(
            provider="FRED",
            series_id=series_id,
            label=label,
            unit=unit,
            history=history,
            source_uri=f"https://fred.stlouisfed.org/series/{series_id}",
            publisher="Federal Reserve Bank of St. Louis",
        )


class EIAPublicAPI:
    def __init__(self, transport=None, env=None):
        self._transport = transport or _http_get_json
        self._env = os.environ if env is None else env

    def fetch(self, series_id: str, label: str, unit: str) -> dict:
        _require_text(series_id, "series_id")
        _require_text(label, "label")
        _require_text(unit, "unit")
        api_key = self._env.get("EIA_API_KEY")
        if not api_key:
            raise SourceAPIError("EIA", "EIA_API_KEY is not set")
        query = urlencode([
            ("api_key", api_key),
            ("frequency", "weekly"),
            ("data[0]", "value"),
            ("facets[series][]", series_id),
            ("sort[0][column]", "period"),
            ("sort[0][direction]", "desc"),
            ("length", "8"),
        ])
        payload = self._transport(f"{EIA_GASOLINE_URL}?{query}")
        if not isinstance(payload, dict):
            raise SourceAPIError("EIA", "response is not a JSON object")
        response = payload.get("response") or {}
        if response.get("error"):
            raise SourceAPIError("EIA", str(response["error"]))
        rows = response.get("data") or []
        history = _normalize_points(rows, period_key="period")
        return _point_evidence(
            provider="EIA",
            series_id=series_id,
            label=label,
            unit=unit,
            history=history,
            source_uri="https://www.eia.gov/opendata/browser/petroleum/pri/gnd",
            publisher="U.S. Energy Information Administration",
        )


def _point_evidence(*, provider, series_id, label, unit, history, source_uri, publisher) -> dict:
    if not history:
        raise SourceAPIError(provider, f"series {series_id} returned no observations")
    latest = history[-1]
    return {
        "kind": "evidence",
        "evidence_id": f"{provider}:{series_id}",
        "claim": f"{label}: latest available value is {latest.period} = {latest.value}.",
        "value": latest.value,
        "unit": unit,
        "confidence": 1.0,
        "provider": provider,
        "series_id": series_id,
        "source_mode": "api",
        "as_of": latest.period,
        "history": [point.to_dict() for point in history],
        "source": {
            "source_id": f"{provider}:{series_id}",
            "title": label,
            "publisher": publisher,
            "uri": source_uri,
        },
        "note": f"Live {provider} public API observation.",
    }


def _bls_rows(payload: dict, series_id: str) -> list[dict]:
    if not isinstance(payload, dict):
        raise SourceAPIError("BLS", "response is not a JSON object")
    if payload.get("status") != "REQUEST_SUCCEEDED":
        raise SourceAPIError("BLS", f"request failed: {payload.get('message') or []}")
    for item in ((payload.get("Results") or {}).get("series") or []):
        if item.get("seriesID") == series_id:
            return list(item.get("data") or [])
    raise SourceAPIError("BLS", f"response missing requested series {series_id}")


def _normalize_bls(rows: list[dict]) -> list[dict]:
    result = []
    for row in rows:
        period = str(row.get("period") or "")
        if len(period) != 3 or not period.startswith("M") or not period[1:].isdigit():
            continue
        month = int(period[1:])
        if not 1 <= month <= 12:
            continue
        try:
            year = int(row["year"])
            value = float(row["value"])
        except (KeyError, TypeError, ValueError):
            continue
        result.append({
            "year": year,
            "month": month,
            "period": period,
            "period_name": str(row.get("periodName") or period),
            "period_key": f"{year:04d}-{month:02d}",
            "value": value,
            "footnotes": [
                str(item.get("text"))
                for item in (row.get("footnotes") or [])
                if isinstance(item, dict) and item.get("text")
            ],
        })
    result.sort(key=lambda item: (item["year"], item["month"]))
    return result


def _normalize_points(rows: list[dict], *, period_key: str) -> list[Point]:
    points = []
    for row in rows:
        period = row.get(period_key)
        value = row.get("value")
        if not period or value in {None, "", "."}:
            continue
        try:
            points.append(Point(str(period), float(value)))
        except (TypeError, ValueError):
            continue
    points.sort(key=lambda item: item.period)
    return points


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _http_get_json(url: str) -> dict:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "agent-engineering-from-scratch/2.1"})
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise SourceAPIError("HTTP", f"HTTP {exc.code}: {body}", status=exc.code) from exc
    except TimeoutError:
        raise
    except URLError as exc:
        raise ConnectionError(f"public API request failed: {exc}") from exc


DEFAULT_BLS_API = BLSPublicAPI()
DEFAULT_FRED_API = FREDPublicAPI()
DEFAULT_EIA_API = EIAPublicAPI()


def fetch_bls_api_series(series_id: str, label: str) -> dict:
    return DEFAULT_BLS_API.fetch(series_id, label)


def fetch_fred_api_series(series_id: str, label: str, unit: str) -> dict:
    return DEFAULT_FRED_API.fetch(series_id, label, unit)


def fetch_eia_api_series(series_id: str, label: str, unit: str) -> dict:
    return DEFAULT_EIA_API.fetch(series_id, label, unit)
