"""R4 source API health and contract checks.

A health check is operational, not analytical. It verifies that the same
production adapters used by research can reach the public APIs, authenticate,
parse JSON, and satisfy the normalized Evidence contract. It also reports the
latest observation date separately from API readiness so a slower monthly series
is not confused with a broken endpoint.

Secrets remain Runtime-owned. Reports contain only credential names and whether
they are present; they never contain credential values or request URLs with
secret query parameters.
"""

from __future__ import annotations

import calendar
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime
from time import perf_counter
from typing import Callable

from api_sources import (
    API_SERIES,
    BLS_BASE_URL,
    EIA_GASOLINE_URL,
    FRED_OBSERVATIONS_URL,
)
from api_sources_native import (
    fetch_bls_api_series,
    fetch_eia_api_series,
    fetch_fred_api_series,
)


PROVIDER_ORDER = ("BLS", "FRED", "EIA")
REQUIRED_ENV = {
    "BLS": (),
    "FRED": ("FRED_API_KEY",),
    "EIA": ("EIA_API_KEY",),
}
SAFE_ENDPOINTS = {
    "BLS": BLS_BASE_URL,
    "FRED": FRED_OBSERVATIONS_URL,
    "EIA": EIA_GASOLINE_URL,
}
PROBES = {
    "BLS": "headline_cpi",
    "FRED": "breakeven_5y",
    "EIA": "regular_gasoline",
}
# Operational heuristics for the workbench, not official publication SLAs.
FRESH_DAYS = {
    "BLS": 75,
    "FRED": 14,
    "EIA": 21,
}


@dataclass(frozen=True)
class SourceHealthResult:
    provider: str
    status: str
    ready: bool
    endpoint: str
    credential_names: tuple[str, ...]
    credentials_present: bool
    series_id: str
    evidence_id: str | None = None
    as_of: str | None = None
    age_days: int | None = None
    freshness: str = "UNKNOWN"
    latency_ms: float | None = None
    transport: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    checks: tuple[dict, ...] = ()

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["credential_names"] = list(self.credential_names)
        payload["checks"] = list(self.checks)
        return payload


class SourceHealthChecker:
    def __init__(
        self,
        *,
        fetchers: dict[str, Callable] | None = None,
        env=None,
        today: date | None = None,
    ):
        self._fetchers = fetchers or {
            "BLS": fetch_bls_api_series,
            "FRED": fetch_fred_api_series,
            "EIA": fetch_eia_api_series,
        }
        self._env = os.environ if env is None else env
        self._today = today or date.today()

    def run(self, providers: tuple[str, ...] | list[str] | None = None) -> dict:
        requested = tuple(providers or PROVIDER_ORDER)
        unknown = [provider for provider in requested if provider not in PROVIDER_ORDER]
        if unknown:
            raise ValueError(f"Unknown source providers: {unknown}")
        results = [self.check(provider).to_dict() for provider in requested]
        ready_count = sum(1 for item in results if item["ready"])
        if ready_count == len(results):
            overall = "READY"
        elif ready_count == 0:
            overall = "UNAVAILABLE"
        else:
            overall = "PARTIAL"
        return {
            "overall": overall,
            "ready": ready_count == len(results),
            "ready_count": ready_count,
            "total": len(results),
            "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "results": results,
            "note": "Freshness thresholds are workbench heuristics, not provider publication SLAs.",
        }

    def check(self, provider: str) -> SourceHealthResult:
        if provider not in PROVIDER_ORDER:
            raise ValueError(f"Unknown source provider: {provider}")
        capability = PROBES[provider]
        series = API_SERIES[capability]
        credential_names = REQUIRED_ENV[provider]
        credentials_present = all(bool(self._env.get(name)) for name in credential_names)
        base_checks = [
            {
                "check": "credential",
                "passed": credentials_present,
                "detail": (
                    "no credential required"
                    if not credential_names
                    else f"required env present: {', '.join(credential_names)}"
                    if credentials_present
                    else f"missing env: {', '.join(name for name in credential_names if not self._env.get(name))}"
                ),
            }
        ]
        if not credentials_present:
            return SourceHealthResult(
                provider=provider,
                status="CREDENTIAL_MISSING",
                ready=False,
                endpoint=SAFE_ENDPOINTS[provider],
                credential_names=credential_names,
                credentials_present=False,
                series_id=series["series_id"],
                checks=tuple(base_checks),
                error_type="CredentialMissing",
                error_message="One or more required environment variables are missing.",
            )

        started = perf_counter()
        try:
            evidence = self._fetch(provider, series)
        except Exception as exc:  # health layer must classify adapter/network failures
            latency_ms = round((perf_counter() - started) * 1000, 1)
            status = _classify_error(exc)
            checks = base_checks + [
                {"check": "api_request", "passed": False, "detail": _safe_error(exc)}
            ]
            return SourceHealthResult(
                provider=provider,
                status=status,
                ready=False,
                endpoint=SAFE_ENDPOINTS[provider],
                credential_names=credential_names,
                credentials_present=True,
                series_id=series["series_id"],
                latency_ms=latency_ms,
                error_type=exc.__class__.__name__,
                error_message=_safe_error(exc),
                checks=tuple(checks),
            )

        latency_ms = round((perf_counter() - started) * 1000, 1)
        contract_errors = _validate_evidence(provider, series["series_id"], evidence)
        if contract_errors:
            checks = base_checks + [
                {"check": "api_request", "passed": True, "detail": "received JSON response"},
                {
                    "check": "evidence_contract",
                    "passed": False,
                    "detail": "; ".join(contract_errors),
                },
            ]
            return SourceHealthResult(
                provider=provider,
                status="CONTRACT_ERROR",
                ready=False,
                endpoint=SAFE_ENDPOINTS[provider],
                credential_names=credential_names,
                credentials_present=True,
                series_id=series["series_id"],
                evidence_id=evidence.get("evidence_id") if isinstance(evidence, dict) else None,
                latency_ms=latency_ms,
                checks=tuple(checks),
                error_type="EvidenceContractError",
                error_message="; ".join(contract_errors),
            )

        as_of = str(evidence.get("as_of"))
        age_days = _age_days(as_of, self._today)
        freshness = _freshness(provider, age_days)
        checks = base_checks + [
            {"check": "api_request", "passed": True, "detail": "request completed"},
            {"check": "evidence_contract", "passed": True, "detail": "normalized Evidence contract valid"},
            {
                "check": "freshness",
                "passed": freshness != "STALE",
                "detail": f"as_of={as_of}; age_days={age_days}; status={freshness}",
            },
        ]
        return SourceHealthResult(
            provider=provider,
            status="READY",
            ready=True,
            endpoint=SAFE_ENDPOINTS[provider],
            credential_names=credential_names,
            credentials_present=True,
            series_id=series["series_id"],
            evidence_id=evidence["evidence_id"],
            as_of=as_of,
            age_days=age_days,
            freshness=freshness,
            latency_ms=latency_ms,
            transport=evidence.get("transport"),
            checks=tuple(checks),
        )

    def _fetch(self, provider: str, series: dict) -> dict:
        fetcher = self._fetchers[provider]
        if provider == "BLS":
            return fetcher(series["series_id"], series["label"])
        return fetcher(series["series_id"], series["label"], series["unit"])


