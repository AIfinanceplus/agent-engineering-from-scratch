"""Resilient public Treasury curve history adapter.

Source ladder: one bulk FRED request, official U.S. Treasury CSV, then a dated
bundled Treasury snapshot for the offline teaching run. Every artifact states
which source won and whether it is live or a snapshot.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

from native_http import http_get_text as native_http_get_text
from rate_control import check_run_control


FRED_GRAPH_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
TREASURY_CSV_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all"
)
TREASURY_SERIES_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "TextView?type=daily_treasury_yield_curve"
)
SNAPSHOT_PATH = Path(__file__).with_name("data") / "rate_curve_snapshot.csv"
SNAPSHOT_CAPTURED_AT = "2026-09-01"
TREASURY_MIN_OBSERVATIONS = 260

RATE_SERIES = {
    "DGS2": "2-Year Treasury Constant Maturity Rate",
    "DGS10": "10-Year Treasury Constant Maturity Rate",
}


class RateSourceError(RuntimeError):
    """No public source could provide a usable aligned history."""


def load_bundled_rate_history(start_date: str) -> dict:
    """Explicit offline lesson mode; never pretend a snapshot is a live fetch."""
    check_run_control()
    _iso_date(start_date, "start_date")
    rows = _parse_snapshot_csv(SNAPSHOT_PATH.read_text(encoding="utf-8"), start_date)
    return _artifact(
        rows, start_date=start_date, provider="U.S. Treasury",
        source_mode="bundled_snapshot", source_attempts=[
            _source_attempt("U.S. Treasury", "bundled_snapshot", "SELECTED")
        ], fallback_used=False, snapshot_captured_at=SNAPSHOT_CAPTURED_AT,
    )


class FredCurveHistorySource:
    """Backward-compatible name for the new multi-source curve adapter."""

    def __init__(self, transport=None, *, snapshot_path=None, today=None):
        self._transport = transport or _http_get_text
        self._snapshot_path = Path(snapshot_path) if snapshot_path else SNAPSHOT_PATH
        self._today = today or date.today

    def fetch(self, start_date: str | None = None) -> dict:
        start_date = start_date or (self._today() - timedelta(days=1_095)).isoformat()
        _iso_date(start_date, "start_date")
        attempts = []

        try:
            check_run_control()
            raw = self._transport(_fred_bulk_url(start_date))
            check_run_control()
            rows = _parse_fred_curve_csv(raw, start_date)
            attempts.append(_source_attempt("FRED", "live_bulk_csv", "SELECTED"))
            return _artifact(rows, start_date=start_date, provider="FRED",
                             source_mode="live_bulk_csv", source_attempts=attempts,
                             fallback_used=False)
        except (ConnectionError, TimeoutError, RuntimeError) as exc:
            attempts.append(_source_attempt("FRED", "live_bulk_csv", "FAILED", exc))

        try:
            check_run_control()
            rows = self._fetch_treasury(start_date)
            attempts.append(_source_attempt("U.S. Treasury", "live_official_csv", "SELECTED"))
            return _artifact(rows, start_date=start_date, provider="U.S. Treasury",
                             source_mode="live_official_csv", source_attempts=attempts,
                             fallback_used=True)
        except (ConnectionError, TimeoutError, RuntimeError) as exc:
            attempts.append(_source_attempt("U.S. Treasury", "live_official_csv", "FAILED", exc))

        try:
            check_run_control()
            raw = self._snapshot_path.read_text(encoding="utf-8")
            rows = _parse_snapshot_csv(raw, start_date)
            attempts.append(_source_attempt("U.S. Treasury", "bundled_snapshot", "SELECTED"))
            return _artifact(rows, start_date=start_date, provider="U.S. Treasury",
                             source_mode="bundled_snapshot", source_attempts=attempts,
                             fallback_used=True, snapshot_captured_at=SNAPSHOT_CAPTURED_AT)
        except (OSError, RateSourceError) as exc:
            attempts.append(_source_attempt("U.S. Treasury", "bundled_snapshot", "FAILED", exc))
            summary = "; ".join(
                f"{row['provider']} {row['source_mode']}: {row.get('error_message', row['status'])}"
                for row in attempts
            )
            raise ConnectionError(f"all public rate sources failed: {summary}") from exc

    def _fetch_treasury(self, start_date: str) -> list[dict]:
        requested_year = date.fromisoformat(start_date).year
        current_year = self._today().year
        all_rows = {}
        for year in range(current_year, requested_year - 1, -1):
            try:
                check_run_control()
                raw = self._transport(_treasury_year_url(year))
                check_run_control()
            except (ConnectionError, TimeoutError, RuntimeError) as exc:
                raise ConnectionError(f"U.S. Treasury {year} connection failed: {exc}") from exc
            for row in _parse_treasury_csv(raw, year):
                all_rows[row["date"]] = row
            if len(all_rows) >= TREASURY_MIN_OBSERVATIONS:
                break
        rows = [all_rows[key] for key in sorted(all_rows) if key >= start_date]
        if len(rows) < 80:
            raise RateSourceError(
                f"U.S. Treasury returned only {len(rows)} usable observations; need at least 80"
            )
        return rows


def _fred_bulk_url(start_date: str) -> str:
    return f"{FRED_GRAPH_CSV_URL}?{urlencode({'id': 'DGS2,DGS10', 'cosd': start_date})}"


def _treasury_year_url(year: int) -> str:
    query = urlencode({"_format": "csv", "field_tdr_date_value": str(year), "page": "",
                       "type": "daily_treasury_yield_curve"})
    return f"{TREASURY_CSV_URL.format(year=year)}?{query}"


def _parse_fred_curve_csv(raw: str, start_date: str) -> list[dict]:
    reader = _csv_reader(raw, "FRED bulk CSV")
    date_field = "DATE" if "DATE" in reader.fieldnames else "observation_date"
    if not {date_field, "DGS2", "DGS10"}.issubset(set(reader.fieldnames or [])):
        raise RateSourceError("FRED bulk CSV must contain date, DGS2, and DGS10 columns")
    rows = []
    for raw_row in reader:
        period = (raw_row.get(date_field) or "").strip()
        if not period or period < start_date:
            continue
        row = _curve_row(period, raw_row.get("DGS2"), raw_row.get("DGS10"))
        if row:
            rows.append(row)
    if not rows:
        raise RateSourceError("FRED bulk CSV returned no aligned numeric observations")
    return rows


def _parse_treasury_csv(raw: str, year: int) -> list[dict]:
    reader = _csv_reader(raw, f"U.S. Treasury {year} CSV")
    if not {"Date", "2 Yr", "10 Yr"}.issubset(set(reader.fieldnames or [])):
        raise RateSourceError(f"U.S. Treasury {year} CSV must contain Date, 2 Yr, and 10 Yr")
    rows = []
    for raw_row in reader:
        try:
            period = datetime.strptime((raw_row.get("Date") or "").strip(), "%m/%d/%Y").date().isoformat()
        except ValueError:
            continue
        row = _curve_row(period, raw_row.get("2 Yr"), raw_row.get("10 Yr"))
        if row:
            rows.append(row)
    if not rows:
        raise RateSourceError(f"U.S. Treasury {year} CSV returned no usable observations")
    return rows


def _parse_snapshot_csv(raw: str, start_date: str) -> list[dict]:
    reader = _csv_reader(raw, "bundled rate snapshot")
    if not {"Date", "DGS2", "DGS10"}.issubset(set(reader.fieldnames or [])):
        raise RateSourceError("bundled rate snapshot has an invalid header")
    rows = []
    for raw_row in reader:
        period = (raw_row.get("Date") or "").strip()
        if period < start_date:
            continue
        row = _curve_row(period, raw_row.get("DGS2"), raw_row.get("DGS10"))
        if row:
            rows.append(row)
    if len(rows) < 80:
        raise RateSourceError(
            f"bundled rate snapshot has only {len(rows)} usable observations; need at least 80"
        )
    return rows


def _csv_reader(raw: str, label: str) -> csv.DictReader:
    if not isinstance(raw, str) or not raw.strip():
        raise RateSourceError(f"{label} returned an empty response")
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        raise RateSourceError(f"{label} has no header")
    return reader


def _curve_row(period: str, dgs2_value, dgs10_value) -> dict | None:
    try:
        _iso_date(period, "observation date")
        dgs2 = float(str(dgs2_value or "").strip())
        dgs10 = float(str(dgs10_value or "").strip())
    except (TypeError, ValueError):
        return None
    return {"date": period, "dgs2": dgs2, "dgs10": dgs10,
            "spread_bps": round((dgs10 - dgs2) * 100, 6)}


def _source_attempt(provider: str, source_mode: str, status: str, exc=None) -> dict:
    row = {"provider": provider, "source_mode": source_mode, "status": status}
    if exc is not None:
        row.update(error_type=exc.__class__.__name__, error_message=str(exc))
    return row


def _artifact(observations, *, start_date, provider, source_mode, source_attempts,
              fallback_used, snapshot_captured_at=None) -> dict:
    if not observations:
        raise RateSourceError("selected rate source returned no observations")
    is_snapshot = source_mode == "bundled_snapshot"
    if provider == "FRED":
        publisher = "Federal Reserve Bank of St. Louis"
        uri_for = lambda series_id: f"https://fred.stlouisfed.org/series/{series_id}"
    else:
        publisher = "U.S. Department of the Treasury"
        uri_for = lambda _series_id: TREASURY_SERIES_URL
    return {
        "artifact_type": "rate_curve_history",
        "provider": provider,
        "source_mode": source_mode,
        "source_freshness": "SNAPSHOT" if is_snapshot else "LIVE",
        "fallback_used": fallback_used,
        "source_attempts": source_attempts,
        "snapshot_captured_at": snapshot_captured_at,
        "series": [
            {"series_id": series_id,
             "evidence_id": (f"FRED:{series_id}" if provider == "FRED"
                             else f"UST:{'2Y' if series_id == 'DGS2' else '10Y'}"),
             "provider": provider, "publisher": publisher, "label": label,
             "unit": "percent", "source_url": uri_for(series_id)}
            for series_id, base_label in RATE_SERIES.items()
            for label in [base_label if provider == "FRED"
                          else base_label.replace("Constant Maturity", "Par Yield Curve")]
        ],
        "start_date": start_date,
        "as_of": observations[-1]["date"],
        "observation_count": len(observations),
        "observations": observations,
        "guardrails": {"common_dates_only": True, "missing_values_dropped": True,
                       "api_key_required": False, "values_fabricated": False,
                       "certificate_verification_disabled": False,
                       "snapshot_disclosed": is_snapshot},
    }


def _iso_date(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be YYYY-MM-DD") from exc
    return value


def _http_get_text(url: str) -> str:
    return native_http_get_text(url, accept="text/csv,text/plain;q=0.9,*/*;q=0.1")
