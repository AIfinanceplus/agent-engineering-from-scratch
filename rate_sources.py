"""Public, credential-free Treasury curve history adapter.

The active source is FRED's downloadable graph CSV for DGS2 and DGS10.  Tests
inject CSV-shaped transports, so CI exercises the production parser without
depending on network availability.
"""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from urllib.parse import urlencode

from native_http import http_get_text as native_http_get_text


FRED_GRAPH_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
RATE_SERIES = {
    "DGS2": "2-Year Treasury Constant Maturity Rate",
    "DGS10": "10-Year Treasury Constant Maturity Rate",
}


class RateSourceError(RuntimeError):
    """The public rate source could not provide a usable aligned history."""


class FredCurveHistorySource:
    def __init__(self, transport=None):
        self._transport = transport or _http_get_text

    def fetch(self, start_date: str | None = None) -> dict:
        start_date = start_date or (date.today() - timedelta(days=1_095)).isoformat()
        _iso_date(start_date, "start_date")
        series_rows = {}
        for series_id in RATE_SERIES:
            try:
                raw = self._transport(_series_url(series_id, start_date))
            except (ConnectionError, TimeoutError) as exc:
                raise ConnectionError(
                    f"FRED {series_id} connection failed: {exc}"
                ) from exc
            series_rows[series_id] = _parse_fred_csv(raw, series_id)
        common_dates = sorted(set(series_rows["DGS2"]) & set(series_rows["DGS10"]))
        observations = [
            {
                "date": period,
                "dgs2": series_rows["DGS2"][period],
                "dgs10": series_rows["DGS10"][period],
                "spread_bps": round(
                    (series_rows["DGS10"][period] - series_rows["DGS2"][period]) * 100,
                    6,
                ),
            }
            for period in common_dates
        ]
        if not observations:
            raise RateSourceError("DGS2 and DGS10 returned no common numeric observation dates")
        return {
            "artifact_type": "rate_curve_history",
            "provider": "FRED",
            "source_mode": "public_csv",
            "series": [
                {
                    "series_id": series_id,
                    "label": label,
                    "unit": "percent",
                    "source_url": f"https://fred.stlouisfed.org/series/{series_id}",
                }
                for series_id, label in RATE_SERIES.items()
            ],
            "start_date": start_date,
            "as_of": observations[-1]["date"],
            "observation_count": len(observations),
            "observations": observations,
            "guardrails": {
                "common_dates_only": True,
                "missing_values_dropped": True,
                "api_key_required": False,
                "values_fabricated": False,
            },
        }


def _series_url(series_id: str, start_date: str) -> str:
    return f"{FRED_GRAPH_CSV_URL}?{urlencode({'id': series_id, 'cosd': start_date})}"


def _parse_fred_csv(raw: str, series_id: str) -> dict[str, float]:
    if not isinstance(raw, str) or not raw.strip():
        raise RateSourceError(f"FRED {series_id} returned an empty CSV response")
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        raise RateSourceError(f"FRED {series_id} CSV has no header")
    date_field = "DATE" if "DATE" in reader.fieldnames else "observation_date"
    if date_field not in reader.fieldnames or series_id not in reader.fieldnames:
        raise RateSourceError(
            f"FRED {series_id} CSV must contain {date_field!r} and {series_id!r} columns"
        )
    points: dict[str, float] = {}
    for row in reader:
        period = (row.get(date_field) or "").strip()
        value = (row.get(series_id) or "").strip()
        if not period or value in {"", "."}:
            continue
        try:
            number = float(value)
            _iso_date(period, "observation date")
        except (TypeError, ValueError):
            continue
        points[period] = number
    if not points:
        raise RateSourceError(f"FRED {series_id} returned no numeric observations")
    return points


def _iso_date(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be YYYY-MM-DD") from exc
    return value


def _http_get_text(url: str) -> str:
    return native_http_get_text(
        url,
        accept="text/csv,text/plain;q=0.9,*/*;q=0.1",
    )
