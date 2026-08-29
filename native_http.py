"""HTTPS transport backed by the operating system's native certificate store.

On macOS this uses Security.framework through truststore, so Python sees the
same trusted roots/intermediates that Safari/Chrome can use. Certificate
verification remains enabled; this module never creates an unverified context.
"""

from __future__ import annotations

import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    import truststore
except ImportError:  # pragma: no cover - exercised on user machines missing deps
    truststore = None


def system_ssl_context():
    if truststore is None:
        raise RuntimeError(
            "Python TLS needs the truststore package. Run: "
            "python3 -m pip install -r requirements.txt"
        )
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def http_get_json(url: str) -> dict:
    request = Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 agent-engineering-from-scratch/2.3",
        },
    )
    return _open_json(request)


def http_post_json(url: str, payload: dict) -> dict:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 agent-engineering-from-scratch/2.3",
        },
    )
    return _open_json(request)


def _open_json(request: Request) -> dict:
    try:
        with urlopen(request, timeout=15, context=system_ssl_context()) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        message = f"HTTP {exc.code} {exc.reason or ''}".strip()
        if body:
            message += f": {body}"
        if 500 <= exc.code < 600:
            raise ConnectionError(message) from exc
        raise RuntimeError(message) from exc
    except TimeoutError as exc:
        raise TimeoutError("public API request timed out after 15s") from exc
    except URLError as exc:
        reason = getattr(exc, "reason", None)
        reason_type = type(reason).__name__ if reason is not None else type(exc).__name__
        detail = str(reason).strip() if reason is not None else str(exc).strip()
        if not detail:
            detail = repr(reason if reason is not None else exc)
        raise ConnectionError(f"{reason_type}: {detail}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"response was not valid JSON: {exc.msg}") from exc
