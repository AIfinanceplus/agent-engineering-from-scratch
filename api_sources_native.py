"""Production wrappers that route API adapters through native OS TLS trust.

BLS can run anonymously, but when BLS_API_KEY is present we deliberately use
an authenticated v2 POST so the request is counted against the registered-user
quota. The key stays Runtime-owned and never enters Tool arguments or Evidence.
"""

import os

from api_sources import BLS_BASE_URL, BLSPublicAPI, EIAPublicAPI, FREDPublicAPI
from native_http import http_get_json, http_post_json


_BLS = BLSPublicAPI(transport=http_get_json, post_transport=http_post_json)
# BLSPublicAPI treats an injected transport as a test transport and normally
# disables fallback. Here both injected transports are production HTTPS paths,
# so preserve GET -> POST fallback semantics for anonymous requests.
_BLS._custom_transport = False
_FRED = FREDPublicAPI(transport=http_get_json)
_EIA = EIAPublicAPI(transport=http_get_json)


def fetch_bls_api_series(series_id: str, label: str) -> dict:
    registration_key = os.environ.get("BLS_API_KEY")
    if registration_key:
        # BLS documents registrationkey on the v2 POST payload. Do not put the
        # key in the URL, Tool args, Evidence, source URI, or Trace.
        payload = http_post_json(
            f"{BLS_BASE_URL}/",
            {
                "seriesid": [series_id],
                "registrationkey": registration_key,
            },
        )
        parser = BLSPublicAPI(transport=lambda _url: payload)
        result = parser.fetch(series_id, label)
        result["transport"] = "POST_REGISTERED"
        result["note"] = "Live BLS Public Data API v2 observation using registered Runtime quota."
        return result
    return _BLS.fetch(series_id, label)


def fetch_fred_api_series(series_id: str, label: str, unit: str) -> dict:
    return _FRED.fetch(series_id, label, unit)


def fetch_eia_api_series(series_id: str, label: str, unit: str) -> dict:
    return _EIA.fetch(series_id, label, unit)
