"""Run real R4 source API smoke checks from the command line.

Examples:
    python3 source_smoke.py
    python3 source_smoke.py BLS
    python3 source_smoke.py BLS FRED EIA

FRED_API_KEY and EIA_API_KEY remain environment variables. The JSON report never
prints credential values.
"""

from __future__ import annotations

import argparse
import json

from r4_source_health import PROVIDER_ORDER, run_source_health


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Test real macro source APIs")
    parser.add_argument(
        "providers",
        nargs="*",
        metavar="PROVIDER",
        help="Providers to test (BLS, FRED, EIA). Default: all providers",
    )
    return parser


def normalize_providers(values: list[str]) -> list[str] | None:
    if not values:
        return None
    normalized = [value.upper() for value in values]
    invalid = [value for value in normalized if value not in PROVIDER_ORDER]
    if invalid:
        allowed = ", ".join(PROVIDER_ORDER)
        raise ValueError(f"unknown provider(s): {', '.join(invalid)}; choose from {allowed}")
    return normalized


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        providers = normalize_providers(args.providers)
    except ValueError as exc:
        parser.error(str(exc))
    report = run_source_health(providers)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
