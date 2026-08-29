"""Live-source preflight for the R2 workbench.

This module reports whether required Runtime-owned credentials exist without
returning credential values. It is intentionally separate from Tool arguments,
Plan data, Evidence, and Trace.
"""

from __future__ import annotations

import os


def live_source_preflight(env=None) -> dict:
    environment = os.environ if env is None else env
    fred_ready = bool(environment.get("FRED_API_KEY"))
    eia_ready = bool(environment.get("EIA_API_KEY"))

    sources = [
        {
            "provider": "BLS",
            "ready": True,
            "credential": "none",
            "detail": "Current BLS public-data path does not require an API key.",
        },
        {
            "provider": "FRED",
            "ready": fred_ready,
            "credential": "FRED_API_KEY",
            "detail": (
                "Runtime environment variable detected."
                if fred_ready
                else "Set FRED_API_KEY before starting the workbench."
            ),
        },
        {
            "provider": "EIA",
            "ready": eia_ready,
            "credential": "EIA_API_KEY",
            "detail": (
                "Runtime environment variable detected."
                if eia_ready
                else "Set EIA_API_KEY before starting the workbench."
            ),
        },
    ]
    missing = [
        item["credential"]
        for item in sources
        if not item["ready"] and item["credential"] != "none"
    ]
    return {
        "ready": not missing,
        "sources": sources,
        "missing_env": missing,
        "setup": [f'export {name}="..."' for name in missing],
        "security": "Credential presence only. Secret values are never returned.",
    }
