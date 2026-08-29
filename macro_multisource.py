"""R2 multi-source macro adapters for FRED + EIA.

Live mode keeps credentials in Runtime-owned environment variables; API keys are
never Tool arguments and therefore never become Model-controlled input or trace
payload. Fixture mode uses the same normalized evidence contract for CI.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
EIA_SERIES_BASE_URL = "https://api.eia.gov/v2/seriesid"

FRED_SERIES = {
    "breakeven_5y": {
        "series_id": "T5YIE",
        "label": "5-Year Breakeven Inflation Rate",
        "unit": "percent",
    },
}

EIA_SERIES = {
    "regular_gasoline": {
        "series_id": "PET.EMM_EPMR_PTE_NUS_DPG.W",
        "label": "U.S. Regular All Formulations Retail Gasoline Prices",
        "unit": "dollars_per_gallon",
    },
}

# Teaching fixtures only. They are intentionally stable, not current market data.
FRED_FIXTURE = {
    "T5YIE": [
        {"date": "2026-02-20", "value": "2.30"},
        {"date": "2026-02-27", "value": "2.34"},
        {"date": "2026-03-06", "value": "2.28"},
        {"date": "2026-03-13", "value": "2.25"},
    ],
}

EIA_FIXTURE = {
    "PET.EMM_EPMR_PTE_NUS_DPG.W": [
        {"period": "2026-02-23", "value": "3.05", "units": "$/GAL"},
        {"period": "2026-03-02", "value": "3.12", "units": "$/GAL"},
        {"period": "2026-03-09", "value": "3.18", "units": "$/GAL"},
        {"period": "2026-03-16", "value": "3.22", "units": "$/GAL"},
    ],
}


@dataclass(frozen=True)
class Point:
    period: str
    value: float

    def to_dict(self) -> dict:
        return {"period": self.period, "value": self.value}


class FREDAdapter:
    def __init__(self, transport=None, env=None):
        self._transport = transport or _http_get_json
        self._env = os.environ if env is None else env

    def fetch_series(self, series_id: str, label: str, unit: str, mode: str = "fixture") -> dict:
        _validate_mode(mode)
        if mode == "fixture":
            rows = FRED_FIXTURE.get(series_id)
            if rows is None:
                raise ValueError(f"No fixture for FRED series {series_id}")
            source_uri = f"fixture://fred/{series_id}"
            publisher = "Federal Reserve Bank of St. Louis / teaching replay"
        else:
            api_key = self._env.get("FRED_API_KEY")
            if not api_key:
                raise RuntimeError("FRED_API_KEY is required for live FRED mode")
            query = urlencode({
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "asc",
            })
            request_url = f"{FRED_BASE_URL}?{query}"
            payload = self._transport(request_url)
            rows = payload.get("observations") or []
            # Never persist the credential-bearing request URL.
            source_uri = f"https://fred.stlouisfed.org/series/{series_id}"
            publisher = "Federal Reserve Bank of St. Louis"

        history = _normalize_fred_rows(rows)
        if not history:
            raise ValueError(f"FRED series {series_id} returned no observations")
        latest = history[-1]
        return _evidence(
            evidence_id=f"FRED:{series_id}",
            claim=f"{label}: latest available value is {latest.value} for {latest.period}.",
            value=latest.value,
            unit=unit,
            series_id=series_id,
            source_mode=mode,
            history=history,
            source={
                "source_id": f"FRED:{series_id}",
                "title": label + (" (teaching fixture)" if mode == "fixture" else ""),
                "publisher": publisher,
                "uri": source_uri,
            },
        )


class EIAAdapter:
    def __init__(self, transport=None, env=None):
        self._transport = transport or _http_get_json
        self._env = os.environ if env is None else env

    def fetch_series(self, series_id: str, label: str, unit: str, mode: str = "fixture") -> dict:
        _validate_mode(mode)
        if mode == "fixture":
            rows = EIA_FIXTURE.get(series_id)
            if rows is None:
                raise ValueError(f"No fixture for EIA series {series_id}")
            source_uri = f"fixture://eia/{series_id}"
            publisher = "U.S. Energy Information Administration / teaching replay"
        else:
            api_key = self._env.get("EIA_API_KEY")
            if not api_key:
                raise RuntimeError("EIA_API_KEY is required for live EIA mode")
            request_url = f"{EIA_SERIES_BASE_URL}/{series_id}?{urlencode({'api_key': api_key})}"
            payload = self._transport(request_url)
            rows = ((payload.get("response") or {}).get("data") or [])
            source_uri = "https://www.eia.gov/opendata/browser/petroleum/pri/gnd"
            publisher = "U.S. Energy Information Administration"

        history = _normalize_eia_rows(rows)
        if not history:
            raise ValueError(f"EIA series {series_id} returned no observations")
        latest = history[-1]
        return _evidence(
            evidence_id=f"EIA:{series_id}",
            claim=f"{label}: latest available value is {latest.value} for {latest.period}.",
            value=latest.value,
            unit=unit,
            series_id=series_id,
            source_mode=mode,
            history=history,
            source={
                "source_id": f"EIA:{series_id}",
                "title": label + (" (teaching fixture)" if mode == "fixture" else ""),
                "publisher": publisher,
                "uri": source_uri,
            },
        )


def _evidence(*, evidence_id, claim, value, unit, series_id, source_mode, history, source) -> dict:
    latest_period = history[-1].period
    return {
        "kind": "evidence",
        "evidence_id": evidence_id,
        "claim": claim,
        "value": value,
        "unit": unit,
        "confidence": 1.0,
        "series_id": series_id,
        "source_mode": source_mode,
        "as_of": latest_period,
        "history": [point.to_dict() for point in history],
        "source": source,
    }


def _normalize_fred_rows(rows: list[dict]) -> list[Point]:
    result = []
    for row in rows:
        value = row.get("value")
        if value in {None, ".", ""}:
            continue
        try:
            result.append(Point(period=str(row["date"]), value=float(value)))
        except (KeyError, TypeError, ValueError):
            continue
    result.sort(key=lambda item: item.period)
    return result


def _normalize_eia_rows(rows: list[dict]) -> list[Point]:
    result = []
    for row in rows:
        value = row.get("value")
        period = row.get("period")
        if value in {None, ".", ""} or not period:
            continue
        try:
            result.append(Point(period=str(period), value=float(value)))
        except (TypeError, ValueError):
            continue
    result.sort(key=lambda item: item.period)
    return result


def _validate_mode(mode: str) -> None:
    if mode not in {"fixture", "live"}:
        raise ValueError("mode must be 'fixture' or 'live'")


def _http_get_json(url: str) -> dict:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "agent-engineering-from-scratch/2.0"})
    try:
        with urlopen(request, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))
    except TimeoutError:
        raise
    except URLError as exc:
        raise ConnectionError(f"macro source request failed: {exc}") from exc


DEFAULT_FRED_ADAPTER = FREDAdapter()
DEFAULT_EIA_ADAPTER = EIAAdapter()


def fetch_fred_series(series_id: str, label: str, unit: str, mode: str = "fixture") -> dict:
    return DEFAULT_FRED_ADAPTER.fetch_series(series_id, label, unit, mode)


def fetch_eia_series(series_id: str, label: str, unit: str, mode: str = "fixture") -> dict:
    return DEFAULT_EIA_ADAPTER.fetch_series(series_id, label, unit, mode)
