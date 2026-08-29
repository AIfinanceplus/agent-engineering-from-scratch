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


def main() -> int:
    parser = argparse.ArgumentParser(description="Test real macro source APIs")
    parser.add_argument(
        "providers",
        nargs="*",
        choices=PROVIDER_ORDER,
        help="Providers to test. Default: BLS FRED EIA",
    )
    args = parser.parse_args()
    report = run_source_health(args.providers or None)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
