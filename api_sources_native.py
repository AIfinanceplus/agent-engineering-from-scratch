"""Production wrappers that route API adapters through native OS TLS trust."""

from api_sources import BLSPublicAPI, EIAPublicAPI, FREDPublicAPI
from native_http import http_get_json, http_post_json


_BLS = BLSPublicAPI(transport=http_get_json, post_transport=http_post_json)
# BLSPublicAPI treats an injected transport as a test transport and normally
# disables fallback. Here both injected transports are production HTTPS paths,
# so preserve GET -> POST fallback semantics.
_BLS._custom_transport = False
_FRED = FREDPublicAPI(transport=http_get_json)
_EIA = EIAPublicAPI(transport=http_get_json)


def fetch_bls_api_series(series_id: str, label: str) -> dict:
    return _BLS.fetch(series_id, label)


def fetch_fred_api_series(series_id: str, label: str, unit: str) -> dict:
    return _FRED.fetch(series_id, label, unit)


def fetch_eia_api_series(series_id: str, label: str, unit: str) -> dict:
    return _EIA.fetch(series_id, label, unit)