def _validate_evidence(provider: str, series_id: str, evidence) -> list[str]:
    if not isinstance(evidence, dict):
        return ["adapter result is not an object"]
    errors = []
    required = ("kind", "evidence_id", "value", "unit", "as_of", "history", "source")
    for key in required:
        if key not in evidence:
            errors.append(f"missing {key}")
    if evidence.get("kind") != "evidence":
        errors.append("kind must equal evidence")
    evidence_id = evidence.get("evidence_id")
    if evidence_id != f"{provider}:{series_id}":
        errors.append(f"unexpected evidence_id {evidence_id!r}")
    history = evidence.get("history")
    if not isinstance(history, list) or not history:
        errors.append("history must be a non-empty list")
    source = evidence.get("source")
    if not isinstance(source, dict):
        errors.append("source must be an object")
    else:
        if not source.get("publisher"):
            errors.append("source.publisher is missing")
        if not source.get("uri"):
            errors.append("source.uri is missing")
    return errors


def _classify_error(exc: BaseException) -> str:
    text = f"{exc.__class__.__name__}: {exc}".upper()
    if "CERTIFICATE_VERIFY_FAILED" in text or "SSL" in text or "TLS" in text:
        return "TLS_ERROR"
    if "API_KEY" in text or "CREDENTIAL" in text or "UNAUTHORIZED" in text or "FORBIDDEN" in text:
        return "AUTH_ERROR"
    if "HTTP 4" in text or "HTTP 5" in text:
        return "HTTP_ERROR"
    if isinstance(exc, TimeoutError) or "TIMED OUT" in text or "TIMEOUT" in text:
        return "TIMEOUT"
    if isinstance(exc, ConnectionError):
        return "CONNECTION_ERROR"
    return "API_ERROR"


def _safe_error(exc: BaseException) -> str:
    text = str(exc).strip()
    # The production adapters never include credential values in their own
    # messages. Keep this extra guard so a future exception cannot accidentally
    # echo a known Runtime secret into health diagnostics.
    for env_name in ("FRED_API_KEY", "EIA_API_KEY"):
        secret = os.environ.get(env_name)
        if secret:
            text = text.replace(secret, f"<{env_name}:redacted>")
    return text or repr(exc)


def _age_days(as_of: str, today: date) -> int | None:
    try:
        if len(as_of) == 7:
            year, month = (int(part) for part in as_of.split("-"))
            day = calendar.monthrange(year, month)[1]
            observed = date(year, month, day)
        else:
            observed = date.fromisoformat(as_of[:10])
    except (TypeError, ValueError):
        return None
    return max(0, (today - observed).days)


def _freshness(provider: str, age_days: int | None) -> str:
    if age_days is None:
        return "UNKNOWN"
    threshold = FRESH_DAYS[provider]
    if age_days <= threshold:
        return "FRESH"
    if age_days <= threshold * 2:
        return "AGING"
    return "STALE"


def run_source_health(providers: tuple[str, ...] | list[str] | None = None) -> dict:
    return SourceHealthChecker().run(providers)
