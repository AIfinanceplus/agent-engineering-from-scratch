"""R1 real macro data source adapters.

The live path calls the U.S. Bureau of Labor Statistics Public Data API.
The fixture path uses the same normalized contract so CI and teaching runs stay
repeatable even when the network is unavailable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import Request, urlopen


BLS_V1_BASE_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data"

BLS_SERIES = {
    "headline_cpi": {
        "series_id": "CUSR0000SA0",
        "label": "CPI-U All Items, seasonally adjusted",
    },
    "core_cpi": {
        "series_id": "CUSR0000SA0L1E",
        "label": "CPI-U All Items Less Food and Energy, seasonally adjusted",
    },
}

# Teaching fixture only. Values are intentionally simple and are not presented
# as current BLS observations. The live adapter is the authoritative real-data path.
BLS_FIXTURE_ROWS = {
    "CUSR0000SA0": [
        {"year": "2024", "period": "M01", "periodName": "January", "value": "100.000", "footnotes": []},
        {"year": "2024", "period": "M02", "periodName": "February", "value": "100.200", "footnotes": []},
        {"year": "2025", "period": "M01", "periodName": "January", "value": "103.000", "footnotes": []},
        {"year": "2025", "period": "M02", "periodName": "February", "value": "103.200", "footnotes": []},
        {"year": "2026", "period": "M01", "periodName": "January", "value": "105.600", "footnotes": []},
        {"year": "2026", "period": "M02", "periodName": "February", "value": "105.900", "footnotes": []},
    ],
    "CUSR0000SA0L1E": [
        {"year": "2024", "period": "M01", "periodName": "January", "value": "100.000", "footnotes": []},
        {"year": "2024", "period": "M02", "periodName": "February", "value": "100.100", "footnotes": []},
        {"year": "2025", "period": "M01", "periodName": "January", "value": "103.300", "footnotes": []},
        {"year": "2025", "period": "M02", "periodName": "February", "value": "103.400", "footnotes": []},
        {"year": "2026", "period": "M01", "periodName": "January", "value": "106.500", "footnotes": []},
        {"year": "2026", "period": "M02", "periodName": "February", "value": "106.600", "footnotes": []},
    ],
}


@dataclass(frozen=True)
class BLSObservation:
    year: int
    month: int
    period: str
    period_name: str
    value: float
    footnotes: tuple[str, ...] = ()

    @property
    def period_key(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    def to_dict(self) -> dict:
        return {
            "year": self.year,
            "month": self.month,
            "period": self.period,
            "period_name": self.period_name,
            "period_key": self.period_key,
            "value": self.value,
            "footnotes": list(self.footnotes),
        }


class BLSAdapter:
    """Normalize BLS API responses into one stable evidence contract."""

    def __init__(self, transport=None):
        self._transport = transport or _http_get_json

    def fetch_series(self, series_id: str, label: str, mode: str = "fixture") -> dict:
        if mode not in {"fixture", "live"}:
            raise ValueError("mode must be 'fixture' or 'live'")
        if not isinstance(series_id, str) or not series_id:
            raise ValueError("series_id must be a non-empty string")
        if not isinstance(label, str) or not label:
            raise ValueError("label must be a non-empty string")

        if mode == "fixture":
            if series_id not in BLS_FIXTURE_ROWS:
                raise ValueError(f"No fixture for BLS series {series_id}")
            rows = BLS_FIXTURE_ROWS[series_id]
            source_uri = f"fixture://bls/{series_id}"
            title = f"{label} (teaching fixture)"
            publisher = "U.S. Bureau of Labor Statistics / teaching replay"
        else:
            source_uri = f"{BLS_V1_BASE_URL}/{series_id}"
            payload = self._transport(source_uri)
            rows = _extract_rows(payload, series_id)
            title = label
            publisher = "U.S. Bureau of Labor Statistics"

        observations = _normalize_rows(rows)
        if not observations:
            raise ValueError(f"BLS series {series_id} returned no monthly observations")
        latest = observations[-1]

        return {
            "kind": "evidence",
            "evidence_id": f"BLS:{series_id}",
            "claim": f"{label}: latest available index level is {latest.value} for {latest.period_key}.",
            "value": latest.value,
            "unit": "index_level",
            "confidence": 1.0,
            "series_id": series_id,
            "source_mode": mode,
            "history": [item.to_dict() for item in observations],
            "source": {
                "source_id": f"BLS:{series_id}",
                "title": title,
                "publisher": publisher,
                "uri": source_uri,
            },
            "note": (
                "Live BLS Public Data API observation."
                if mode == "live"
                else "Deterministic teaching fixture using the live adapter contract."
            ),
        }


def _http_get_json(url: str) -> dict:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "agent-engineering-from-scratch/1.0",
        },
    )
    try:
        with urlopen(request, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))
    except TimeoutError:
        raise
    except URLError as exc:
        raise ConnectionError(f"BLS request failed: {exc}") from exc


def _extract_rows(payload: dict, series_id: str) -> list[dict]:
    if not isinstance(payload, dict):
        raise ValueError("BLS response must be a JSON object")
    if payload.get("status") != "REQUEST_SUCCEEDED":
        messages = payload.get("message") or []
        raise ValueError(f"BLS request did not succeed: {messages}")

    series = ((payload.get("Results") or {}).get("series") or [])
    for item in series:
        if item.get("seriesID") == series_id:
            return list(item.get("data") or [])
    raise ValueError(f"BLS response missing requested series {series_id}")


def _normalize_rows(rows: list[dict]) -> list[BLSObservation]:
    observations = []
    for row in rows:
        period = str(row.get("period", ""))
        if len(period) != 3 or not period.startswith("M") or not period[1:].isdigit():
            continue
        month = int(period[1:])
        if not 1 <= month <= 12:
            continue
        footnotes = tuple(
            str(item.get("text"))
            for item in (row.get("footnotes") or [])
            if isinstance(item, dict) and item.get("text")
        )
        observations.append(
            BLSObservation(
                year=int(row["year"]),
                month=month,
                period=period,
                period_name=str(row.get("periodName") or period),
                value=float(row["value"]),
                footnotes=footnotes,
            )
        )
    observations.sort(key=lambda item: (item.year, item.month))
    return observations


DEFAULT_BLS_ADAPTER = BLSAdapter()


def fetch_bls_series(series_id: str, label: str, mode: str = "fixture") -> dict:
    return DEFAULT_BLS_ADAPTER.fetch_series(series_id, label, mode)
